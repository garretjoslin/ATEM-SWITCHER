# tests/test_api_config.py
import json
import pytest
from starlette.testclient import TestClient

from app import config as config_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    default = {
        "atem": {"ip": "", "meIndex": 0},
        "audioDevice": {"type": "system", "deviceId": None, "sampleRate": 48000, "channelCount": 2},
        "timecode": {"enabled": False, "channelIndex": None},
        "enabled": False,
        "showLatencyReadout": True,
        "global": {
            "attackMs": 150, "releaseHoldMs": 2500, "minShotHoldMs": 2000, "hysteresisDb": 4,
            "crosstalkWindowMs": 400, "crosstalkBiasCameraId": None,
            "transition": {"type": "cut", "autoDurationFrames": 15}, "timelineFps": 29.97,
            "advanced": {
                "noiseFloorAdaptive": {"enabled": False, "marginDb": 10, "adaptWindowSec": 30},
                "speechBandFilter": {"enabled": False, "lowHz": 300, "highHz": 3400},
                "audioWatchdogMs": 500, "clippingWarnDb": -1,
            },
        },
        "cameras": [{"id": "cam1", "name": "Cam 1", "atemInput": 1, "isoReelName": "Input 1"}],
        "mics": [{"id": "mic1", "name": "Mic 1", "enabled": True, "thresholdDb": -35, "priority": 1, "cameraId": "cam1"}],
    }
    (tmp_path / "default.json").write_text(json.dumps(default))
    monkeypatch.setenv("MIC_CAM_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("MIC_CAM_SKIP_STARTUP", "1")

    # app.main builds its config/state at import time, and Python caches modules.
    # Reload it under this test's env so each test gets its own tmp config dir and
    # a fresh in-memory state (no leakage between tests).
    import importlib
    import app.main as main_module
    importlib.reload(main_module)
    return TestClient(main_module.app)


def test_get_config_returns_loaded_config(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    assert res.json()["enabled"] is False


def test_post_config_persists_and_returns_ok(client):
    cfg = client.get("/api/config").json()
    cfg["enabled"] = True
    res = client.post("/api/config", json=cfg)
    assert res.status_code == 200
    assert client.get("/api/config").json()["enabled"] is True


def test_presets_round_trip(client):
    cfg = client.get("/api/config").json()
    res = client.post("/api/presets/My Preset", json=cfg)
    assert res.status_code == 200
    assert res.json()["name"] == "My_Preset"

    res = client.get("/api/presets")
    assert "My_Preset.json" in res.json()

    res = client.get("/api/presets/My Preset")
    assert res.status_code == 200

    res = client.get("/api/presets/does-not-exist")
    assert res.status_code == 404


def test_engine_enabled_toggle_updates_top_level_config_field(client):
    res = client.post("/api/engine/enabled", json={"enabled": True})
    assert res.status_code == 200
    assert client.get("/api/config").json()["enabled"] is True


def test_status_reports_atem_and_audio(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    body = res.json()
    assert "atem" in body and "connected" in body["atem"]
    assert "audio" in body and "running" in body["audio"]


def test_atem_connect_persists_ip(client):
    res = client.post("/api/atem/connect", json={"ip": "10.0.0.5"})
    assert res.status_code == 200
    assert client.get("/api/config").json()["atem"]["ip"] == "10.0.0.5"


def test_export_edl_without_mark_start_returns_400(client, tmp_path, monkeypatch):
    from app import switch_log
    log_path = tmp_path / "switch_log.jsonl"
    switch_log.append_entry("cam1", 1, 1000, path=log_path)
    monkeypatch.setattr(switch_log, "DEFAULT_LOG_PATH", log_path)

    res = client.get("/api/export/edl", params={"from": 0, "to": 5000})
    assert res.status_code == 400


def test_mark_start_then_export_edl_succeeds(client, tmp_path, monkeypatch):
    from app import switch_log
    log_path = tmp_path / "switch_log.jsonl"
    switch_log.append_entry("cam1", 1, 1000, path=log_path)
    monkeypatch.setattr(switch_log, "DEFAULT_LOG_PATH", log_path)

    res = client.post("/api/timecode/mark-start")
    assert res.status_code == 200

    res = client.get("/api/export/edl", params={"from": 0, "to": 5000})
    assert res.status_code == 200
    assert "TITLE:" in res.text


def test_apply_audio_runs_on_event_loop(client, monkeypatch):
    # Regression guard: /api/config/apply-audio must run on the event loop, not a
    # threadpool worker. As a sync `def` route it dispatched to an AnyIO worker thread
    # where asyncio.get_event_loop()/create_task() raise RuntimeError. Mock the audio
    # source so no hardware is touched; we only assert the event-loop plumbing works.
    import app.main as main_module

    class _FakeSource:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(main_module, "SystemAudioSource", _FakeSource)
    res = client.post("/api/config/apply-audio")
    assert res.status_code == 200
    assert res.json() == {"ok": True}
