from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.stt import engines as stt_engines


class _FakeWebSocket:
    def __init__(self):
        self.closed = False
        self.sent: list[bytes] = []

    def send_binary(self, data):
        self.sent.append(data)

    def settimeout(self, timeout):
        pass

    def recv(self):
        raise RuntimeError("no more frames")

    def close(self):
        self.closed = True


def test_websocket_sslopt_uses_certifi_bundle():
    sslopt = stt_engines._websocket_sslopt()

    assert sslopt.get("ca_certs"), "应传入 certifi 的 CA bundle"
    # 只是补上 CA 路径，不能顺手把证书校验关掉。
    assert "cert_reqs" not in sslopt
    assert "check_hostname" not in sslopt


def test_websocket_sslopt_empty_when_certifi_missing(monkeypatch):
    monkeypatch.setattr(stt_engines, "certifi", None)
    assert stt_engines._websocket_sslopt() == {}


def test_doubao_transcribe_passes_certifi_sslopt_to_websocket(monkeypatch):
    ws = _FakeWebSocket()
    captured: dict = {}

    def fake_create_connection(url, header=None, timeout=None, sslopt=None):
        captured.update(url=url, header=header, timeout=timeout, sslopt=sslopt)
        return ws

    monkeypatch.setattr(stt_engines.websocket, "create_connection", fake_create_connection)
    engine = stt_engines.DoubaoSTT(api_key="test-api-key")

    text = engine.transcribe(np.full(1600, 1000, dtype=np.int16), sample_rate=16000)

    assert text == ""
    assert captured["sslopt"] == stt_engines._websocket_sslopt()
    assert captured["sslopt"].get("ca_certs")
    assert any(h.lower().startswith("x-api-key:") for h in captured["header"])
    assert ws.closed is True
