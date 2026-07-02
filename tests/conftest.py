# tests/conftest.py
def make_engine_config(**overrides):
    base = {
        "enabled": True,
        "global": {
            "attackMs": 100,
            "releaseHoldMs": 200,
            "minShotHoldMs": 500,
            "hysteresisDb": 4,
            "crosstalkWindowMs": 300,
            "crosstalkBiasCameraId": "cam3",
            "transition": {"type": "cut", "autoDurationFrames": 15},
            "advanced": {
                "noiseFloorAdaptive": {"enabled": False, "marginDb": 10, "adaptWindowSec": 30},
            },
        },
        "cameras": [
            {"id": "cam1", "name": "Cam 1", "atemInput": 1},
            {"id": "cam2", "name": "Cam 2", "atemInput": 2},
            {"id": "cam3", "name": "Wide", "atemInput": 3},
        ],
        "mics": [
            {"id": "mic1", "name": "Mic 1", "enabled": True, "thresholdDb": -35, "priority": 1, "cameraId": "cam1"},
            {"id": "mic2", "name": "Mic 2", "enabled": True, "thresholdDb": -35, "priority": 1, "cameraId": "cam2"},
        ],
    }
    for key, value in overrides.items():
        base[key] = value
    return base


class FakeAtemController:
    def __init__(self):
        self.calls = []

    def cut_to(self, atem_input, me_index=0):
        self.calls.append(("cut", atem_input))

    def auto_to(self, atem_input, me_index=0):
        self.calls.append(("auto", atem_input))
