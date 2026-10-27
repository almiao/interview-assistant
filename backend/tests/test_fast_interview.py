from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from api.assist.asr_state import AssistAsrStateMachine
from api.assist.answer_worker import _max_tokens_for_prompt
from core.config import AppConfig
from services.llm.prompts import build_system_prompt
from services.llm.prompts import create_answer_stream_sanitizer


def test_explicit_question_dispatches_in_200ms_without_merge_or_extra_grace():
    clock = [0.0]
    tasks = []
    cfg = AppConfig(transcription_min_sig_chars=2)
    session = SimpleNamespace(capture_is_loopback=True, add_transcription=lambda _: None)
    state = AssistAsrStateMachine(
        broadcast=lambda _: None, submit_answer_task=lambda t: tasks.append(t) or True,
        begin_asr_turn=lambda: 1, record_asr_turn=lambda _: None,
        is_high_churn_submission=lambda *_: False, logger=Mock(), clock=lambda: clock[0],
    )
    state.append_transcription_fragment(cfg, session, 'Redis 持久化讲一下', 0.0)
    assert state.pending_group is not None
    clock[0] = 0.19
    state.try_flush_question_group(cfg, session, clock[0])
    assert not tasks
    clock[0] = 0.2
    state.try_flush_question_group(cfg, session, clock[0])
    assert tasks[0][4]['dispatch_after_mono'] == pytest.approx(0.2)


def test_constraint_arriving_before_confirmation_is_not_lost():
    clock = [0.0]
    tasks = []
    cfg = AppConfig(transcription_min_sig_chars=2)
    session = SimpleNamespace(capture_is_loopback=True, add_transcription=lambda _: None)
    state = AssistAsrStateMachine(
        broadcast=lambda _: None, submit_answer_task=lambda t: tasks.append(t) or True,
        begin_asr_turn=lambda: 1, record_asr_turn=lambda _: None,
        is_high_churn_submission=lambda *_: False, logger=Mock(), clock=lambda: clock[0],
    )
    state.append_transcription_fragment(cfg, session, 'Redis 持久化讲一下', 0.0)
    clock[0] = 0.1
    state.append_transcription_fragment(cfg, session, '不要结合项目', clock[0])
    clock[0] = 0.31
    state.try_flush_question_group(cfg, session, clock[0])
    assert len(tasks) == 1
    assert '不要结合项目' in tasks[0][0]


def test_outline_is_default_without_conflicting_long_answer_contract():
    prompt = build_system_prompt(mode='asr_realtime', answer_style='outline')
    assert AppConfig().assist_answer_style == 'outline'
    assert '60-100 字' in prompt
    assert '专注面板输出协议' not in prompt
    assert '420-780' not in prompt
    assert '新增或修正' in prompt
    assert _max_tokens_for_prompt('asr_realtime', AppConfig()) == 320
    assert '详细回答模式' in build_system_prompt(mode='asr_realtime', answer_style='detailed')
    with pytest.raises(ValidationError):
        AppConfig(assist_answer_style='unknown')


def test_outline_does_not_change_written_exam_or_screenshot_prompts():
    for mode in ('written_exam', 'server_screen_code'):
        assert build_system_prompt(mode=mode, answer_style='outline') == build_system_prompt(mode=mode, answer_style='detailed')


@pytest.mark.parametrize('question', ['请写代码实现 LRU', '给出完整 Java 代码', '实现一下线程安全队列', 'write a function to sort a list', '请用 Java 实现 LRU 缓存', '手写一个线程安全队列', 'implement an LRU cache'])
def test_explicit_code_requests_keep_full_token_budget(question):
    for mode in ('asr_realtime', 'manual_text'):
        assert _max_tokens_for_prompt(mode, AppConfig(), question_text=question) == 4096


def test_fast_cleaner_emits_before_64_chars_and_still_hides_split_reasoning():
    cleaner = create_answer_stream_sanitizer('asr_realtime', low_latency=True)
    assert cleaner.push('先更新数据库再删缓存，通过重试补偿保证最终一致性。')
    cleaner = create_answer_stream_sanitizer('asr_realtime', low_latency=True)
    chunks = ['<thi', 'nk>内部', '思考不应该显示', '</th', 'ink>先更新数据库，再删除缓存。']
    output = ''.join(cleaner.push(chunk) for chunk in chunks) + cleaner.finish()
    assert output == '先更新数据库，再删除缓存。'
