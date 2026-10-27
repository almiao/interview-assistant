from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from api.assist import routes
from api.assist.answer_worker import prompt_mode_for_task, _max_tokens_for_prompt
from services.capture import screen_capture as capture
from services.capture._screen_capture_worker import _current_monitor, _region_for_monitor
from services.llm import prompts


def test_algorithm_prompt_is_java_even_with_python_config(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(prompts, 'get_config', lambda: SimpleNamespace(language='Python'))
    prompt = prompts.build_system_prompt(mode='algorithm_screen')
    assert '固定为 Java' in prompt
    assert '```java' in prompt
    assert 'public class Main' in prompt
    assert 'class Solution' in prompt
    assert '未识别到算法题' in prompt
    assert 'Python' not in prompt
    assert prompt_mode_for_task('algorithm_screen', True, written_exam=True) == 'algorithm_screen'
    assert _max_tokens_for_prompt('algorithm_screen', SimpleNamespace(max_tokens=4096, assist_answer_style='outline')) == 4096


def test_capture_is_full_resolution_independent_of_crop_settings(monkeypatch):
    grab = Mock(return_value='image')
    monkeypatch.setattr(capture, 'capture_primary_region_data_url', grab)
    assert capture.capture_algorithm_screen_data_url() == 'image'
    grab.assert_called_once_with('full', max_long_edge=3200, follow_cursor=True)


def test_current_monitor_handles_negative_coordinates_and_fallback():
    primary = dict(left=0, top=0, width=1920, height=1080)
    secondary = dict(left=-2560, top=-200, width=2560, height=1440)
    monitors = [{}, primary, secondary]
    assert _current_monitor(monitors, (-100, 0)) == secondary
    assert _current_monitor(monitors, (0, 0)) == primary
    assert _current_monitor(monitors, None) == primary
    assert _region_for_monitor(secondary, 'full') == secondary


def setup_route(monkeypatch):
    import services.llm as llm
    monkeypatch.setattr(llm, 'has_vision_model', lambda: True)
    monkeypatch.setattr(routes, 'pick_model_index', lambda *_: 0)
    grab = Mock(return_value='data:image/png;base64,test')
    monkeypatch.setattr(capture, 'capture_algorithm_screen_data_url', grab)
    submit = Mock(return_value=True)
    monkeypatch.setattr(routes, 'submit_answer_task', submit)
    return grab, submit


def test_route_queues_java_image_without_cancelling_voice(monkeypatch):
    grab, submit = setup_route(monkeypatch)
    cancel = Mock()
    monkeypatch.setattr(routes, 'cancel_answer_work', cancel)
    result = asyncio.run(routes.api_ask_algorithm_screen())
    task = submit.call_args.args[0]
    assert result['qa_id'].startswith('algorithm-')
    assert task[:4] == ('截屏算法题 · Java', 'data:image/png;base64,test', True, 'algorithm_screen')
    assert task[4]['algorithm_qa_id'] == result['qa_id']
    assert task[4]['capture_generation'] == routes._capture_generation()
    grab.assert_called_once()
    cancel.assert_not_called()


def test_route_checks_model_before_capture(monkeypatch):
    import services.llm as llm
    grab, submit = setup_route(monkeypatch)
    monkeypatch.setattr(llm, 'has_vision_model', lambda: False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.api_ask_algorithm_screen())
    assert exc.value.status_code == 400
    grab.assert_not_called()
    submit.assert_not_called()


def test_capture_failure_does_not_submit_a_question(monkeypatch):
    grab, submit = setup_route(monkeypatch)
    grab.side_effect = capture.ScreenCaptureError('缺少屏幕录制权限')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.api_ask_algorithm_screen())
    assert exc.value.status_code == 503
    assert '权限' in exc.value.detail
    submit.assert_not_called()


def test_clearing_while_capture_is_running_does_not_submit_old_image(monkeypatch):
    grab, submit = setup_route(monkeypatch)
    generation = [1]
    monkeypatch.setattr(routes, '_capture_generation', lambda: generation[0])
    def capture_then_clear():
        generation[0] += 1
        return 'data:image/png;base64,old'
    grab.side_effect = capture_then_clear
    with pytest.raises(HTTPException) as exc:
        asyncio.run(routes.api_ask_algorithm_screen())
    assert exc.value.status_code == 409
    submit.assert_not_called()


def test_reset_notifies_queued_algorithm_requests(monkeypatch):
    from api.assist import pipeline
    task = ('截屏算法题 · Java', 'image', True, 'algorithm_screen', {'algorithm_qa_id': 'algorithm-queued'})
    monkeypatch.setattr(pipeline, '_pending', [(task, 0, 0)])
    monkeypatch.setattr(pipeline, '_in_flight_tasks', {})
    monkeypatch.setattr(pipeline, '_commit_buffer', {})
    monkeypatch.setattr(pipeline, '_skipped_commit_seqs', set())
    monkeypatch.setattr(pipeline, '_reset_asr_merge_buffer_locked', Mock())
    monkeypatch.setattr(pipeline, '_reset_pending_asr_group_locked', Mock())
    broadcast = Mock()
    monkeypatch.setattr(pipeline, 'broadcast', broadcast)
    pipeline._reset_answer_state()
    assert pipeline._pending == []
    broadcast.assert_called_once_with({'type': 'answer_cancelled', 'id': 'algorithm-queued'})


def test_mac_permission_preflight_reads_native_bool(monkeypatch):
    import ctypes
    from types import SimpleNamespace
    from services.capture import _screen_capture_worker as worker
    native_check = Mock(return_value=False)
    monkeypatch.setattr(worker.sys, 'platform', 'darwin')
    monkeypatch.setattr(ctypes, 'CDLL', lambda _: SimpleNamespace(CGPreflightScreenCaptureAccess=native_check))
    assert worker._screen_capture_allowed() is False
    native_check.assert_called_once_with()
    assert native_check.restype is ctypes.c_bool


def test_worker_rejects_wallpaper_capture_before_accessing_display(monkeypatch, capsys):
    from services.capture import _screen_capture_worker as worker
    monkeypatch.setattr(worker, '_screen_capture_allowed', lambda: False)
    with pytest.raises(SystemExit) as exc:
        worker.main()
    assert exc.value.code == 4
    output = capsys.readouterr()
    assert output.out == ''
    assert '屏幕录制权限未开启' in output.err
    assert '重新启动助手' in output.err


def test_parent_preserves_permission_error_instead_of_decoding_an_image(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(capture.subprocess, 'run', lambda **_: SimpleNamespace(
        returncode=4, stdout=b'', stderr='屏幕录制权限未开启，请授权 Electron 后重启'.encode(),
    ))
    with pytest.raises(capture.ScreenCaptureError, match='屏幕录制权限未开启，请授权 Electron 后重启'):
        capture.capture_algorithm_screen_data_url()
