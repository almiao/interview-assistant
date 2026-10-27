"""ASR merge and question-group state machine for interview assist."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from services.stt import (
    build_asr_question_group_text,
    classify_asr_question_candidate,
    is_asr_question_constraint_tail,
    is_viable_asr_question_group,
    join_transcription_fragments,
    transcription_for_publish,
    transcription_significant_len,
    is_interview_boilerplate_text,
    is_backchannel_text,
)
from api.assist.scheduler import TaskPayload


@dataclass
class PendingASRGroup:
    source: str
    utterances: list[str] = field(default_factory=list)
    first_mono: float = 0.0
    last_mono: float = 0.0
    has_promote: bool = False


class AssistAsrStateMachine:
    def __init__(
        self,
        *,
        broadcast: Callable[[dict], None],
        submit_answer_task: Callable[[TaskPayload], bool],
        begin_asr_turn: Callable[[], int],
        record_asr_turn: Callable[[float], None],
        is_high_churn_submission: Callable[[Any, float], bool],
        logger,
        append_late_constraint_tail: Callable[[str, str, float], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.broadcast = broadcast
        self.submit_answer_task = submit_answer_task
        self.begin_asr_turn = begin_asr_turn
        self.record_asr_turn = record_asr_turn
        self.is_high_churn_submission = is_high_churn_submission
        self.append_late_constraint_tail = append_late_constraint_tail or (lambda _text, _source, _now: False)
        self.logger = logger
        self.clock = clock
        self.merge_parts: list[str] = []
        self.merge_mono_first: Optional[float] = None
        self.merge_mono_last: Optional[float] = None
        self.pending_group: Optional[PendingASRGroup] = None

    def reset_merge_buffer(self):
        self.merge_parts = []
        self.merge_mono_first = None
        self.merge_mono_last = None

    def reset_pending_group(self):
        self.pending_group = None

    def flush_question_group_now(self, cfg, session) -> None:
        group = self.pending_group
        if group is None:
            return
        self.pending_group = None
        # The initial classifier sees the original '?' and marks a question
        # as promoted. Splitting/revalidation must not erase that evidence.
        if not group.has_promote and not is_viable_asr_question_group(
            group.utterances,
            getattr(cfg, "transcription_min_sig_chars", 2),
        ):
            self.logger.info(
                "ASR_FILTER stage=question_group reason=no_question_evidence source=%s min_sig_chars=%d utterances=%r",
                group.source, getattr(cfg, "transcription_min_sig_chars", 2), group.utterances,
            )
            return
        question_text = build_asr_question_group_text(group.utterances)
        if not question_text:
            self.logger.info(
                "ASR_FILTER stage=question_group reason=empty_question_after_build source=%s utterances=%r",
                group.source, group.utterances,
            )
            return
        now_mono = self.clock()
        high_churn_short = self.is_high_churn_submission(cfg, now_mono)
        turn_id = self.begin_asr_turn()
        self.record_asr_turn(now_mono)
        self.logger.info(
            "ASR_QUESTION turn=%d utterances=%d churn=%s text=%r",
            turn_id, len(group.utterances), high_churn_short,
            question_text[:150],
        )
        accepted = self.submit_answer_task(
            (
                question_text,
                None,
                False,
                group.source,
                {
                    "origin": "asr",
                    "asr_turn_id": turn_id,
                    "utterances": list(group.utterances),
                    "high_churn_short_answer": high_churn_short,
                    "dispatch_after_mono": now_mono + _asr_late_constraint_grace_sec(cfg),
                    "asr_tail_grace_until_mono": now_mono + _asr_late_constraint_grace_sec(cfg),
                },
            )
        )
        if not accepted:
            self.logger.info(
                "ASR_FILTER stage=submit reason=task_rejected turn=%d source=%s text=%r",
                turn_id, group.source, question_text,
            )

    def try_flush_question_group(self, cfg, session, now_mono: float, force: bool = False) -> None:
        group = self.pending_group
        if group is None:
            return
        confirm = _asr_confirm_window_sec(cfg)
        fast_confirm = _asr_fast_confirm_sec(cfg)
        max_wait = _asr_group_max_wait_sec(cfg)
        if group.has_promote and len(group.utterances) == 1:
            max_wait = max(max_wait, fast_confirm + confirm)
        since_last = now_mono - group.last_mono
        age = now_mono - group.first_mono
        if force or age >= max_wait:
            self.flush_question_group_now(cfg, session)
        elif group.has_promote and len(group.utterances) == 1 and since_last >= fast_confirm:
            self.flush_question_group_now(cfg, session)
        elif group.has_promote and since_last >= confirm:
            self.flush_question_group_now(cfg, session)
        elif not group.has_promote and since_last >= confirm * 2:
            self.flush_question_group_now(cfg, session)

    def handle_auto_detect_asr_text(self, cfg, session, pub: str, source: str, now_mono: float) -> None:
        kind, cleaned = classify_asr_question_candidate(
            pub,
            getattr(cfg, "transcription_min_sig_chars", 2),
        )
        self.logger.info(
            "ASR_CLASSIFY kind=%s source=%s min_sig_chars=%d text=%r normalized=%r",
            kind, source, getattr(cfg, "transcription_min_sig_chars", 2), pub, cleaned,
        )
        if not cleaned:
            self.logger.info("ASR_FILTER stage=classify reason=empty_after_normalization source=%s text=%r", source, pub)
            return
        # Classification uses normalized text; display and prompts retain ASR punctuation.
        display_text = pub.strip()
        if (
            self.pending_group is None
            and kind == "candidate"
            and is_asr_question_constraint_tail(cleaned)
            and self.append_late_constraint_tail(display_text, source, now_mono)
        ):
            return
        if (
            self.pending_group is not None
            and kind == "candidate"
            and is_asr_question_constraint_tail(cleaned)
        ):
            self.pending_group.utterances.append(display_text)
            self.pending_group.last_mono = now_mono
            self.pending_group.source = source
            return
        self.try_flush_question_group(cfg, session, now_mono, False)
        if kind == "ignore" and self.pending_group is None:
            reason = (
                "boilerplate" if is_interview_boilerplate_text(pub)
                else "backchannel" if is_backchannel_text(pub)
                else "not_question_candidate"
            )
            self.logger.info(
                "ASR_FILTER stage=classify reason=%s source=%s significant_chars=%d min_sig_chars=%d text=%r",
                reason, source, transcription_significant_len(cleaned),
                getattr(cfg, "transcription_min_sig_chars", 2), pub,
            )
            return
        if self.pending_group is None:
            self.pending_group = PendingASRGroup(
                source=source,
                utterances=[display_text],
                first_mono=now_mono,
                last_mono=now_mono,
                has_promote=(kind == "promote"),
            )
        else:
            self.pending_group.utterances.append(display_text)
            self.pending_group.last_mono = now_mono
            self.pending_group.source = source
            self.pending_group.has_promote = self.pending_group.has_promote or kind == "promote"

    def flush_merge_buffer_now(self, cfg, session) -> None:
        if not self.merge_parts:
            return
        parts = list(self.merge_parts)
        self.merge_parts.clear()
        self.merge_mono_first = None
        self.merge_mono_last = None
        merged_raw = join_transcription_fragments(parts)
        min_sig = getattr(cfg, "transcription_min_sig_chars", 2)
        pub = transcription_for_publish(merged_raw, min_sig)
        if not pub:
            self.logger.info(
                "ASR_FILTER stage=merge_publish reason=%s significant_chars=%d min_sig_chars=%d text=%r",
                "empty_text" if not merged_raw.strip() else "boilerplate" if is_interview_boilerplate_text(merged_raw) else "below_min_significant_chars",
                transcription_significant_len(merged_raw), min_sig, merged_raw,
            )
            return
        session.add_transcription(pub)
        self.broadcast({"type": "transcription", "text": pub})
        if cfg.auto_detect:
            source = (
                "conversation_loopback"
                if session.capture_is_loopback
                else "conversation_mic"
            )
            self.handle_auto_detect_asr_text(cfg, session, pub, source, self.clock())
        else:
            self.logger.info("ASR_FILTER stage=auto_detect reason=disabled text=%r", pub)

    def try_flush_merge_buffer(self, cfg, session, now_mono: float, force: bool = False) -> None:
        if not self.merge_parts:
            return
        gap = float(getattr(cfg, "assist_transcription_merge_gap_sec", 0.0) or 0.0)
        max_wait = float(getattr(cfg, "assist_transcription_merge_max_sec", 12.0) or 12.0)
        if max_wait < 1.0:
            max_wait = 12.0
        if force:
            self.flush_merge_buffer_now(cfg, session)
            return
        if gap <= 0:
            return
        if self.merge_mono_last is None:
            return
        since_last = now_mono - self.merge_mono_last
        burst_age = (now_mono - self.merge_mono_first) if self.merge_mono_first is not None else 0.0
        if since_last >= gap or burst_age >= max_wait:
            self.flush_merge_buffer_now(cfg, session)

    def append_transcription_fragment(
        self,
        cfg,
        session,
        pub: str,
        now_mono: float,
        force_flush_tail: bool = False,
    ) -> None:
        gap = float(getattr(cfg, "assist_transcription_merge_gap_sec", 0.0) or 0.0)
        if gap <= 0:
            session.add_transcription(pub)
            self.broadcast({"type": "transcription", "text": pub})
            if cfg.auto_detect:
                source = (
                    "conversation_loopback"
                    if session.capture_is_loopback
                    else "conversation_mic"
                )
                self.handle_auto_detect_asr_text(cfg, session, pub, source, now_mono)
            else:
                self.logger.info("ASR_FILTER stage=auto_detect reason=disabled text=%r", pub)
            return
        if not self.merge_parts:
            self.merge_mono_first = now_mono
        self.merge_parts.append(pub)
        self.merge_mono_last = now_mono
        if force_flush_tail:
            self.flush_merge_buffer_now(cfg, session)
        else:
            self.try_flush_merge_buffer(cfg, session, now_mono, False)


def _asr_confirm_window_sec(cfg) -> float:
    confirm = float(getattr(cfg, "assist_asr_confirm_window_sec", 0.2) or 0.0)
    return max(0.0, min(5.0, confirm))


def _asr_group_max_wait_sec(cfg) -> float:
    max_wait = float(getattr(cfg, "assist_asr_group_max_wait_sec", 1.2) or 0.0)
    return max(0.2, min(8.0, max_wait))


def _asr_fast_confirm_sec(cfg) -> float:
    fast = float(getattr(cfg, "assist_asr_fast_confirm_sec", 1.15) or 0.0)
    return max(0.1, min(2.0, fast))


def _asr_late_constraint_grace_sec(cfg) -> float:
    grace = float(getattr(cfg, "assist_asr_late_constraint_grace_sec", 0.0) or 0.0)
    return max(0.0, min(3.0, grace))


def asr_interrupt_running(cfg) -> bool:
    return bool(getattr(cfg, "assist_asr_interrupt_running", True))
