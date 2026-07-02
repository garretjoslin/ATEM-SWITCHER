# app/switch_engine.py
import time
from dataclasses import dataclass, field

SILENCE_DB = -100.0


@dataclass
class MicState:
    level: float = SILENCE_DB
    above_since: float | None = None
    below_since: float | None = None
    talking: bool = False
    clipping: bool = False
    noise_floor_samples: list = field(default_factory=list)


class SwitchEngine:
    def __init__(self, atem_controller):
        self.atem_controller = atem_controller
        self.config = None
        self.mic_state: dict[str, MicState] = {}
        self.active_mic_id = None
        self.active_camera_id = None
        self.last_switch_at = float("-inf")  # so the first-ever switch is never min-shot-hold gated
        self.recent_talk_starts = []  # list of (mic_id, at_ms)
        self._stalled = False
        self._tick_listeners = []
        self._switch_listeners = []

    def on_tick(self, callback):
        self._tick_listeners.append(callback)

    def on_switch(self, callback):
        self._switch_listeners.append(callback)

    def set_config(self, config):
        self.config = config
        for mic in config["mics"]:
            if mic["id"] not in self.mic_state:
                self.mic_state[mic["id"]] = MicState(below_since=time.time() * 1000)

    def update_levels(self, levels_by_mic_id, clipping_by_mic_id=None, now_ms=None):
        if now_ms is None:
            now_ms = time.time() * 1000
        self._stalled = False

        if not self.config or not self.config["enabled"]:
            self._update_meter_state_only(levels_by_mic_id, clipping_by_mic_id)
            self._emit_tick()
            return

        g = self.config["global"]
        for mic in self.config["mics"]:
            if mic["id"] not in levels_by_mic_id:
                continue
            state = self.mic_state[mic["id"]]
            state.level = levels_by_mic_id[mic["id"]]
            if clipping_by_mic_id:
                state.clipping = bool(clipping_by_mic_id.get(mic["id"], False))

            is_above = state.level >= mic["thresholdDb"]
            if is_above:
                if state.above_since is None:
                    state.above_since = now_ms
                state.below_since = None
                if not state.talking and now_ms - state.above_since >= g["attackMs"]:
                    state.talking = True
                    self.recent_talk_starts.append((mic["id"], now_ms))
            else:
                if state.below_since is None:
                    state.below_since = now_ms
                state.above_since = None
                if state.talking and now_ms - state.below_since >= g["releaseHoldMs"]:
                    state.talking = False

        self.recent_talk_starts = [
            (mid, at) for (mid, at) in self.recent_talk_starts if now_ms - at <= g["crosstalkWindowMs"]
        ]

        self._decide_and_switch(now_ms)
        self._emit_tick()

    def _update_meter_state_only(self, levels_by_mic_id, clipping_by_mic_id=None):
        if not self.config:
            return
        for mic in self.config["mics"]:
            if mic["id"] not in levels_by_mic_id:
                continue
            state = self.mic_state[mic["id"]]
            state.level = levels_by_mic_id[mic["id"]]
            if clipping_by_mic_id:
                state.clipping = bool(clipping_by_mic_id.get(mic["id"], False))

    def _decide_and_switch(self, now_ms):
        pass  # filled in by Task 4

    def _emit_tick(self):
        snapshot = self._snapshot()
        for cb in self._tick_listeners:
            cb(snapshot)

    def _emit_switch(self, evt):
        for cb in self._switch_listeners:
            cb(evt)

    def _snapshot(self):
        mics = {}
        for mic_id, s in self.mic_state.items():
            mics[mic_id] = {
                "level": round(s.level, 1),
                "talking": s.talking,
                "clipping": s.clipping,
            }
        return {
            "mics": mics,
            "activeMicId": self.active_mic_id,
            "activeCameraId": self.active_camera_id,
            "enabled": self.config["enabled"] if self.config else False,
            "stalled": self._stalled,
        }
