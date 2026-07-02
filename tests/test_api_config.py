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
