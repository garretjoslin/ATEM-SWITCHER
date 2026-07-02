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

    def mark_stalled(self, now_ms=None):
        if now_ms is None:
            now_ms = time.time() * 1000
        self._stalled = True
        self._emit_tick()

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

            threshold = self._effective_threshold_db(mic, state)
            is_above = state.level >= threshold
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

            if not state.talking:
                adv = g.get("advanced", {})
                nf_cfg = adv.get("noiseFloorAdaptive", {"enabled": False})
                if nf_cfg.get("enabled"):
                    state.noise_floor_samples.append((now_ms, state.level))
                    window_ms = nf_cfg.get("adaptWindowSec", 30) * 1000
                    state.noise_floor_samples = [
                        (t, lvl) for (t, lvl) in state.noise_floor_samples if now_ms - t <= window_ms
                    ]

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

    def _effective_threshold_db(self, mic, state):
        adv = self.config["global"].get("advanced", {})
        nf_cfg = adv.get("noiseFloorAdaptive", {"enabled": False})
        if not nf_cfg.get("enabled"):
            return mic["thresholdDb"]
        samples = [lvl for (_, lvl) in state.noise_floor_samples]
        if not samples:
            return mic["thresholdDb"]
        noise_floor = sum(samples) / len(samples)
        return noise_floor + nf_cfg.get("marginDb", 10)

    def _decide_and_switch(self, now_ms):
        eligible = [m for m in self.config["mics"] if m["enabled"] and self.mic_state[m["id"]].talking]
        if not eligible:
            return  # hold last shot, nobody's talking

        g = self.config["global"]
        distinct_recent = {
            mid for (mid, at) in self.recent_talk_starts if now_ms - at <= g["crosstalkWindowMs"]
        }
        if len(distinct_recent) > 1 and g.get("crosstalkBiasCameraId"):
            self._apply_switch(now_ms, None, g["crosstalkBiasCameraId"])
            return

        winner = None
        for m in eligible:
            if winner is None:
                winner = m
                continue
            bp = winner.get("priority", 1)
            mp = m.get("priority", 1)
            if mp != bp:
                winner = m if mp > bp else winner
            else:
                bl = self.mic_state[winner["id"]].level
                ml = self.mic_state[m["id"]].level
                winner = m if ml > bl else winner

        if self.active_mic_id and self.active_mic_id != winner["id"]:
            active_state = self.mic_state.get(self.active_mic_id)
            if active_state and active_state.talking:
                winner_level = self.mic_state[winner["id"]].level
                if winner_level - active_state.level < g["hysteresisDb"]:
                    active_mic_config = next(
                        (m for m in self.config["mics"] if m["id"] == self.active_mic_id), None
                    )
                    target_camera_id = active_mic_config["cameraId"] if active_mic_config else winner["cameraId"]
                    self._apply_switch(now_ms, self.active_mic_id, target_camera_id)
                    return

        self._apply_switch(now_ms, winner["id"], winner["cameraId"])

    def _apply_switch(self, now_ms, mic_id, camera_id):
        if camera_id == self.active_camera_id:
            self.active_mic_id = mic_id
            return
        if now_ms - self.last_switch_at < self.config["global"]["minShotHoldMs"]:
            return

        camera = next((c for c in self.config["cameras"] if c["id"] == camera_id), None)
        if camera is None:
            return

        transition = self.config["global"]["transition"]
        if transition["type"] == "auto":
            self.atem_controller.auto_to(camera["atemInput"])
        else:
            self.atem_controller.cut_to(camera["atemInput"])

        self.active_mic_id = mic_id
        self.active_camera_id = camera_id
        self.last_switch_at = now_ms
        self._emit_switch({
            "micId": mic_id,
            "cameraId": camera_id,
            "atemInput": camera["atemInput"],
            "at": now_ms,
        })

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
