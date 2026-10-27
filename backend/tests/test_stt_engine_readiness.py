from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.stt.engines import DoubaoSTT, GenericHTTPSTT


def test_doubao_readiness_requires_credentials():
    assert DoubaoSTT().is_configured is False
    assert DoubaoSTT().is_loaded is False

    api_key_engine = DoubaoSTT(api_key="test-key")
    assert api_key_engine.is_configured is True
    assert api_key_engine.is_loaded is True

    legacy_engine = DoubaoSTT(app_id="app-id", access_token="access-token")
    assert legacy_engine.is_configured is True


def test_doubao_empty_resource_id_falls_back_to_seedasr():
    engine = DoubaoSTT(api_key="test-key", resource_id="")
    assert engine.resource_id == "volc.seedasr.sauc.duration"


def test_generic_readiness_requires_all_connection_fields():
    assert GenericHTTPSTT("", "key", "model").is_configured is False
    assert GenericHTTPSTT("https://asr.example.com/v1", "", "model").is_configured is False
    assert GenericHTTPSTT("https://asr.example.com/v1", "key", "").is_configured is False
    assert GenericHTTPSTT("https://asr.example.com/v1", "key", "model").is_configured is True
