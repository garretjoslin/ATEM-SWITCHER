# Mic → Cam ATEM Auto-Switcher (Python) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the working Node.js `mic-cam-switcher` prototype (`reference/mic-cam-switcher-node/`) to a standalone Python/FastAPI app per `docs/superpowers/specs/2026-06-30-mic-cam-atem-switcher-design.md`, preserving exact switch-decision behavior and adding flexible mic/camera counts, a latency readout, adaptive/robustness features, calibration tooling, and optional LTC-timecode-driven EDL export.

**Architecture:** `app/switch_engine.py` is pure logic (no I/O), unit-tested with synthetic timestamps via an injectable `now_ms`. `app/audio/system_audio_source.py` captures multichannel audio with `sounddevice`, computes per-channel dBFS/peak, and hands levels to the engine through an `asyncio.Queue`. `app/atem_controller.py` wraps `PyATEMMax`. FastAPI (`app/main.py`) wires everything together, exposes REST + `/ws`, and serves the static `web/` frontend (ported from `public/`). Hardware-dependent modules (ATEM, audio capture, LTC analog decode) are validated manually via `app/smoke_test.py` and real gear, not unit tests — this matches the reference Node prototype's own testing boundary.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, PyATEMMax, sounddevice, numpy, scipy (bandpass filter), pytest, plain HTML/CSS/JS frontend.

**Key schema correction vs. the Node source:** the design spec's config data model (spec lines 76–107) moves the master switch flag to a **top-level** `config["enabled"]` field, separate from `config["global"]` (which holds only timing/transition knobs). The Node prototype's original `config/default.json` nests `enabled` inside `global` — the spec's illustrated JSON is the approved schema and is authoritative. Every task below reads/writes `config["enabled"]`, never `config["global"]["enabled"]`. Watch for this if cross-referencing the Node source.

---

## Task 1: Project scaffolding

**Files:**
- Create: `app/__init__.py`, `app/audio/__init__.py`, `app/timecode/__init__.py`, `app/export/__init__.py`
- Create: `config/presets/.gitkeep`, `logs/.gitkeep`
- Create: `.gitignore`
- Create: `tests/__init__.py`

- [ ] **Step 1: Initialize git and directory skeleton**

```bash
cd "/Users/joslin/Documents/Claude/Projects/Live ATEM Pod cutting"
git init
mkdir -p app/audio app/timecode app/export web config/presets logs tests
touch app/__init__.py app/audio/__init__.py app/timecode/__init__.py app/export/__init__.py tests/__init__.py
touch config/presets/.gitkeep logs/.gitkeep
```

- [ ] **Step 2: Write `.gitignore`**

```
config/live.json
logs/*.jsonl
!logs/.gitkeep
__pycache__/
*.pyc
.venv/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: scaffold project directories"
```

---

## Task 2: Config layer (`app/config.py`)

**Files:**
- Create: `app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import json
from app import config as config_store


def test_load_config_falls_back_to_default(tmp_path):
    (tmp_path / "default.json").write_text(json.dumps({"enabled": False, "mics": []}))
    loaded = config_store.load_config(base_dir=tmp_path)
    assert loaded == {"enabled": False, "mics": []}


def test_save_then_load_prefers_live(tmp_path):
    (tmp_path / "default.json").write_text(json.dumps({"enabled": False}))
    config_store.save_config({"enabled": True}, base_dir=tmp_path)
    loaded = config_store.load_config(base_dir=tmp_path)
    assert loaded == {"enabled": True}
    assert (tmp_path / "live.json").exists()


def test_preset_round_trip(tmp_path):
    saved_name = config_store.save_preset("Studio A!", {"enabled": True}, base_dir=tmp_path)
    assert saved_name == "Studio_A_"
    assert config_store.list_presets(base_dir=tmp_path) == ["Studio_A_.json"]
    assert config_store.load_preset("Studio A!", base_dir=tmp_path) == {"enabled": True}


def test_load_preset_missing_raises(tmp_path):
    try:
        config_store.load_preset("nope", base_dir=tmp_path)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'` (or `AttributeError`)

- [ ] **Step 3: Write the implementation**

```python
# app/config.py
import json
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FILENAME = "default.json"
LIVE_FILENAME = "live.json"
PRESETS_DIR_NAME = "presets"


def _config_dir(base_dir=None):
    return Path(base_dir) if base_dir else APP_DIR / "config"


def load_config(base_dir=None):
    cdir = _config_dir(base_dir)
    live_path = cdir / LIVE_FILENAME
    default_path = cdir / DEFAULT_FILENAME
    source = live_path if live_path.exists() else default_path
    return json.loads(source.read_text())


def save_config(config, base_dir=None):
    cdir = _config_dir(base_dir)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / LIVE_FILENAME).write_text(json.dumps(config, indent=2))


def _presets_dir(base_dir=None):
    d = _config_dir(base_dir) / PRESETS_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_presets(base_dir=None):
    return sorted(p.name for p in _presets_dir(base_dir).glob("*.json"))


def _safe_name(name):
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


def save_preset(name, config, base_dir=None):
    safe_name = _safe_name(name)
    (_presets_dir(base_dir) / f"{safe_name}.json").write_text(json.dumps(config, indent=2))
    return safe_name


def load_preset(name, base_dir=None):
    safe_name = _safe_name(name)
    path = _presets_dir(base_dir) / f"{safe_name}.json"
    if not path.exists():
        raise FileNotFoundError(safe_name)
    return json.loads(path.read_text())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: config load/save and preset storage"
```

---

## Task 3: Switch engine skeleton (attack/release timing, meter-only mode)

**Files:**
- Create: `app/switch_engine.py`
- Create: `tests/conftest.py`
- Test: `tests/test_switch_engine.py`

- [ ] **Step 1: Write shared test fixtures**

```python
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
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_switch_engine.py
from app.switch_engine import SwitchEngine
from tests.conftest import make_engine_config, FakeAtemController


def test_mic_becomes_talking_after_attack_ms():
    engine = SwitchEngine(FakeAtemController())
    engine.set_config(make_engine_config())

    engine.update_levels({"mic1": -20}, now_ms=1000)
    assert engine.mic_state["mic1"].talking is False

    engine.update_levels({"mic1": -20}, now_ms=1099)
    assert engine.mic_state["mic1"].talking is False

    engine.update_levels({"mic1": -20}, now_ms=1100)
    assert engine.mic_state["mic1"].talking is True


def test_mic_stops_talking_after_release_hold_ms():
    engine = SwitchEngine(FakeAtemController())
    engine.set_config(make_engine_config())
    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=100)
    assert engine.mic_state["mic1"].talking is True

    engine.update_levels({"mic1": -50}, now_ms=150)
    assert engine.mic_state["mic1"].talking is True  # still within releaseHoldMs

    engine.update_levels({"mic1": -50}, now_ms=350)
    assert engine.mic_state["mic1"].talking is False


def test_brief_spike_below_attack_ms_does_not_trigger_talking():
    engine = SwitchEngine(FakeAtemController())
    engine.set_config(make_engine_config())
    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -50}, now_ms=50)  # dropped before attackMs elapsed
    engine.update_levels({"mic1": -50}, now_ms=500)
    assert engine.mic_state["mic1"].talking is False


def test_disabled_engine_updates_meters_but_never_talks():
    engine = SwitchEngine(FakeAtemController())
    engine.set_config(make_engine_config(enabled=False))
    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=200)
    assert engine.mic_state["mic1"].level == -20
    assert engine.mic_state["mic1"].talking is False


def test_tick_listener_receives_snapshot():
    engine = SwitchEngine(FakeAtemController())
    engine.set_config(make_engine_config())
    snapshots = []
    engine.on_tick(snapshots.append)
    engine.update_levels({"mic1": -20}, now_ms=0)
    assert len(snapshots) == 1
    assert snapshots[0]["mics"]["mic1"]["level"] == -20
    assert snapshots[0]["enabled"] is True
    assert snapshots[0]["stalled"] is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_switch_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.switch_engine'`

- [ ] **Step 4: Write the implementation**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_switch_engine.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add app/switch_engine.py tests/conftest.py tests/test_switch_engine.py
git commit -m "feat: switch engine attack/release timing and meter-only mode"
```

---

## Task 4: Winner selection, ATEM apply, min-shot-hold gating

**Files:**
- Modify: `app/switch_engine.py` (`_decide_and_switch` body, new `_apply_switch`)
- Test: `tests/test_switch_engine.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_switch_engine.py`:

```python
def test_highest_priority_mic_wins_and_cuts_atem():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    cfg = make_engine_config()
    cfg["mics"][1]["priority"] = 5
    cfg["global"]["crosstalkBiasCameraId"] = None  # isolate winner selection from crosstalk bias
    engine.set_config(cfg)

    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=0)
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=100)

    assert engine.active_camera_id == "cam2"
    assert atem.calls == [("cut", 2)]


def test_tie_priority_breaks_on_higher_level():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    cfg = make_engine_config()
    cfg["global"]["crosstalkBiasCameraId"] = None  # isolate tie-break from crosstalk bias
    engine.set_config(cfg)

    engine.update_levels({"mic1": -20, "mic2": -10}, now_ms=0)
    engine.update_levels({"mic1": -20, "mic2": -10}, now_ms=100)

    assert engine.active_camera_id == "cam2"


def test_same_camera_updates_active_mic_without_atem_call():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    cfg = make_engine_config()
    cfg["mics"][1]["cameraId"] = "cam1"  # both mics route to cam1
    cfg["global"]["crosstalkBiasCameraId"] = None  # isolate same-camera handling from crosstalk bias
    engine.set_config(cfg)

    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=100)
    assert atem.calls == [("cut", 1)]

    engine.update_levels({"mic1": -20, "mic2": -10}, now_ms=200)  # mic2 rising, not yet talking
    engine.update_levels({"mic1": -20, "mic2": -10}, now_ms=300)  # mic2 now talking and louder
    assert engine.active_mic_id == "mic2"
    assert atem.calls == [("cut", 1)]  # no new ATEM call, same camera


def test_min_shot_hold_suppresses_rapid_camera_changes():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())

    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=100)  # mic1 talks, cuts to cam1
    assert atem.calls == [("cut", 1)]

    # mic2 becomes louder and starts talking well within minShotHoldMs (500ms)
    engine.update_levels({"mic1": -20, "mic2": -5}, now_ms=150)
    engine.update_levels({"mic1": -20, "mic2": -5}, now_ms=250)  # mic2 talking now
    assert atem.calls == [("cut", 1)]  # still gated, cam1 stays up

    engine.update_levels({"mic1": -20, "mic2": -5}, now_ms=650)  # past minShotHoldMs from 100
    assert atem.calls == [("cut", 1), ("cut", 2)]


def test_nobody_talking_holds_last_shot():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())
    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=100)
    assert atem.calls == [("cut", 1)]

    engine.update_levels({"mic1": -80}, now_ms=400)  # goes silent, still in releaseHold
    engine.update_levels({"mic1": -80}, now_ms=500)  # past releaseHoldMs; nobody talking; shot holds
    assert atem.calls == [("cut", 1)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_switch_engine.py -v`
Expected: FAIL — new tests fail because `_decide_and_switch` is a no-op

- [ ] **Step 3: Implement winner selection and ATEM apply**

Replace `_decide_and_switch` in `app/switch_engine.py`:

```python
    def _decide_and_switch(self, now_ms):
        eligible = [m for m in self.config["mics"] if m["enabled"] and self.mic_state[m["id"]].talking]
        if not eligible:
            return  # hold last shot, nobody's talking

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

        self._apply_switch(now_ms, winner["id"], winner["cameraId"])

    def _apply_switch(self, now_ms, mic_id, camera_id):
        # ATEM disconnected: hold the last shot, issue no cuts, and emit nothing
        # (design spec error handling). Emitting here would log/broadcast cuts that
        # never went to air and corrupt a later EDL export. getattr default keeps
        # unit tests (FakeAtemController has no `connected` attr) behaving as connected.
        if not getattr(self.atem_controller, "connected", True):
            return
        if camera_id == self.active_camera_id:
            self.active_mic_id = mic_id
            return
        if now_ms - self.last_switch_at < self.config["global"]["minShotHoldMs"]:
            return

        camera = next((c for c in self.config["cameras"] if c["id"] == camera_id), None)
        if camera is None:
            return

        me_index = self.config.get("atem", {}).get("meIndex", 0)
        transition = self.config["global"]["transition"]
        if transition["type"] == "auto":
            self.atem_controller.auto_to(camera["atemInput"], me_index)
        else:
            self.atem_controller.cut_to(camera["atemInput"], me_index)

        self.active_mic_id = mic_id
        self.active_camera_id = camera_id
        self.last_switch_at = now_ms
        self._emit_switch({
            "micId": mic_id,
            "cameraId": camera_id,
            "atemInput": camera["atemInput"],
            "at": now_ms,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_switch_engine.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add app/switch_engine.py tests/test_switch_engine.py
git commit -m "feat: switch engine winner selection, ATEM apply, min-shot-hold"
```

---

## Task 5: Hysteresis stickiness

**Files:**
- Modify: `app/switch_engine.py` (`_decide_and_switch`)
- Test: `tests/test_switch_engine.py` (append)

- [ ] **Step 1: Write the failing test**

```python
def test_hysteresis_blocks_steal_below_margin():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())  # hysteresisDb = 4

    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=100)  # mic1 active, cam1 up
    engine.update_levels({"mic1": -20}, now_ms=700)  # past minShotHoldMs

    # mic2 becomes talking and is louder, but only by 3dB (< hysteresisDb of 4)
    engine.update_levels({"mic1": -20, "mic2": -17}, now_ms=700)
    engine.update_levels({"mic1": -20, "mic2": -17}, now_ms=800)  # mic2 now talking
    assert engine.active_camera_id == "cam1"  # mic1 keeps the shot

    # mic2 beats mic1 by >= 4dB now
    engine.update_levels({"mic1": -20, "mic2": -15}, now_ms=900)
    assert engine.active_camera_id == "cam2"


def test_hysteresis_does_not_apply_once_active_mic_stops_talking():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())

    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=100)  # mic1 active
    engine.update_levels({"mic1": -20}, now_ms=700)

    # mic1 goes silent long enough to stop talking (releaseHoldMs=200)
    engine.update_levels({"mic1": -80, "mic2": -34}, now_ms=700)
    engine.update_levels({"mic1": -80, "mic2": -34}, now_ms=920)  # mic1 no longer talking
    engine.update_levels({"mic1": -80, "mic2": -34}, now_ms=1020)  # mic2 now talking (attackMs=100)

    # mic2 barely beats mic1's old threshold but mic1 isn't talking, so no hysteresis check applies
    assert engine.active_camera_id == "cam2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_switch_engine.py -v`
Expected: FAIL — winner switches immediately regardless of hysteresis margin

- [ ] **Step 3: Add hysteresis check**

In `_decide_and_switch`, insert before the final `self._apply_switch(now_ms, winner["id"], winner["cameraId"])` call:

```python
        if self.active_mic_id and self.active_mic_id != winner["id"]:
            active_state = self.mic_state.get(self.active_mic_id)
            if active_state and active_state.talking:
                winner_level = self.mic_state[winner["id"]].level
                if winner_level - active_state.level < self.config["global"]["hysteresisDb"]:
                    active_mic_config = next(
                        (m for m in self.config["mics"] if m["id"] == self.active_mic_id), None
                    )
                    target_camera_id = active_mic_config["cameraId"] if active_mic_config else winner["cameraId"]
                    self._apply_switch(now_ms, self.active_mic_id, target_camera_id)
                    return

        self._apply_switch(now_ms, winner["id"], winner["cameraId"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_switch_engine.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add app/switch_engine.py tests/test_switch_engine.py
git commit -m "feat: switch engine hysteresis stickiness"
```

---

## Task 6: Crosstalk bias

**Files:**
- Modify: `app/switch_engine.py` (`_decide_and_switch`)
- Test: `tests/test_switch_engine.py` (append)

- [ ] **Step 1: Write the failing test**

```python
def test_crosstalk_bias_cuts_to_wide_shot():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())  # crosstalkWindowMs=300, biasCameraId=cam3

    # Both mics cross the attack threshold on the same tick, so both talk-starts land
    # within the crosstalk window and the wide-shot cut is the first (un-gated) cut.
    # (If one mic triggered a solo cut first, min-shot-hold would correctly suppress
    # the subsequent crosstalk cut — see test_crosstalk_gated_by_min_shot_hold_...)
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=0)
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=100)  # both start talking at t=100

    assert engine.active_camera_id == "cam3"
    assert atem.calls[-1] == ("cut", 3)


def test_no_crosstalk_when_talk_starts_are_far_apart():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())

    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=100)  # mic1 talking at t=100

    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=900)
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=1000)  # mic2 talking at t=1000, outside window

    assert engine.active_camera_id != "cam3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_switch_engine.py -v`
Expected: FAIL — engine picks an individual mic's camera instead of the bias camera

- [ ] **Step 3: Add crosstalk check**

In `_decide_and_switch`, insert immediately after the `if not eligible: return` guard:

```python
        g = self.config["global"]
        distinct_recent = {
            mid for (mid, at) in self.recent_talk_starts if now_ms - at <= g["crosstalkWindowMs"]
        }
        if len(distinct_recent) > 1 and g.get("crosstalkBiasCameraId"):
            self._apply_switch(now_ms, None, g["crosstalkBiasCameraId"])
            return
```

(`self.config["global"]` is already used later in the method for `hysteresisDb` — replace that inline lookup with the new `g` local variable for consistency.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_switch_engine.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add app/switch_engine.py tests/test_switch_engine.py
git commit -m "feat: switch engine crosstalk bias to wide shot"
```

---

## Task 7: Adaptive noise-floor threshold

**Files:**
- Modify: `app/switch_engine.py` (new `_effective_threshold_db`, `update_levels` loop)
- Test: `tests/test_switch_engine.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
def test_adaptive_threshold_disabled_uses_static_threshold():
    engine = SwitchEngine(FakeAtemController())
    cfg = make_engine_config()
    engine.set_config(cfg)
    # -36 is below the static -35 threshold; mic should not trigger even after long silence sampling
    for t in range(0, 1000, 50):
        engine.update_levels({"mic1": -36}, now_ms=t)
    assert engine.mic_state["mic1"].talking is False


def test_adaptive_threshold_tracks_rising_noise_floor():
    engine = SwitchEngine(FakeAtemController())
    cfg = make_engine_config()
    cfg["global"]["advanced"]["noiseFloorAdaptive"] = {
        "enabled": True, "marginDb": 5, "adaptWindowSec": 1,
    }
    engine.set_config(cfg)

    # HVAC-like noise floor rises to -30dB while mic1 stays silent (never talks: below effective threshold)
    for t in range(0, 900, 50):
        engine.update_levels({"mic1": -30}, now_ms=t)
    assert engine.mic_state["mic1"].talking is False  # -30 is below noiseFloor(-30)+margin(5) once tracked

    # now a real talker at -20dB should trigger against the adapted floor (~-30+5=-25)
    engine.update_levels({"mic1": -20}, now_ms=900)
    engine.update_levels({"mic1": -20}, now_ms=1000)
    assert engine.mic_state["mic1"].talking is True


def test_adaptive_threshold_window_prunes_old_samples():
    engine = SwitchEngine(FakeAtemController())
    cfg = make_engine_config()
    cfg["global"]["advanced"]["noiseFloorAdaptive"] = {
        "enabled": True, "marginDb": 5, "adaptWindowSec": 1,
    }
    engine.set_config(cfg)
    engine.update_levels({"mic1": -30}, now_ms=0)
    # jump far beyond the 1s window; old sample should be pruned so the floor resets
    engine.update_levels({"mic1": -90}, now_ms=5000)
    state = engine.mic_state["mic1"]
    assert all(t >= 4000 for t, _ in state.noise_floor_samples)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_switch_engine.py -v`
Expected: FAIL — engine always uses the static `thresholdDb`

- [ ] **Step 3: Add adaptive threshold logic**

Add a new method to `SwitchEngine` and update the per-mic loop in `update_levels`:

```python
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
```

In `update_levels`, replace `is_above = state.level >= mic["thresholdDb"]` with:

```python
            threshold = self._effective_threshold_db(mic, state)
            is_above = state.level >= threshold
```

Then, **after** the whole `if is_above: ... else: ...` block (so it runs on every tick regardless of branch), append a unified noise-floor sampling step keyed on the mic *not talking*. This matches the spec's "sampled only during periods a mic is not talking" — sampling must happen even while the level sits above the (too-low) static default, otherwise the floor can never learn to rise above ambient. `is_above` for this tick was already computed against the floor from prior ticks, so sampling now does not affect the current tick's decision:

```python
            if not state.talking:
                adv = g.get("advanced", {})
                nf_cfg = adv.get("noiseFloorAdaptive", {"enabled": False})
                if nf_cfg.get("enabled"):
                    state.noise_floor_samples.append((now_ms, state.level))
                    window_ms = nf_cfg.get("adaptWindowSec", 30) * 1000
                    state.noise_floor_samples = [
                        (t, lvl) for (t, lvl) in state.noise_floor_samples if now_ms - t <= window_ms
                    ]
```

Note the indentation: this block is inside the `for mic in self.config["mics"]:` loop but at the same level as the `if is_above:`/`else:` statement, not nested inside `else`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_switch_engine.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add app/switch_engine.py tests/test_switch_engine.py
git commit -m "feat: switch engine adaptive noise-floor threshold"
```

---

## Task 8: Audio-stalled watchdog state and clipping passthrough

**Files:**
- Modify: `app/switch_engine.py` (new `mark_stalled`)
- Test: `tests/test_switch_engine.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
def test_mark_stalled_sets_flag_and_holds_shot():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())
    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=100)
    assert atem.calls == [("cut", 1)]

    snapshots = []
    engine.on_tick(snapshots.append)
    engine.mark_stalled(now_ms=200)

    assert snapshots[-1]["stalled"] is True
    assert atem.calls == [("cut", 1)]  # no new ATEM call while stalled
    assert engine.mic_state["mic1"].talking is True  # frozen, not reset to silence


def test_stalled_flag_clears_on_next_real_update():
    engine = SwitchEngine(FakeAtemController())
    engine.set_config(make_engine_config())
    engine.mark_stalled(now_ms=0)
    snapshots = []
    engine.on_tick(snapshots.append)
    engine.update_levels({"mic1": -80}, now_ms=100)
    assert snapshots[-1]["stalled"] is False


def test_clipping_flag_surfaces_in_snapshot():
    engine = SwitchEngine(FakeAtemController())
    engine.set_config(make_engine_config())
    snapshots = []
    engine.on_tick(snapshots.append)
    engine.update_levels({"mic1": -3}, clipping_by_mic_id={"mic1": True}, now_ms=0)
    assert snapshots[-1]["mics"]["mic1"]["clipping"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_switch_engine.py -v`
Expected: FAIL with `AttributeError: 'SwitchEngine' object has no attribute 'mark_stalled'`

- [ ] **Step 3: Add `mark_stalled`**

```python
    def mark_stalled(self, now_ms=None):
        if now_ms is None:
            now_ms = time.time() * 1000
        self._stalled = True
        self._emit_tick()
```

(Clipping passthrough was already wired in Task 3's `update_levels`/`_update_meter_state_only` and `_snapshot`; this task only adds the watchdog method and its tests.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_switch_engine.py -v`
Expected: PASS (20 tests)

- [ ] **Step 5: Commit**

```bash
git add app/switch_engine.py tests/test_switch_engine.py
git commit -m "feat: switch engine audio-stalled watchdog state"
```

---

## Task 9: Switch engine interaction tests

**Files:**
- Test: `tests/test_switch_engine.py` (append)

- [ ] **Step 1: Write interaction tests covering mechanism combinations**

```python
def test_crosstalk_gated_by_min_shot_hold_then_fires_on_fresh_overlap():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())  # minShotHoldMs=500, crosstalkWindowMs=300, releaseHoldMs=200

    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=100)  # cam1 up, lastSwitchAt=100
    assert atem.calls == [("cut", 1)]

    # mic2 joins within the crosstalk window, but min-shot-hold (500ms) blocks the wide cut
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=150)
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=250)  # crosstalk detected, but gated
    assert atem.calls == [("cut", 1)]
    assert engine.active_camera_id == "cam1"

    # both go quiet long enough to stop talking (releaseHoldMs=200)
    engine.update_levels({"mic1": -80, "mic2": -80}, now_ms=300)
    engine.update_levels({"mic1": -80, "mic2": -80}, now_ms=520)  # both stopped talking

    # both re-start talking together after min-shot-hold has passed -> fresh crosstalk fires
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=600)
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=700)  # both talking again, fresh talk-starts
    assert atem.calls == [("cut", 1), ("cut", 3)]
    assert engine.active_camera_id == "cam3"


def test_hysteresis_blocks_steal_right_as_release_hold_expires():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())  # releaseHoldMs=200, hysteresisDb=4

    engine.update_levels({"mic1": -20}, now_ms=0)
    engine.update_levels({"mic1": -20}, now_ms=100)  # mic1 active
    engine.update_levels({"mic1": -20}, now_ms=700)  # past minShotHoldMs

    # mic1 drops just below threshold but stays within releaseHoldMs of talking=True;
    # mic2 is louder but only by 3dB (< hysteresisDb of 4), so mic1 keeps the shot
    engine.update_levels({"mic1": -36, "mic2": -33}, now_ms=700)
    engine.update_levels({"mic1": -36, "mic2": -33}, now_ms=850)  # still < 200ms since below_since
    assert engine.active_camera_id == "cam1"


def test_adaptive_threshold_enabled_together_with_crosstalk_bias():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    cfg = make_engine_config()
    cfg["global"]["advanced"]["noiseFloorAdaptive"] = {
        "enabled": True, "marginDb": 5, "adaptWindowSec": 1,
    }
    engine.set_config(cfg)

    # settle noise floor near -40 for both mics
    for t in range(0, 500, 50):
        engine.update_levels({"mic1": -40, "mic2": -40}, now_ms=t)

    # both mics jump to -20 (well above -40+5=-35 effective threshold) within the crosstalk window
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=500)
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=600)  # both talking, attackMs=100
    assert engine.active_camera_id == "cam3"  # crosstalk bias wins over either mic's own camera
```

- [ ] **Step 2: Run tests to verify they fail or pass**

Run: `pytest tests/test_switch_engine.py -v`
Expected: These exercise combinations of already-implemented mechanisms — if any fails, fix the interaction bug in `_decide_and_switch`/`update_levels` before proceeding (do not weaken the test).

- [ ] **Step 3: Run the full switch engine suite**

Run: `pytest tests/test_switch_engine.py -v`
Expected: PASS (23 tests)

- [ ] **Step 4: Commit**

```bash
git add tests/test_switch_engine.py
git commit -m "test: switch engine mechanism interaction coverage"
```

---

## Task 10: DSP — RMS/peak dBFS helpers (`app/audio/dsp.py`)

**Files:**
- Create: `app/audio/dsp.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dsp.py
import numpy as np
from app.audio import dsp


def test_rms_dbfs_of_silence_is_floor():
    samples = np.zeros(480, dtype=np.float32)
    assert dsp.rms_dbfs(samples) == -100.0


def test_rms_dbfs_of_full_scale_sine_near_minus_3db():
    t = np.linspace(0, 1, 480, endpoint=False)
    samples = np.sin(2 * np.pi * 100 * t).astype(np.float32)
    db = dsp.rms_dbfs(samples)
    assert -3.5 < db < -2.5  # sine RMS = amplitude / sqrt(2) ~= -3.01dB for full-scale


def test_peak_dbfs_of_full_scale_sine_near_zero():
    t = np.linspace(0, 1, 480, endpoint=False)
    samples = np.sin(2 * np.pi * 100 * t).astype(np.float32)
    db = dsp.peak_dbfs(samples)
    assert -0.5 < db <= 0.0


def test_peak_dbfs_of_silence_is_floor():
    samples = np.zeros(480, dtype=np.float32)
    assert dsp.peak_dbfs(samples) == -100.0


def test_empty_array_returns_floor():
    empty = np.array([], dtype=np.float32)
    assert dsp.rms_dbfs(empty) == -100.0
    assert dsp.peak_dbfs(empty) == -100.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dsp.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.audio.dsp'`

- [ ] **Step 3: Write the implementation**

```python
# app/audio/dsp.py
import numpy as np

SILENCE_DB = -100.0


def rms_dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return SILENCE_DB
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    db = 20 * np.log10(rms) if rms > 0 else SILENCE_DB
    return max(db, SILENCE_DB)


def peak_dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return SILENCE_DB
    peak = float(np.max(np.abs(samples)))
    db = 20 * np.log10(peak) if peak > 0 else SILENCE_DB
    return max(db, SILENCE_DB)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dsp.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/audio/dsp.py tests/test_dsp.py
git commit -m "feat: dsp rms/peak dBFS helpers"
```

---

## Task 11: DSP — speech-band bandpass filter

**Files:**
- Modify: `app/audio/dsp.py`
- Test: `tests/test_dsp.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dsp.py`:

```python
def test_bandpass_filter_attenuates_out_of_band_tone_more_than_in_band():
    sample_rate = 48000
    t = np.linspace(0, 1, sample_rate, endpoint=False)
    low_tone = np.sin(2 * np.pi * 80 * t).astype(np.float32)  # below 300-3400 band
    in_band_tone = np.sin(2 * np.pi * 1000 * t).astype(np.float32)  # inside band

    low_filter = dsp.SpeechBandFilter(low_hz=300, high_hz=3400, sample_rate=sample_rate)
    in_band_filter = dsp.SpeechBandFilter(low_hz=300, high_hz=3400, sample_rate=sample_rate)

    filtered_low = low_filter.process(low_tone)
    filtered_in_band = in_band_filter.process(in_band_tone)

    low_attenuation_db = dsp.rms_dbfs(low_tone) - dsp.rms_dbfs(filtered_low)
    in_band_attenuation_db = dsp.rms_dbfs(in_band_tone) - dsp.rms_dbfs(filtered_in_band)

    assert low_attenuation_db > in_band_attenuation_db + 10  # low tone attenuated much more


def test_bandpass_filter_preserves_state_across_chunks():
    sample_rate = 48000
    t = np.linspace(0, 1, sample_rate, endpoint=False)
    tone = np.sin(2 * np.pi * 1000 * t).astype(np.float32)

    whole_filter = dsp.SpeechBandFilter(low_hz=300, high_hz=3400, sample_rate=sample_rate)
    whole_output = whole_filter.process(tone)

    chunked_filter = dsp.SpeechBandFilter(low_hz=300, high_hz=3400, sample_rate=sample_rate)
    chunk_size = 480
    chunked_output = np.concatenate([
        chunked_filter.process(tone[i:i + chunk_size]) for i in range(0, len(tone), chunk_size)
    ])

    np.testing.assert_allclose(whole_output, chunked_output, atol=1e-5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dsp.py -v`
Expected: FAIL with `AttributeError: module 'app.audio.dsp' has no attribute 'SpeechBandFilter'`

- [ ] **Step 3: Add the filter class**

Append to `app/audio/dsp.py`:

```python
from scipy.signal import butter, sosfilt, sosfilt_zi


class SpeechBandFilter:
    def __init__(self, low_hz, high_hz, sample_rate, order=4):
        nyq = sample_rate / 2
        self.sos = butter(order, [low_hz / nyq, high_hz / nyq], btype="band", output="sos")
        self.zi = sosfilt_zi(self.sos)

    def process(self, samples: np.ndarray) -> np.ndarray:
        filtered, self.zi = sosfilt(self.sos, samples, zi=self.zi)
        return filtered.astype(np.float32)
```

(Move the `from scipy.signal import ...` line to the top of the file alongside the `numpy` import — shown inline here for clarity of what's added.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dsp.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/audio/dsp.py tests/test_dsp.py
git commit -m "feat: dsp speech-band bandpass filter"
```

---

## Task 12: Switch log (`app/switch_log.py`)

**Files:**
- Create: `app/switch_log.py`
- Test: `tests/test_switch_log.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_switch_log.py
from app import switch_log


def test_append_and_read_entries(tmp_path):
    log_path = tmp_path / "switch_log.jsonl"
    switch_log.append_entry("cam1", 1, 1000, timecode=None, path=log_path)
    switch_log.append_entry("cam2", 2, 2000, timecode="00:00:01:00", path=log_path)

    entries = switch_log.read_entries(path=log_path)
    assert len(entries) == 2
    assert entries[0] == {"cameraId": "cam1", "atemInput": 1, "epochMs": 1000, "timecode": None}
    assert entries[1]["timecode"] == "00:00:01:00"


def test_read_entries_filters_by_range(tmp_path):
    log_path = tmp_path / "switch_log.jsonl"
    for i in range(5):
        switch_log.append_entry("cam1", 1, i * 1000, path=log_path)

    entries = switch_log.read_entries(from_ms=1000, to_ms=3000, path=log_path)
    assert [e["epochMs"] for e in entries] == [1000, 2000, 3000]


def test_read_entries_missing_file_returns_empty_list(tmp_path):
    assert switch_log.read_entries(path=tmp_path / "nope.jsonl") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_switch_log.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.switch_log'`

- [ ] **Step 3: Write the implementation**

```python
# app/switch_log.py
import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LOG_PATH = APP_DIR / "logs" / "switch_log.jsonl"


def append_entry(camera_id, atem_input, epoch_ms, timecode=None, path=None):
    p = Path(path) if path else DEFAULT_LOG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {"cameraId": camera_id, "atemInput": atem_input, "epochMs": epoch_ms, "timecode": timecode}
    with p.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_entries(from_ms=None, to_ms=None, path=None):
    p = Path(path) if path else DEFAULT_LOG_PATH
    if not p.exists():
        return []
    entries = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if from_ms is not None and entry["epochMs"] < from_ms:
                continue
            if to_ms is not None and entry["epochMs"] > to_ms:
                continue
            entries.append(entry)
    return entries
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_switch_log.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/switch_log.py tests/test_switch_log.py
git commit -m "feat: append-only switch log persistence"
```

---

## Task 13: Calibration suggestion logic (`app/calibration.py`)

**Files:**
- Create: `app/calibration.py`
- Test: `tests/test_calibration.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_calibration.py
from app.calibration import suggest_threshold_db


def test_suggested_threshold_is_60_percent_from_floor_to_speech():
    assert suggest_threshold_db(noise_floor_db=-60, speech_level_db=-20) == -36.0


def test_suggested_threshold_handles_equal_floor_and_speech():
    assert suggest_threshold_db(noise_floor_db=-40, speech_level_db=-40) == -40.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_calibration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.calibration'`

- [ ] **Step 3: Write the implementation**

```python
# app/calibration.py
def suggest_threshold_db(noise_floor_db: float, speech_level_db: float) -> float:
    return noise_floor_db + 0.6 * (speech_level_db - noise_floor_db)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_calibration.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/calibration.py tests/test_calibration.py
git commit -m "feat: calibration threshold suggestion"
```

---

## Task 14: EDL export — timecode/frame conversion helpers

**Files:**
- Create: `app/export/edl_export.py`
- Test: `tests/test_edl_export.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_edl_export.py
from app.export.edl_export import ms_to_frames, frames_to_timecode, timecode_to_frames


def test_ms_to_frames_at_29_97():
    assert ms_to_frames(1000, 29.97) == 30


def test_frames_to_timecode_basic():
    assert frames_to_timecode(0, 30) == "00:00:00:00"
    assert frames_to_timecode(30, 30) == "00:00:01:00"
    assert frames_to_timecode(30 * 60, 30) == "00:01:00:00"
    assert frames_to_timecode(30 * 3600, 30) == "01:00:00:00"


def test_timecode_to_frames_round_trip():
    fps = 30
    for total_frames in (0, 5, 30, 90, 1801, 108000):
        tc = frames_to_timecode(total_frames, fps)
        assert timecode_to_frames(tc, fps) == total_frames
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_edl_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.export.edl_export'`

- [ ] **Step 3: Write the implementation**

```python
# app/export/edl_export.py
class EdlExportError(Exception):
    pass


def ms_to_frames(ms: float, fps: float) -> int:
    return round(ms / 1000 * fps)


def frames_to_timecode(total_frames: int, fps: float) -> str:
    fps_int = round(fps)
    frames = total_frames % fps_int
    total_seconds = total_frames // fps_int
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def timecode_to_frames(tc: str, fps: float) -> int:
    h, m, s, f = (int(x) for x in tc.split(":"))
    fps_int = round(fps)
    return ((h * 60 + m) * 60 + s) * fps_int + f
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_edl_export.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/export/edl_export.py tests/test_edl_export.py
git commit -m "feat: EDL timecode/frame conversion helpers"
```

---

## Task 15: EDL export — CMX3600 builder (timecode + wall-clock fallback modes)

**Files:**
- Modify: `app/export/edl_export.py`
- Test: `tests/test_edl_export.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_edl_export.py`:

```python
from app.export.edl_export import build_cmx3600_edl, EdlExportError

CAMERAS = {
    "cam1": {"id": "cam1", "name": "Cam 1", "atemInput": 1, "isoReelName": "Input 1"},
    "cam2": {"id": "cam2", "name": "Cam 2", "atemInput": 2, "isoReelName": "Input 2"},
}


def test_wallclock_mode_builds_edl_with_derived_durations():
    entries = [
        {"cameraId": "cam1", "atemInput": 1, "epochMs": 10_000, "timecode": None},
        {"cameraId": "cam2", "atemInput": 2, "epochMs": 12_000, "timecode": None},
    ]
    text = build_cmx3600_edl(
        entries, CAMERAS, fps=30, mode="wallclock", to_ms=13_000, record_start_epoch=10_000,
    )
    assert "TITLE:" in text
    assert "001" in text
    assert "Input 1" in text
    assert "00:00:00:00 00:00:02:00 00:00:00:00 00:00:02:00" in text  # event 1: 2s duration
    assert "00:00:02:00 00:00:03:00 00:00:02:00 00:00:03:00" in text  # event 2: 1s duration to range end


def test_wallclock_mode_without_record_start_raises():
    entries = [{"cameraId": "cam1", "atemInput": 1, "epochMs": 10_000, "timecode": None}]
    try:
        build_cmx3600_edl(entries, CAMERAS, fps=30, mode="wallclock", to_ms=11_000, record_start_epoch=None)
        assert False, "expected EdlExportError"
    except EdlExportError:
        pass


def test_timecode_mode_uses_decoded_timecode_directly():
    entries = [
        {"cameraId": "cam1", "atemInput": 1, "epochMs": 10_000, "timecode": "01:00:00:00"},
        {"cameraId": "cam2", "atemInput": 2, "epochMs": 11_000, "timecode": "01:00:01:00"},
    ]
    text = build_cmx3600_edl(entries, CAMERAS, fps=30, mode="timecode", to_ms=12_000)
    assert "01:00:00:00 01:00:01:00" in text  # source in/out for event 1


def test_timecode_mode_missing_decoded_value_raises():
    entries = [{"cameraId": "cam1", "atemInput": 1, "epochMs": 10_000, "timecode": None}]
    try:
        build_cmx3600_edl(entries, CAMERAS, fps=30, mode="timecode", to_ms=11_000)
        assert False, "expected EdlExportError"
    except EdlExportError:
        pass


def test_empty_entries_returns_header_only():
    text = build_cmx3600_edl([], CAMERAS, fps=30, mode="wallclock", to_ms=1000, record_start_epoch=0)
    assert "TITLE:" in text
    assert "001" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_edl_export.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_cmx3600_edl'`

- [ ] **Step 3: Write the implementation**

Append to `app/export/edl_export.py`:

```python
def build_cmx3600_edl(entries, cameras_by_id, fps, mode, to_ms, record_start_epoch=None,
                       title="mic-cam-switcher export"):
    if mode == "wallclock" and record_start_epoch is None:
        raise EdlExportError("recording start not marked; call POST /api/timecode/mark-start first")

    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    if not entries:
        return "\n".join(lines) + "\n"

    record_frame_cursor = 0
    event_num = 1
    for i, entry in enumerate(entries):
        camera = cameras_by_id.get(entry["cameraId"])
        if camera is None:
            continue

        next_epoch_ms = entries[i + 1]["epochMs"] if i + 1 < len(entries) else to_ms
        duration_ms = max(next_epoch_ms - entry["epochMs"], 0)
        duration_frames = max(ms_to_frames(duration_ms, fps), 1)

        if mode == "timecode":
            if entry.get("timecode") is None:
                raise EdlExportError(f"entry at {entry['epochMs']} has no decoded timecode")
            src_in_frames = timecode_to_frames(entry["timecode"], fps)
        else:
            src_in_frames = ms_to_frames(entry["epochMs"] - record_start_epoch, fps)
        src_out_frames = src_in_frames + duration_frames

        rec_in_frames = record_frame_cursor
        rec_out_frames = rec_in_frames + duration_frames
        record_frame_cursor = rec_out_frames

        reel = camera.get("isoReelName") or camera.get("name") or entry["cameraId"]
        lines.append(
            f"{event_num:03d}  {reel:<8} V     C        "
            f"{frames_to_timecode(src_in_frames, fps)} {frames_to_timecode(src_out_frames, fps)} "
            f"{frames_to_timecode(rec_in_frames, fps)} {frames_to_timecode(rec_out_frames, fps)}"
        )
        lines.append(f"* FROM CLIP NAME: {reel}")
        lines.append("")
        event_num += 1

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_edl_export.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add app/export/edl_export.py tests/test_edl_export.py
git commit -m "feat: CMX3600 EDL builder with timecode and wall-clock fallback modes"
```

---

## Task 16: LTC frame bit-decode (pure logic)

**Files:**
- Create: `app/timecode/ltc_reader.py`
- Test: `tests/test_ltc_reader.py`

**Note:** SMPTE LTC bit-layout/BCD-grouping constants below follow the commonly documented SMPTE 12M wire format. This is unit-tested for internal bit-math correctness only — per the design spec's timecode caveat, verify against a real LTC generator before trusting decoded values against production hardware (see Task 31).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ltc_reader.py
from app.timecode.ltc_reader import decode_ltc_frame_bits, timecode_dict_to_str, SYNC_WORD_BITS


def _bits_for_bcd(value, width):
    return [(value >> i) & 1 for i in range(width)]


def _build_frame(hours, minutes, seconds, frames):
    bits = [0] * 80
    bits[0:4] = _bits_for_bcd(frames % 10, 4)
    bits[8:10] = _bits_for_bcd(frames // 10, 2)
    bits[16:20] = _bits_for_bcd(seconds % 10, 4)
    bits[24:27] = _bits_for_bcd(seconds // 10, 3)
    bits[32:36] = _bits_for_bcd(minutes % 10, 4)
    bits[40:43] = _bits_for_bcd(minutes // 10, 3)
    bits[48:52] = _bits_for_bcd(hours % 10, 4)
    bits[56:58] = _bits_for_bcd(hours // 10, 2)
    bits[64:80] = SYNC_WORD_BITS
    return bits


def test_decode_known_frame():
    bits = _build_frame(hours=1, minutes=2, seconds=3, frames=4)
    tc = decode_ltc_frame_bits(bits)
    assert tc == {"hours": 1, "minutes": 2, "seconds": 3, "frames": 4}
    assert timecode_dict_to_str(tc) == "01:02:03:04"


def test_decode_rejects_wrong_length():
    assert decode_ltc_frame_bits([0] * 79) is None


def test_decode_rejects_bad_sync_word():
    bits = _build_frame(hours=0, minutes=0, seconds=0, frames=0)
    bits[64] = 1  # corrupt the sync word
    assert decode_ltc_frame_bits(bits) is None


def test_decode_max_values():
    bits = _build_frame(hours=23, minutes=59, seconds=59, frames=29)
    tc = decode_ltc_frame_bits(bits)
    assert tc == {"hours": 23, "minutes": 59, "seconds": 59, "frames": 29}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ltc_reader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.timecode.ltc_reader'`

- [ ] **Step 3: Write the bit-decode implementation**

```python
# app/timecode/ltc_reader.py
SYNC_WORD_BITS = [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1]
FRAME_BIT_COUNT = 80


def _bcd_value(bits):
    value = 0
    for i, b in enumerate(bits):
        value += b * (2 ** i)
    return value


def decode_ltc_frame_bits(bits):
    if len(bits) != FRAME_BIT_COUNT:
        return None
    if list(bits[64:80]) != SYNC_WORD_BITS:
        return None

    hours = _bcd_value(bits[56:58]) * 10 + _bcd_value(bits[48:52])
    minutes = _bcd_value(bits[40:43]) * 10 + _bcd_value(bits[32:36])
    seconds = _bcd_value(bits[24:27]) * 10 + _bcd_value(bits[16:20])
    frames = _bcd_value(bits[8:10]) * 10 + _bcd_value(bits[0:4])
    return {"hours": hours, "minutes": minutes, "seconds": seconds, "frames": frames}


def timecode_dict_to_str(tc):
    return f"{tc['hours']:02d}:{tc['minutes']:02d}:{tc['seconds']:02d}:{tc['frames']:02d}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ltc_reader.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/timecode/ltc_reader.py tests/test_ltc_reader.py
git commit -m "feat: SMPTE LTC frame bit-decode"
```

---

## Task 17: LTC analog demodulation wrapper (hardware-dependent)

**Files:**
- Modify: `app/timecode/ltc_reader.py`

This class does biphase-mark zero-crossing demodulation on raw audio samples. Per the design spec's Testing section, this is hardware-dependent and validated manually against a real LTC generator (see Task 31), not with unit tests — the same boundary the Node prototype draws around its own hardware-facing modules.

- [ ] **Step 1: Add `LtcReader`**

Append to `app/timecode/ltc_reader.py`:

```python
class LtcReader:
    """Decodes LTC from a raw audio channel via biphase-mark zero-crossing
    demodulation. A '1' bit has a transition at both cell edges and the cell
    midpoint (two short intervals); a '0' bit has a transition only at cell
    edges (one long interval). Needs tuning/validation against a real LTC
    generator before trusting decoded values in production."""

    def __init__(self, sample_rate, fps=29.97):
        self.sample_rate = sample_rate
        self.fps = fps
        self._prev_sample = 0.0
        self._samples_since_transition = 0
        self._half_bit_samples = sample_rate / (fps * FRAME_BIT_COUNT * 2)
        self._pending_half = False
        self._bit_buffer = []
        self._last_timecode_str = None
        self._has_signal = False

    def process(self, samples) -> None:
        for sample in samples:
            self._samples_since_transition += 1
            crossed = (sample >= 0) != (self._prev_sample >= 0)
            self._prev_sample = sample
            if not crossed:
                continue

            interval = self._samples_since_transition
            self._samples_since_transition = 0

            if interval < self._half_bit_samples * 1.5:
                if self._pending_half:
                    self._bit_buffer.append(1)
                    self._pending_half = False
                    self._maybe_decode_frame()
                else:
                    self._pending_half = True
            else:
                self._pending_half = False
                self._bit_buffer.append(0)
                self._maybe_decode_frame()

    def _maybe_decode_frame(self):
        if len(self._bit_buffer) < FRAME_BIT_COUNT:
            return
        window = self._bit_buffer[-FRAME_BIT_COUNT:]
        tc = decode_ltc_frame_bits(window)
        if tc:
            self._last_timecode_str = timecode_dict_to_str(tc)
            self._has_signal = True
            self._bit_buffer = []

    def current_timecode(self):
        return self._last_timecode_str

    def has_signal(self):
        return self._has_signal
```

- [ ] **Step 2: Commit**

```bash
git add app/timecode/ltc_reader.py
git commit -m "feat: LTC analog demodulation wrapper (needs hardware validation)"
```

---

## Task 18: ATEM controller (`app/atem_controller.py`)

**Files:**
- Create: `app/atem_controller.py`

Hardware-dependent per the design spec's Testing section — validated via `app/smoke_test.py` (Task 21) against real hardware, not unit tests. Uses the PyATEMMax API surface confirmed in the design spec: `switcher.connect(ip)`, `switcher.connected`, `switcher.registerEvent(...)`, `switcher.setPreviewInputVideoSource(meIndex, atemInput)`, `switcher.execCutME(meIndex)`, `switcher.execAutoME(meIndex)`.

- [ ] **Step 1: Write the implementation**

```python
# app/atem_controller.py
import asyncio
import PyATEMMax


class AtemController:
    def __init__(self):
        self.switcher = PyATEMMax.ATEMMax()
        self.connected = False
        self.current_input = None
        self.ip = None
        self.switcher.registerEvent(self.switcher.atem.events.connect, self._on_connect)
        self.switcher.registerEvent(self.switcher.atem.events.disconnect, self._on_disconnect)

    def _on_connect(self, params):
        self.connected = True

    def _on_disconnect(self, params):
        self.connected = False
        self.current_input = None

    def connect(self, ip):
        self.ip = ip
        self.switcher.connect(ip)

    def disconnect(self):
        self.switcher.disconnect()

    def cut_to(self, atem_input, me_index=0):
        if not self.connected:
            return
        if self.current_input == atem_input:
            return
        self.switcher.setPreviewInputVideoSource(me_index, atem_input)
        self.switcher.execCutME(me_index)
        self.current_input = atem_input

    def auto_to(self, atem_input, me_index=0):
        if not self.connected:
            return
        if self.current_input == atem_input:
            return
        self.switcher.setPreviewInputVideoSource(me_index, atem_input)
        self.switcher.execAutoME(me_index)
        self.current_input = atem_input

    def get_status(self):
        return {"connected": self.connected, "ip": self.ip, "currentInput": self.current_input}

    async def maintain_connection(self, poll_interval_sec=2, max_backoff_sec=30):
        """Background reconnect-with-backoff loop; run as an asyncio task from main.py."""
        backoff = poll_interval_sec
        while True:
            await asyncio.sleep(poll_interval_sec)
            if self.ip and not self.connected:
                try:
                    self.switcher.connect(self.ip)
                except Exception:
                    pass
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff_sec)
            else:
                backoff = poll_interval_sec
```

- [ ] **Step 2: Commit**

```bash
git add app/atem_controller.py
git commit -m "feat: ATEM controller with reconnect-with-backoff"
```

---

## Task 19: ATEM Fairlight source stub (`app/audio/atem_fairlight_source.py`)

**Files:**
- Create: `app/audio/atem_fairlight_source.py`

Per the design spec's "Deferred / experimental" section, this is a documented starting point, not a finished/tested part — direct port of the Node prototype's `atemFairlightSource.js`, which carries the same caveat. `PyATEMMax` exposes Fairlight mixer *state* but not consistent live meter ticks across ATEM firmware/models; the reliable path is `system_audio_source.py` instead.

- [ ] **Step 1: Write the implementation**

```python
# app/audio/atem_fairlight_source.py
import asyncio

"""
EXPERIMENTAL. See docs/superpowers/specs/2026-06-30-mic-cam-atem-switcher-design.md,
"Deferred / experimental" section. PyATEMMax exposes Fairlight mixer *state* (gain,
EQ, dynamics) but not consistent live meter ticks across ATEM firmware/models. Kept
as a documented starting point -- confirm the state-tree attribute names below
against your actual switcher's PyATEMMax object before relying on this; the reliable
path is tapping mics into the audio interface and using system_audio_source.py.
"""


class AtemFairlightSource:
    def __init__(self, atem_controller, poll_ms=50):
        self.atem_controller = atem_controller
        self.poll_ms = poll_ms
        self._on_levels_cb = None
        self._on_unavailable_cb = None

    def on_levels(self, callback):
        self._on_levels_cb = callback

    def on_unavailable(self, callback):
        self._on_unavailable_cb = callback

    async def start(self):
        while True:
            self._poll()
            await asyncio.sleep(self.poll_ms / 1000)

    def _poll(self):
        if not self.atem_controller.connected:
            return
        fairlight_state = getattr(self.atem_controller.switcher, "fairlightAudioMixerInput", None)
        if not fairlight_state:
            if self._on_unavailable_cb:
                self._on_unavailable_cb()
            return
        # Unconfirmed against real hardware: PyATEMMax's Fairlight state-tree layout
        # and attribute names need verification (see module docstring above).
        levels = {}
        if self._on_levels_cb:
            self._on_levels_cb(levels)
```

- [ ] **Step 2: Commit**

```bash
git add app/audio/atem_fairlight_source.py
git commit -m "feat: experimental ATEM Fairlight source stub"
```

---

## Task 20: System audio source (`app/audio/system_audio_source.py`)

**Files:**
- Create: `app/audio/system_audio_source.py`

Hardware-dependent per the design spec's Testing section — validated manually with real audio hardware, not unit tests (`app/audio/dsp.py`'s pure math is already covered by Tasks 10–11). Pushes `(levels, clipping)` tuples to an `asyncio.Queue` via `call_soon_threadsafe` since the `sounddevice` callback runs on a PortAudio thread, not the asyncio event loop.

- [ ] **Step 1: Write the implementation**

```python
# app/audio/system_audio_source.py
import sounddevice as sd

from . import dsp

WINDOW_MS = 30


class SystemAudioSource:
    def __init__(self, loop, queue, device_id=None, sample_rate=48000, channel_count=8,
                 speech_band_filter=None, clip_warn_db=-1.0, ltc_reader=None, ltc_channel_index=None):
        self.loop = loop
        self.queue = queue
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.channel_count = channel_count
        self.blocksize = int(sample_rate * WINDOW_MS / 1000)
        self.clip_warn_db = clip_warn_db
        self.ltc_reader = ltc_reader
        self.ltc_channel_index = ltc_channel_index
        self._filters = None
        if speech_band_filter and speech_band_filter.get("enabled"):
            self._filters = [
                dsp.SpeechBandFilter(speech_band_filter["lowHz"], speech_band_filter["highHz"], sample_rate)
                for _ in range(channel_count)
            ]
        self.stream = None

    @staticmethod
    def list_devices():
        devices = sd.query_devices()
        return [
            {
                "id": i,
                "name": d["name"],
                "maxInputChannels": d["max_input_channels"],
                "defaultSampleRate": d["default_samplerate"],
            }
            for i, d in enumerate(devices)
            if d["max_input_channels"] > 0
        ]

    def start(self):
        self.stream = sd.InputStream(
            device=self.device_id,
            channels=self.channel_count,
            samplerate=self.sample_rate,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._on_audio,
        )
        self.stream.start()

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def _on_audio(self, indata, frames, time_info, status):
        levels = []
        clipping = []
        for ch in range(self.channel_count):
            raw = indata[:, ch]
            clipping.append(dsp.peak_dbfs(raw) >= self.clip_warn_db)
            channel_samples = self._filters[ch].process(raw) if self._filters else raw
            levels.append(dsp.rms_dbfs(channel_samples))

        if self.ltc_reader is not None and self.ltc_channel_index is not None:
            if self.ltc_channel_index < self.channel_count:
                self.ltc_reader.process(indata[:, self.ltc_channel_index])

        self.loop.call_soon_threadsafe(self.queue.put_nowait, (levels, clipping))
```

- [ ] **Step 2: Commit**

```bash
git add app/audio/system_audio_source.py
git commit -m "feat: system audio source with sounddevice capture"
```

---

## Task 21: Smoke test script (`app/smoke_test.py`)

**Files:**
- Create: `app/smoke_test.py`

Standalone script per the design spec: connect, list inputs, cut, auto — run against real hardware before trusting the full app. This environment has no network access to ATEM/audio hardware to run it here.

- [ ] **Step 1: Write the implementation**

```python
# app/smoke_test.py
"""
Run this against real ATEM hardware before trusting the full app:

    python -m app.smoke_test <atem-ip> [atem-input-to-cut-to]

Connects, prints firmware/model info and the input list, then issues one cut
and one auto-transition on the given input (defaults to input 2, assumed
harmless -- change if input 2 is live on your switcher).
"""
import sys
import time

from app.atem_controller import AtemController


def main():
    if len(sys.argv) < 2:
        print("usage: python -m app.smoke_test <atem-ip> [atem-input]")
        sys.exit(1)

    ip = sys.argv[1]
    test_input = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    controller = AtemController()
    print(f"connecting to {ip} ...")
    controller.connect(ip)

    deadline = time.time() + 10
    while not controller.connected and time.time() < deadline:
        time.sleep(0.2)

    if not controller.connected:
        print("FAILED to connect within 10s")
        sys.exit(1)

    print("connected.")
    print("switcher info:", controller.switcher.atemModel, controller.switcher.protocolVersion)
    print("inputs:")
    for key, value in controller.switcher.inputProperties.items():
        print(f"  {key}: {getattr(value, 'name', value)}")

    print(f"issuing cut to input {test_input} ...")
    controller.cut_to(test_input)
    time.sleep(1)

    print(f"issuing auto-transition to input {test_input + 1} ...")
    controller.auto_to(test_input + 1)
    time.sleep(1)

    print("smoke test complete.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add app/smoke_test.py
git commit -m "feat: standalone ATEM smoke test script"
```

---

## Task 22: FastAPI app skeleton — config/status/devices/presets routes

**Files:**
- Create: `app/main.py`
- Test: `tests/test_api_config.py`

These routes are pure config plumbing (no hardware), so they're covered with `TestClient` against a temp config dir. Static file mount and hardware wiring come in later tasks.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_api_config.py
import json
import pytest
from fastapi.testclient import TestClient

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Write the implementation**

```python
# app/main.py
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app import config as config_store

APP_DIR = Path(__file__).resolve().parent.parent

app = FastAPI()

_config_base_dir = os.environ.get("MIC_CAM_CONFIG_DIR")

state = {
    "config": config_store.load_config(base_dir=_config_base_dir),
    "audio_source": None,
    "record_start_epoch": None,
    "last_levels_at": None,
    "latest_levels": {},
}


@app.get("/api/config")
def get_config():
    return state["config"]


@app.post("/api/config")
async def post_config(request: Request):
    body = await request.json()
    state["config"] = body
    config_store.save_config(body, base_dir=_config_base_dir)
    return {"ok": True}


@app.get("/api/devices")
def get_devices():
    from app.audio.system_audio_source import SystemAudioSource
    try:
        return SystemAudioSource.list_devices()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/presets")
def get_presets():
    return config_store.list_presets(base_dir=_config_base_dir)


@app.post("/api/presets/{name}")
async def post_preset(name: str, request: Request):
    body = await request.json()
    saved_name = config_store.save_preset(name, body, base_dir=_config_base_dir)
    return {"ok": True, "name": saved_name}


@app.get("/api/presets/{name}")
def get_preset(name: str):
    try:
        return config_store.load_preset(name, base_dir=_config_base_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="preset not found")


@app.post("/api/presets/{name}/load")
def load_preset_route(name: str):
    try:
        preset = config_store.load_preset(name, base_dir=_config_base_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="preset not found")
    state["config"] = preset
    config_store.save_config(preset, base_dir=_config_base_dir)
    return {"ok": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_api_config.py
git commit -m "feat: FastAPI app skeleton with config/preset routes"
```

---

## Task 23: ATEM wiring — connect, engine enabled, status

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_api_config.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_config.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_config.py -v`
Expected: FAIL with `404 Not Found` for the new routes

- [ ] **Step 3: Add ATEM controller instance and routes**

Add to `app/main.py`, after the `state = {...}` block:

```python
from app.atem_controller import AtemController

atem_controller = AtemController()
```

Add these routes:

```python
@app.post("/api/atem/connect")
async def atem_connect(request: Request):
    body = await request.json()
    ip = body.get("ip") or state["config"]["atem"]["ip"]
    state["config"]["atem"]["ip"] = ip
    config_store.save_config(state["config"], base_dir=_config_base_dir)
    atem_controller.connect(ip)
    return {"ok": True}


@app.post("/api/engine/enabled")
async def engine_enabled(request: Request):
    body = await request.json()
    state["config"]["enabled"] = bool(body.get("enabled"))
    config_store.save_config(state["config"], base_dir=_config_base_dir)
    return {"ok": True}


@app.get("/api/status")
def get_status():
    ltc_reader = state.get("ltc_reader")
    return {
        "atem": atem_controller.get_status(),
        "audio": {"running": state["audio_source"] is not None},
        "timecode": {
            "enabled": state["config"]["timecode"]["enabled"],
            "hasSignal": ltc_reader.has_signal() if ltc_reader else False,
        },
    }
```

(`state["ltc_reader"]` doesn't exist until Task 24 initializes it — `state.get("ltc_reader")` returns `None` safely in the meantime, and by the time Task 24/25's code has been appended to the module this reads the real value at request time.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_config.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Add startup wiring, gated for tests**

Add to `app/main.py`:

```python
import asyncio


@app.on_event("startup")
async def on_startup():
    if os.environ.get("MIC_CAM_SKIP_STARTUP"):
        return
    if state["config"]["atem"]["ip"]:
        atem_controller.connect(state["config"]["atem"]["ip"])
    asyncio.create_task(atem_controller.maintain_connection())
```

- [ ] **Step 6: Run the full API test suite**

Run: `pytest tests/test_api_config.py -v`
Expected: PASS (7 tests) — `MIC_CAM_SKIP_STARTUP=1` (set in the `client` fixture) keeps `TestClient` from trying to reach real hardware

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/test_api_config.py
git commit -m "feat: ATEM connect/status/engine-enabled routes"
```

---

## Task 24: Audio wiring — capture start/stop, watchdog, calibration route

**Files:**
- Modify: `app/main.py`

Audio capture itself is hardware-dependent (validated manually per Task 31); this task's routing/state-machine logic (queue consumption, watchdog timing, calibration sampling window) is exercised manually alongside it since it requires a live `asyncio` event loop and real audio callbacks — consistent with the design spec's Testing section boundary for `system_audio_source.py`.

- [ ] **Step 1: Write the implementation**

Add to `app/main.py`:

```python
import time

from app.switch_engine import SwitchEngine
from app.audio.system_audio_source import SystemAudioSource
from app.calibration import suggest_threshold_db
from app.timecode.ltc_reader import LtcReader

switch_engine = SwitchEngine(atem_controller)
switch_engine.set_config(state["config"])

audio_queue = None
state["ltc_reader"] = None


def start_audio():
    global audio_queue
    if state["audio_source"]:
        state["audio_source"].stop()
        state["audio_source"] = None

    loop = asyncio.get_running_loop()  # must run on the event loop (apply-audio route is async)
    audio_queue = asyncio.Queue()
    cfg = state["config"]
    adv = cfg["global"].get("advanced", {})
    speech_filter_cfg = adv.get("speechBandFilter")
    clip_warn_db = adv.get("clippingWarnDb", -1.0)

    ltc_reader = None
    ltc_channel_index = None
    if cfg["timecode"]["enabled"] and cfg["timecode"]["channelIndex"] is not None:
        ltc_reader = LtcReader(sample_rate=cfg["audioDevice"]["sampleRate"], fps=cfg["global"]["timelineFps"])
        ltc_channel_index = cfg["timecode"]["channelIndex"]
    state["ltc_reader"] = ltc_reader

    source = SystemAudioSource(
        loop=loop,
        queue=audio_queue,
        device_id=cfg["audioDevice"]["deviceId"],
        sample_rate=cfg["audioDevice"]["sampleRate"],
        channel_count=cfg["audioDevice"]["channelCount"],
        speech_band_filter=speech_filter_cfg,
        clip_warn_db=clip_warn_db,
        ltc_reader=ltc_reader,
        ltc_channel_index=ltc_channel_index,
    )
    source.start()
    state["audio_source"] = source
    asyncio.create_task(_consume_audio_queue(audio_queue))


async def _consume_audio_queue(my_queue):
    mic_ids = [m["id"] for m in state["config"]["mics"]]
    while state["audio_source"] is not None and audio_queue is my_queue:
        levels, clipping = await my_queue.get()
        state["last_levels_at"] = time.time() * 1000
        levels_by_mic_id = {}
        clipping_by_mic_id = {}
        for idx, mic_id in enumerate(mic_ids):
            if idx < len(levels):
                levels_by_mic_id[mic_id] = levels[idx]
                clipping_by_mic_id[mic_id] = clipping[idx]
        state["latest_levels"] = levels_by_mic_id
        switch_engine.update_levels(levels_by_mic_id, clipping_by_mic_id)


async def _watchdog_loop():
    while True:
        await asyncio.sleep(0.1)
        watchdog_ms = state["config"]["global"].get("advanced", {}).get("audioWatchdogMs", 500)
        last = state["last_levels_at"]
        if last is not None and (time.time() * 1000 - last) > watchdog_ms and state["audio_source"] is not None:
            switch_engine.mark_stalled()


@app.post("/api/config/apply-audio")
async def apply_audio():  # async so start_audio() runs on the loop, not a threadpool worker
    try:
        start_audio()
    except Exception as e:
        # Audio device open failure (e.g. configured channelCount exceeds the device's
        # channels) is reported to the caller, not fatal (design spec error-handling).
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
    return {"ok": True}


@app.post("/api/calibrate/{mic_id}")
async def calibrate(mic_id: str):
    mic = next((m for m in state["config"]["mics"] if m["id"] == mic_id), None)
    if mic is None:
        raise HTTPException(status_code=404, detail="mic not found")

    async def sample_for(seconds):
        samples = []
        deadline = time.time() + seconds
        while time.time() < deadline:
            level = state["latest_levels"].get(mic_id)
            if level is not None:
                samples.append(level)
            await asyncio.sleep(0.03)
        return samples

    floor_samples = await sample_for(3.0)
    speech_samples = await sample_for(3.0)

    noise_floor_db = sum(floor_samples) / len(floor_samples) if floor_samples else -100.0
    speech_level_db = max(speech_samples) if speech_samples else -100.0
    suggested = suggest_threshold_db(noise_floor_db, speech_level_db)
    return {
        "noiseFloorDb": round(noise_floor_db, 1),
        "speechLevelDb": round(speech_level_db, 1),
        "suggestedThresholdDb": round(suggested, 1),
    }
```

Update the `on_startup` handler added in Task 23 to also start audio and the watchdog:

```python
@app.on_event("startup")
async def on_startup():
    if os.environ.get("MIC_CAM_SKIP_STARTUP"):
        return
    if state["config"]["atem"]["ip"]:
        atem_controller.connect(state["config"]["atem"]["ip"])
    asyncio.create_task(atem_controller.maintain_connection())
    try:
        start_audio()
    except Exception as e:
        # Never let an audio-open failure abort ASGI startup (would kill the whole
        # server). Log and continue; operator picks a valid device via the UI.
        print(f"[startup] audio capture failed to start: {e}")
    asyncio.create_task(_watchdog_loop())
```

- [ ] **Step 2: Run the full API test suite (unaffected by this task)**

Run: `pytest tests/test_api_config.py -v`
Expected: PASS (7 tests) — `MIC_CAM_SKIP_STARTUP=1` means `start_audio()`/watchdog never run under `TestClient`

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: audio capture wiring, watchdog, calibration endpoint"
```

---

## Task 25: Switch engine wiring — /ws broadcast, switch log, timecode, EDL export

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_api_config.py` (append)

- [ ] **Step 1: Write the failing test for the export route (no hardware needed)**

Append to `tests/test_api_config.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_config.py -v`
Expected: FAIL with `404 Not Found` for `/api/export/edl` and `/api/timecode/mark-start`

- [ ] **Step 3: Wire the switch engine's callbacks, /ws, and the export routes**

Add to `app/main.py`:

```python
import json

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import switch_log
from app.export.edl_export import build_cmx3600_edl, EdlExportError

ws_clients: set[WebSocket] = set()


async def broadcast(msg_type, payload):
    msg = json.dumps({"type": msg_type, "payload": payload})
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


def _on_tick(snapshot):
    asyncio.create_task(broadcast("tick", snapshot))


def _on_switch(evt):
    asyncio.create_task(broadcast("switch", evt))
    timecode = None
    if state["config"]["timecode"]["enabled"] and state.get("ltc_reader"):
        timecode = state["ltc_reader"].current_timecode()
    switch_log.append_entry(evt["cameraId"], evt["atemInput"], int(evt["at"]), timecode=timecode)


switch_engine.on_tick(_on_tick)
switch_engine.on_switch(_on_switch)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_clients.discard(websocket)


@app.post("/api/timecode/mark-start")
def mark_start():
    state["record_start_epoch"] = int(time.time() * 1000)
    return {"ok": True, "recordStartEpoch": state["record_start_epoch"]}


@app.get("/api/export/edl")
def export_edl(**params):
    from_ms = int(params.get("from", 0))
    to_ms = int(params["to"])
    entries = switch_log.read_entries(from_ms=from_ms, to_ms=to_ms)
    cameras_by_id = {c["id"]: c for c in state["config"]["cameras"]}
    fps = state["config"]["global"]["timelineFps"]
    mode = "timecode" if state["config"]["timecode"]["enabled"] else "wallclock"
    try:
        edl_text = build_cmx3600_edl(
            entries, cameras_by_id, fps, mode, to_ms=to_ms, record_start_epoch=state["record_start_epoch"],
        )
    except EdlExportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PlainTextResponse(
        edl_text, media_type="application/x-cmx3600",
        headers={"Content-Disposition": "attachment; filename=export.edl"},
    )
```

Replace the `export_edl` signature above with an explicit `Query`-based one (FastAPI doesn't support `**params` for query args) — use this instead:

```python
from fastapi import Query


@app.get("/api/export/edl")
def export_edl(from_ms: int = Query(..., alias="from"), to_ms: int = Query(..., alias="to")):
    entries = switch_log.read_entries(from_ms=from_ms, to_ms=to_ms)
    cameras_by_id = {c["id"]: c for c in state["config"]["cameras"]}
    fps = state["config"]["global"]["timelineFps"]
    mode = "timecode" if state["config"]["timecode"]["enabled"] else "wallclock"
    try:
        edl_text = build_cmx3600_edl(
            entries, cameras_by_id, fps, mode, to_ms=to_ms, record_start_epoch=state["record_start_epoch"],
        )
    except EdlExportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PlainTextResponse(
        edl_text, media_type="application/x-cmx3600",
        headers={"Content-Disposition": "attachment; filename=export.edl"},
    )
```

(Delete the earlier `**params` version — it was shown first only to explain the change; the file should contain a single `export_edl` route using `Query`.)

Finally, mount the static frontend **last**, after every `@app.get`/`@app.post`/`@app.websocket` route so it doesn't shadow the API:

```python
app.mount("/", StaticFiles(directory=str(APP_DIR / "web"), html=True), name="web")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_config.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests across every module written so far)

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_api_config.py
git commit -m "feat: /ws broadcast, switch log integration, timecode mark-start, EDL export route"
```

---

## Task 26: Switch engine — "ms since trigger" latency on switch events

**Files:**
- Modify: `app/switch_engine.py` (`_apply_switch`)
- Test: `tests/test_switch_engine.py` (append)

Supports the spec's UI requirement: "Switch-event log entries show a 'ms since trigger' latency value next to each cut." Latency = time from when the winning mic's level first crossed its threshold (`above_since`) to the moment the ATEM was actually cut.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_switch_engine.py`:

```python
def test_switch_event_includes_latency_since_trigger():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())
    events = []
    engine.on_switch(events.append)

    engine.update_levels({"mic1": -20}, now_ms=1000)  # above_since = 1000
    engine.update_levels({"mic1": -20}, now_ms=1100)  # talking=True, cuts at 1100

    assert len(events) == 1
    assert events[0]["latencyMs"] == 100


def test_crosstalk_switch_event_has_no_latency():
    atem = FakeAtemController()
    engine = SwitchEngine(atem)
    engine.set_config(make_engine_config())
    events = []
    engine.on_switch(events.append)

    # both mics cross the attack threshold together -> the crosstalk cut is the first,
    # un-gated cut (mic_id=None), so its event carries no per-mic trigger latency
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=0)
    engine.update_levels({"mic1": -20, "mic2": -20}, now_ms=100)  # crosstalk fires (cam3, mic_id=None)

    crosstalk_events = [e for e in events if e["cameraId"] == "cam3"]
    assert crosstalk_events[0]["latencyMs"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_switch_engine.py -v`
Expected: FAIL with `KeyError: 'latencyMs'`

- [ ] **Step 3: Add latency calculation to `_apply_switch`**

Replace the tail of `_apply_switch` in `app/switch_engine.py` (from the `me_index = ...` line onward) with:

```python
        me_index = self.config.get("atem", {}).get("meIndex", 0)
        transition = self.config["global"]["transition"]
        if transition["type"] == "auto":
            self.atem_controller.auto_to(camera["atemInput"], me_index)
        else:
            self.atem_controller.cut_to(camera["atemInput"], me_index)

        latency_ms = None
        if mic_id is not None:
            trigger_state = self.mic_state.get(mic_id)
            if trigger_state and trigger_state.above_since is not None:
                latency_ms = now_ms - trigger_state.above_since

        self.active_mic_id = mic_id
        self.active_camera_id = camera_id
        self.last_switch_at = now_ms
        self._emit_switch({
            "micId": mic_id,
            "cameraId": camera_id,
            "atemInput": camera["atemInput"],
            "at": now_ms,
            "latencyMs": latency_ms,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_switch_engine.py -v`
Expected: PASS (25 tests)

- [ ] **Step 5: Commit**

```bash
git add app/switch_engine.py tests/test_switch_engine.py
git commit -m "feat: switch engine ms-since-trigger latency on cut events"
```

---

## Task 27: Frontend scaffold — `web/index.html` + `web/style.css`

**Files:**
- Create: `web/index.html`
- Create: `web/style.css`

Ported from `reference/mic-cam-switcher-node/public/index.html` and `style.css`, with: no channel-index field (position-based per the config schema change), no ATEM-direct mic source selector (the Python config schema has no `sourceType` field — Fairlight-direct stays an experimental stub, not user-facing), add/remove mic & camera buttons, per-mic Calibrate button + CLIP/STALLED badges, latency-readout toggle, closed-by-default Advanced disclosure, and the Export Timeline panel.

- [ ] **Step 1: Write `web/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>Mic → Cam ATEM Switcher</title>
<link rel="stylesheet" href="style.css" />
</head>
<body>
<header>
  <h1>Mic → Cam ATEM Switcher</h1>
  <div class="header-controls">
    <label>ATEM IP <input id="atemIp" type="text" /></label>
    <button id="atemConnectBtn">Connect</button>
    <span id="atemStatus" class="status-dot off" title="ATEM connection"></span>

    <label class="master-toggle">
      <input id="masterEnable" type="checkbox" />
      Auto-Switch Active
    </label>
  </div>
</header>

<section id="statusBar">
  <div>Active Mic: <strong id="activeMic">—</strong></div>
  <div>Active Camera: <strong id="activeCamera">—</strong></div>
  <div id="stalledIndicator" class="warn-badge hidden">AUDIO STALLED</div>
  <div id="log"></div>
</section>

<section id="audioDeviceSection" class="panel">
  <h2>Audio Device</h2>
  <div class="row">
    <label>Input device
      <select id="deviceSelect"></select>
    </label>
    <label>Channel count <input id="channelCount" type="number" min="1" max="32" /></label>
    <label>Sample rate <input id="sampleRate" type="number" step="1" /></label>
    <button id="applyAudioBtn">Apply &amp; Restart Capture</button>
  </div>
</section>

<section id="micsSection" class="panel">
  <h2>Mics</h2>
  <div id="micStrips"></div>
  <div class="row">
    <button id="addMicBtn">Add Mic</button>
    <button id="removeMicBtn">Remove Last Mic</button>
  </div>
</section>

<section id="camerasSection" class="panel">
  <h2>Cameras</h2>
  <div id="cameraStrips"></div>
  <div class="row">
    <button id="addCameraBtn">Add Camera</button>
    <button id="removeCameraBtn">Remove Last Camera</button>
  </div>
</section>

<section id="globalSection" class="panel">
  <h2>Global Timing &amp; Behavior</h2>
  <div class="row">
    <label>Attack (ms) <input id="attackMs" type="number" /></label>
    <label>Release hold (ms) <input id="releaseHoldMs" type="number" /></label>
    <label>Min shot hold (ms) <input id="minShotHoldMs" type="number" /></label>
    <label>Hysteresis (dB) <input id="hysteresisDb" type="number" /></label>
  </div>
  <div class="row">
    <label>Transition
      <select id="transitionType">
        <option value="cut">Cut</option>
        <option value="auto">Auto</option>
      </select>
    </label>
    <label>Auto duration (frames) <input id="autoDurationFrames" type="number" /></label>
    <label>Crosstalk window (ms) <input id="crosstalkWindowMs" type="number" /></label>
    <label>Crosstalk bias camera
      <select id="crosstalkBiasCameraId"></select>
    </label>
  </div>
  <div class="row">
    <label><input id="showLatencyReadout" type="checkbox" /> Show cut latency in log</label>
  </div>

  <details id="advancedDisclosure">
    <summary>Advanced</summary>
    <div class="row">
      <label><input id="noiseFloorAdaptiveEnabled" type="checkbox" /> Adaptive noise-floor threshold</label>
      <label>Margin (dB) <input id="noiseFloorMarginDb" type="number" /></label>
      <label>Adapt window (s) <input id="noiseFloorAdaptWindowSec" type="number" /></label>
    </div>
    <div class="row">
      <label><input id="speechBandFilterEnabled" type="checkbox" /> Speech-band pre-filter</label>
      <label>Low Hz <input id="speechBandLowHz" type="number" /></label>
      <label>High Hz <input id="speechBandHighHz" type="number" /></label>
    </div>
    <div class="row">
      <label>Audio watchdog (ms) <input id="audioWatchdogMs" type="number" /></label>
      <label>Clip warning (dBFS) <input id="clippingWarnDb" type="number" /></label>
    </div>
  </details>
</section>

<section id="exportSection" class="panel">
  <h2>Export Timeline</h2>
  <div class="row">
    <label>From <input id="exportFrom" type="datetime-local" /></label>
    <label>To <input id="exportTo" type="datetime-local" /></label>
    <button id="exportEdlBtn">Export Timeline (.edl)</button>
    <button id="markStartBtn">Mark Recording Start</button>
  </div>
  <div id="timecodeStatus" class="row"></div>
</section>

<section id="presetsSection" class="panel">
  <h2>Presets</h2>
  <div class="row">
    <input id="presetName" type="text" placeholder="preset name" />
    <button id="savePresetBtn">Save Current as Preset</button>
    <select id="presetList"></select>
    <button id="loadPresetBtn">Load Selected</button>
  </div>
</section>

<footer>
  <button id="saveConfigBtn">Save Config</button>
</footer>

<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `web/style.css`**

Port `reference/mic-cam-switcher-node/public/style.css` verbatim, then apply these changes: widen `.mic-strip` to 7 columns (drop the old channel-index column, add a calibrate-button column and a badges column), and add styles for the new badges/disclosure/warning elements.

```css
:root {
  --bg: #14161a;
  --panel: #1d2026;
  --border: #2c3038;
  --text: #e8e8ec;
  --dim: #9096a3;
  --accent: #4da3ff;
  --green: #35d07f;
  --yellow: #f2c94c;
  --red: #eb5757;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  padding: 0 0 60px;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 10px;
}

h1 { font-size: 18px; margin: 0; }
h2 { font-size: 15px; margin: 0 0 12px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.05em; }

.header-controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.header-controls label { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.header-controls input[type=text] { width: 130px; }

input, select, button {
  background: #262a32;
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}

button {
  cursor: pointer;
  background: #2a3f57;
}
button:hover { background: #35507a; }

.status-dot {
  width: 12px; height: 12px; border-radius: 50%;
  display: inline-block;
}
.status-dot.off { background: var(--red); }
.status-dot.on { background: var(--green); }

.master-toggle { font-weight: 600; }

#statusBar {
  display: flex;
  align-items: center;
  gap: 30px;
  padding: 10px 20px;
  background: #191c22;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
}

.panel {
  margin: 20px;
  padding: 16px 20px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
}

.row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 8px;
}
.row label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--dim); }

#micStrips { display: flex; flex-direction: column; gap: 10px; }

.mic-strip {
  display: grid;
  grid-template-columns: 120px 70px 1fr 90px 140px 90px 110px;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: #20242c;
  border-radius: 8px;
  border: 1px solid var(--border);
}
.mic-strip.talking { border-color: var(--green); box-shadow: 0 0 0 1px var(--green) inset; }
.mic-strip input[type=text] { width: 100%; }
.mic-strip input[type=number] { width: 70px; }

.meter-wrap {
  position: relative;
  height: 20px;
  background: #0e1013;
  border-radius: 4px;
  overflow: hidden;
}
.meter-fill {
  position: absolute; left: 0; top: 0; bottom: 0;
  width: 0%;
  background: linear-gradient(90deg, var(--green), var(--yellow) 80%, var(--red));
  transition: width 60ms linear;
}
.meter-threshold {
  position: absolute; top: 0; bottom: 0;
  width: 2px;
  background: #fff;
}

.mic-badges { display: flex; gap: 6px; }
.badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #333;
  color: var(--dim);
  visibility: hidden;
}
.badge.active { visibility: visible; }
.badge.clip.active { background: var(--red); color: #fff; }
.badge.stalled.active { background: var(--yellow); color: #14161a; }

.warn-badge {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--yellow);
  color: #14161a;
  font-weight: 600;
}
.hidden { display: none; }

#advancedDisclosure { margin-top: 12px; }
#advancedDisclosure summary {
  cursor: pointer;
  color: var(--dim);
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
#advancedDisclosure[open] summary { margin-bottom: 10px; }

#cameraStrips { display: flex; flex-direction: column; gap: 8px; }
.camera-strip {
  display: grid;
  grid-template-columns: 160px 100px 140px;
  gap: 10px;
  align-items: center;
  padding: 6px 10px;
  background: #20242c;
  border-radius: 8px;
  border: 1px solid var(--border);
}
.camera-strip.active { border-color: var(--accent); }

footer {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  padding: 12px 20px;
  background: var(--panel);
  border-top: 1px solid var(--border);
  display: flex; justify-content: flex-end;
}

#log { font-size: 12px; color: var(--dim); }
```

- [ ] **Step 3: Commit**

```bash
git add web/index.html web/style.css
git commit -m "feat: port frontend HTML/CSS scaffold from Node prototype"
```

---

## Task 28: Frontend logic — `web/app.js`

**Files:**
- Create: `web/app.js`

Ported behavior from `reference/mic-cam-switcher-node/public/app.js`, adapted to the new config schema (top-level `enabled`, no per-mic `channelIndex`/`sourceType`), add/remove mic & camera, calibrate flow, CLIP/STALLED badges, latency readout, Advanced knobs, and Export Timeline. **Security:** unlike the Node prototype (which used `innerHTML` string interpolation), this builds every strip with `createElement` + `textContent`/`value`, so operator-entered names can never inject markup. The WebSocket connects to the FastAPI `/ws` path.

- [ ] **Step 1: Write `web/app.js`**

```javascript
let config = null;
let ws = null;

const dbToPercent = (db) => {
  const clamped = Math.max(-60, Math.min(0, db));
  return ((clamped + 60) / 60) * 100;
};

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

// Small DOM helpers — never interpolate user data into markup strings.
function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => {
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k in node) node[k] = v;
    else node.setAttribute(k, v);
  });
  children.forEach((c) => node.appendChild(c));
  return node;
}

function cameraSelect(className, selectedId, includeNone = false) {
  const sel = el('select', { class: className });
  if (includeNone) sel.appendChild(el('option', { value: '', text: '(none)' }));
  config.cameras.forEach((c) => {
    const opt = el('option', { value: c.id, text: c.name });
    if (c.id === selectedId) opt.selected = true;
    sel.appendChild(opt);
  });
  return sel;
}

async function loadAll() {
  config = await fetchJSON('/api/config');
  const devices = await fetchJSON('/api/devices').catch(() => []);
  renderHeader();
  renderAudioDevice(devices);
  renderMics();
  renderCameras();
  renderGlobal();
  renderAdvanced();
  await refreshPresets();
  connectWS();
  refreshStatus();
  setInterval(refreshStatus, 4000);
}

function renderHeader() {
  document.getElementById('atemIp').value = config.atem.ip || '';
  document.getElementById('masterEnable').checked = !!config.enabled;
}

function renderAudioDevice(devices) {
  const sel = document.getElementById('deviceSelect');
  sel.replaceChildren(el('option', { value: '', text: 'Default input' }));
  devices.forEach((d) => {
    const opt = el('option', { value: String(d.id), text: `${d.name} (${d.maxInputChannels} ch)` });
    if (config.audioDevice.deviceId === d.id) opt.selected = true;
    sel.appendChild(opt);
  });
  document.getElementById('channelCount').value = config.audioDevice.channelCount;
  document.getElementById('sampleRate').value = config.audioDevice.sampleRate;
}

function renderMics() {
  const container = document.getElementById('micStrips');
  container.replaceChildren();
  config.mics.forEach((mic) => {
    const nameInput = el('input', { type: 'text', class: 'mic-name', value: mic.name });
    nameInput.addEventListener('input', (e) => (mic.name = e.target.value));

    const enabledInput = el('input', { type: 'checkbox', class: 'mic-enabled', checked: mic.enabled });
    enabledInput.addEventListener('change', (e) => (mic.enabled = e.target.checked));
    const enabledLabel = el('label', {}, [enabledInput, document.createTextNode(' on')]);
    enabledLabel.setAttribute('style', 'font-size:11px;color:#9096a3;display:flex;gap:4px;align-items:center;');

    const meterFill = el('div', { class: 'meter-fill' });
    meterFill.style.width = '0%';
    const meterThreshold = el('div', { class: 'meter-threshold' });
    meterThreshold.style.left = `${dbToPercent(mic.thresholdDb)}%`;
    const meterWrap = el('div', { class: 'meter-wrap' }, [meterFill, meterThreshold]);

    const thresholdInput = el('input', { type: 'number', class: 'mic-threshold', value: mic.thresholdDb, step: '1', title: 'Threshold dB' });
    thresholdInput.addEventListener('input', (e) => {
      mic.thresholdDb = parseFloat(e.target.value);
      meterThreshold.style.left = `${dbToPercent(mic.thresholdDb)}%`;
    });

    const camSel = cameraSelect('mic-camera', mic.cameraId);
    camSel.addEventListener('change', (e) => (mic.cameraId = e.target.value));

    const calibrateBtn = el('button', { class: 'mic-calibrate', text: 'Calibrate' });

    const clipBadge = el('span', { class: 'badge clip', text: 'CLIP' });
    const stalledBadge = el('span', { class: 'badge stalled', text: 'STALL' });
    const badges = el('div', { class: 'mic-badges' }, [clipBadge, stalledBadge]);

    const strip = el('div', { class: 'mic-strip' }, [
      nameInput, enabledLabel, meterWrap, thresholdInput, camSel, calibrateBtn, badges,
    ]);
    strip.dataset.micId = mic.id;
    calibrateBtn.addEventListener('click', () => calibrateMic(mic, strip));
    container.appendChild(strip);
  });
}

function renderCameras() {
  const container = document.getElementById('cameraStrips');
  container.replaceChildren();
  config.cameras.forEach((cam) => {
    const nameInput = el('input', { type: 'text', class: 'cam-name', value: cam.name });
    nameInput.addEventListener('input', (e) => {
      cam.name = e.target.value;
      renderMics();
      renderGlobal();
    });

    const inputNum = el('input', { type: 'number', class: 'cam-input', value: cam.atemInput, min: '1' });
    inputNum.addEventListener('input', (e) => (cam.atemInput = parseInt(e.target.value, 10)));
    const inputLabel = el('label', {}, [document.createTextNode('ATEM input '), inputNum]);
    inputLabel.setAttribute('style', 'font-size:11px;color:#9096a3;');

    const reelInput = el('input', { type: 'text', class: 'cam-reel', value: cam.isoReelName || '' });
    reelInput.addEventListener('input', (e) => (cam.isoReelName = e.target.value));
    const reelLabel = el('label', {}, [document.createTextNode('ISO reel '), reelInput]);
    reelLabel.setAttribute('style', 'font-size:11px;color:#9096a3;');

    const strip = el('div', { class: 'camera-strip' }, [nameInput, inputLabel, reelLabel]);
    strip.dataset.cameraId = cam.id;
    container.appendChild(strip);
  });
}

function renderGlobal() {
  const g = config.global;
  document.getElementById('attackMs').value = g.attackMs;
  document.getElementById('releaseHoldMs').value = g.releaseHoldMs;
  document.getElementById('minShotHoldMs').value = g.minShotHoldMs;
  document.getElementById('hysteresisDb').value = g.hysteresisDb;
  document.getElementById('transitionType').value = g.transition.type;
  document.getElementById('autoDurationFrames').value = g.transition.autoDurationFrames;
  document.getElementById('crosstalkWindowMs').value = g.crosstalkWindowMs;
  document.getElementById('showLatencyReadout').checked = !!config.showLatencyReadout;

  const biasWrap = document.getElementById('crosstalkBiasCameraId');
  const newSel = cameraSelect('', g.crosstalkBiasCameraId, true);
  newSel.id = 'crosstalkBiasCameraId';
  newSel.onchange = (e) => (g.crosstalkBiasCameraId = e.target.value || null);
  biasWrap.replaceWith(newSel);

  document.getElementById('attackMs').oninput = (e) => (g.attackMs = parseInt(e.target.value, 10));
  document.getElementById('releaseHoldMs').oninput = (e) => (g.releaseHoldMs = parseInt(e.target.value, 10));
  document.getElementById('minShotHoldMs').oninput = (e) => (g.minShotHoldMs = parseInt(e.target.value, 10));
  document.getElementById('hysteresisDb').oninput = (e) => (g.hysteresisDb = parseFloat(e.target.value));
  document.getElementById('transitionType').onchange = (e) => (g.transition.type = e.target.value);
  document.getElementById('autoDurationFrames').oninput = (e) => (g.transition.autoDurationFrames = parseInt(e.target.value, 10));
  document.getElementById('crosstalkWindowMs').oninput = (e) => (g.crosstalkWindowMs = parseInt(e.target.value, 10));
  document.getElementById('showLatencyReadout').onchange = (e) => (config.showLatencyReadout = e.target.checked);
}

function renderAdvanced() {
  const adv = config.global.advanced;
  document.getElementById('noiseFloorAdaptiveEnabled').checked = !!adv.noiseFloorAdaptive.enabled;
  document.getElementById('noiseFloorMarginDb').value = adv.noiseFloorAdaptive.marginDb;
  document.getElementById('noiseFloorAdaptWindowSec').value = adv.noiseFloorAdaptive.adaptWindowSec;
  document.getElementById('speechBandFilterEnabled').checked = !!adv.speechBandFilter.enabled;
  document.getElementById('speechBandLowHz').value = adv.speechBandFilter.lowHz;
  document.getElementById('speechBandHighHz').value = adv.speechBandFilter.highHz;
  document.getElementById('audioWatchdogMs').value = adv.audioWatchdogMs;
  document.getElementById('clippingWarnDb').value = adv.clippingWarnDb;

  document.getElementById('noiseFloorAdaptiveEnabled').onchange = (e) => (adv.noiseFloorAdaptive.enabled = e.target.checked);
  document.getElementById('noiseFloorMarginDb').oninput = (e) => (adv.noiseFloorAdaptive.marginDb = parseFloat(e.target.value));
  document.getElementById('noiseFloorAdaptWindowSec').oninput = (e) => (adv.noiseFloorAdaptive.adaptWindowSec = parseInt(e.target.value, 10));
  document.getElementById('speechBandFilterEnabled').onchange = (e) => (adv.speechBandFilter.enabled = e.target.checked);
  document.getElementById('speechBandLowHz').oninput = (e) => (adv.speechBandFilter.lowHz = parseInt(e.target.value, 10));
  document.getElementById('speechBandHighHz').oninput = (e) => (adv.speechBandFilter.highHz = parseInt(e.target.value, 10));
  document.getElementById('audioWatchdogMs').oninput = (e) => (adv.audioWatchdogMs = parseInt(e.target.value, 10));
  document.getElementById('clippingWarnDb').oninput = (e) => (adv.clippingWarnDb = parseFloat(e.target.value));
}

async function calibrateMic(mic, strip) {
  const btn = strip.querySelector('.mic-calibrate');
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Stay quiet...';
  setTimeout(() => { btn.textContent = 'Now talk...'; }, 3000);
  try {
    const result = await fetchJSON(`/api/calibrate/${encodeURIComponent(mic.id)}`, { method: 'POST' });
    mic.thresholdDb = result.suggestedThresholdDb;
    strip.querySelector('.mic-threshold').value = mic.thresholdDb;
    strip.querySelector('.meter-threshold').style.left = `${dbToPercent(mic.thresholdDb)}%`;
    btn.textContent = `Suggest ${result.suggestedThresholdDb} dB`;
    setTimeout(() => { btn.textContent = original; }, 2500);
  } catch (e) {
    btn.textContent = 'Failed';
    setTimeout(() => { btn.textContent = original; }, 2000);
  } finally {
    btn.disabled = false;
  }
}

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === 'tick') updateMeters(msg.payload);
    if (msg.type === 'switch') logSwitch(msg.payload);
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}

function updateMeters(snapshot) {
  Object.entries(snapshot.mics).forEach(([micId, m]) => {
    const strip = document.querySelector(`.mic-strip[data-mic-id="${micId}"]`);
    if (!strip) return;
    strip.querySelector('.meter-fill').style.width = `${dbToPercent(m.level)}%`;
    strip.classList.toggle('talking', !!m.talking);
    strip.querySelector('.badge.clip').classList.toggle('active', !!m.clipping);
    strip.querySelector('.badge.stalled').classList.toggle('active', !!snapshot.stalled);
  });

  document.getElementById('stalledIndicator').classList.toggle('hidden', !snapshot.stalled);

  const activeMic = config.mics.find((m) => m.id === snapshot.activeMicId);
  const activeCam = config.cameras.find((c) => c.id === snapshot.activeCameraId);
  document.getElementById('activeMic').textContent = activeMic ? activeMic.name : '—';
  document.getElementById('activeCamera').textContent = activeCam ? activeCam.name : '—';

  document.querySelectorAll('.camera-strip').forEach((elem) => {
    elem.classList.toggle('active', elem.dataset.cameraId === snapshot.activeCameraId);
  });
}

function logSwitch(evt) {
  const cam = config.cameras.find((c) => c.id === evt.cameraId);
  const mic = config.mics.find((m) => m.id === evt.micId);
  const logEl = document.getElementById('log');
  const time = new Date(evt.at).toLocaleTimeString();
  let text = `${time} -> ${cam ? cam.name : evt.cameraId} (${mic ? mic.name : 'shared'})`;
  if (config.showLatencyReadout && evt.latencyMs != null) {
    text += ` [${Math.round(evt.latencyMs)}ms since trigger]`;
  }
  logEl.textContent = text;
}

async function refreshStatus() {
  try {
    const status = await fetchJSON('/api/status');
    const dot = document.getElementById('atemStatus');
    dot.classList.toggle('on', status.atem.connected);
    dot.classList.toggle('off', !status.atem.connected);

    const tcEl = document.getElementById('timecodeStatus');
    const markBtn = document.getElementById('markStartBtn');
    if (status.timecode && status.timecode.enabled) {
      tcEl.textContent = `Timecode: LTC decode (${status.timecode.hasSignal ? 'live' : 'no signal'})`;
      markBtn.style.display = 'none';
    } else {
      tcEl.textContent = 'Timecode: wall-clock estimate — mark recording start when you begin ISO recording';
      markBtn.style.display = '';
    }
  } catch (e) {
    /* ignore */
  }
}

async function refreshPresets() {
  const presets = await fetchJSON('/api/presets').catch(() => []);
  const sel = document.getElementById('presetList');
  sel.replaceChildren();
  presets.forEach((p) => sel.appendChild(el('option', { value: p.replace(/\.json$/, ''), text: p })));
}

function collectConfig() {
  config.audioDevice.deviceId = document.getElementById('deviceSelect').value || null;
  config.audioDevice.channelCount = parseInt(document.getElementById('channelCount').value, 10);
  config.audioDevice.sampleRate = parseInt(document.getElementById('sampleRate').value, 10);
  return config;
}

function nextId(items, prefix) {
  let n = items.length + 1;
  const existing = new Set(items.map((i) => i.id));
  while (existing.has(`${prefix}${n}`)) n += 1;
  return `${prefix}${n}`;
}

document.getElementById('addMicBtn').addEventListener('click', () => {
  if (config.mics.length >= 10) return;
  const id = nextId(config.mics, 'mic');
  config.mics.push({
    id, name: `Mic ${config.mics.length + 1}`, enabled: true, thresholdDb: -35, priority: 1,
    cameraId: config.cameras[0] ? config.cameras[0].id : null,
  });
  renderMics();
});

document.getElementById('removeMicBtn').addEventListener('click', () => {
  if (config.mics.length === 0) return;
  config.mics.pop();
  renderMics();
});

document.getElementById('addCameraBtn').addEventListener('click', () => {
  if (config.cameras.length >= 10) return;
  const id = nextId(config.cameras, 'cam');
  const n = config.cameras.length + 1;
  config.cameras.push({ id, name: `Cam ${n}`, atemInput: n, isoReelName: `Input ${n}` });
  renderCameras();
  renderMics();
  renderGlobal();
});

document.getElementById('removeCameraBtn').addEventListener('click', () => {
  if (config.cameras.length === 0) return;
  config.cameras.pop();
  renderCameras();
  renderMics();
  renderGlobal();
});

document.getElementById('atemConnectBtn').addEventListener('click', async () => {
  const ip = document.getElementById('atemIp').value;
  await fetchJSON('/api/atem/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ip }) });
});

document.getElementById('masterEnable').addEventListener('change', async (e) => {
  await fetchJSON('/api/engine/enabled', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: e.target.checked }) });
});

document.getElementById('applyAudioBtn').addEventListener('click', async () => {
  collectConfig();
  await fetchJSON('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
  await fetchJSON('/api/config/apply-audio', { method: 'POST' });
});

document.getElementById('saveConfigBtn').addEventListener('click', async () => {
  collectConfig();
  await fetchJSON('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
  const btn = document.getElementById('saveConfigBtn');
  const original = btn.textContent;
  btn.textContent = 'Saved';
  setTimeout(() => (btn.textContent = original), 1200);
});

document.getElementById('savePresetBtn').addEventListener('click', async () => {
  const name = document.getElementById('presetName').value.trim();
  if (!name) return;
  collectConfig();
  await fetchJSON(`/api/presets/${encodeURIComponent(name)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
  await refreshPresets();
});

document.getElementById('loadPresetBtn').addEventListener('click', async () => {
  const name = document.getElementById('presetList').value;
  if (!name) return;
  await fetchJSON(`/api/presets/${encodeURIComponent(name)}/load`, { method: 'POST' });
  location.reload();
});

document.getElementById('markStartBtn').addEventListener('click', async () => {
  await fetchJSON('/api/timecode/mark-start', { method: 'POST' });
  const btn = document.getElementById('markStartBtn');
  const original = btn.textContent;
  btn.textContent = 'Marked';
  setTimeout(() => (btn.textContent = original), 1500);
});

document.getElementById('exportEdlBtn').addEventListener('click', () => {
  const fromVal = document.getElementById('exportFrom').value;
  const toVal = document.getElementById('exportTo').value;
  if (!fromVal || !toVal) return;
  const fromMs = new Date(fromVal).getTime();
  const toMs = new Date(toVal).getTime();
  window.location = `/api/export/edl?from=${fromMs}&to=${toMs}`;
});

loadAll();
```

- [ ] **Step 2: Commit**

```bash
git add web/app.js
git commit -m "feat: frontend app.js (safe-DOM) with calibration, badges, advanced, export"
```

---

## Task 29: Config template (`config/default.json`) and `requirements.txt`

**Files:**
- Create: `config/default.json`
- Create: `requirements.txt`

- [ ] **Step 1: Write `config/default.json`**

Ships 8 mics / 6 cameras per the design spec, using the new schema (top-level `enabled`, no per-mic `channelIndex`/`sourceType`, `isoReelName` per camera, `timecode` block, `global.advanced`).

```json
{
  "atem": { "ip": "192.168.1.240", "meIndex": 0 },
  "audioDevice": { "type": "system", "deviceId": null, "sampleRate": 48000, "channelCount": 8 },
  "timecode": { "enabled": false, "channelIndex": null },
  "enabled": false,
  "showLatencyReadout": true,
  "global": {
    "attackMs": 150,
    "releaseHoldMs": 2500,
    "minShotHoldMs": 2000,
    "hysteresisDb": 4,
    "crosstalkWindowMs": 400,
    "crosstalkBiasCameraId": "cam6",
    "transition": { "type": "cut", "autoDurationFrames": 15 },
    "timelineFps": 29.97,
    "advanced": {
      "noiseFloorAdaptive": { "enabled": true, "marginDb": 10, "adaptWindowSec": 30 },
      "speechBandFilter": { "enabled": true, "lowHz": 300, "highHz": 3400 },
      "audioWatchdogMs": 500,
      "clippingWarnDb": -1
    }
  },
  "cameras": [
    { "id": "cam1", "name": "Cam 1", "atemInput": 1, "isoReelName": "Input 1" },
    { "id": "cam2", "name": "Cam 2", "atemInput": 2, "isoReelName": "Input 2" },
    { "id": "cam3", "name": "Cam 3", "atemInput": 3, "isoReelName": "Input 3" },
    { "id": "cam4", "name": "Cam 4", "atemInput": 4, "isoReelName": "Input 4" },
    { "id": "cam5", "name": "Cam 5", "atemInput": 5, "isoReelName": "Input 5" },
    { "id": "cam6", "name": "Wide / Cutaway", "atemInput": 6, "isoReelName": "Input 6" }
  ],
  "mics": [
    { "id": "mic1", "name": "Mic 1", "enabled": true, "thresholdDb": -35, "priority": 1, "cameraId": "cam1" },
    { "id": "mic2", "name": "Mic 2", "enabled": true, "thresholdDb": -35, "priority": 1, "cameraId": "cam2" },
    { "id": "mic3", "name": "Mic 3", "enabled": true, "thresholdDb": -35, "priority": 1, "cameraId": "cam3" },
    { "id": "mic4", "name": "Mic 4", "enabled": true, "thresholdDb": -35, "priority": 1, "cameraId": "cam4" },
    { "id": "mic5", "name": "Mic 5", "enabled": true, "thresholdDb": -35, "priority": 1, "cameraId": "cam5" },
    { "id": "mic6", "name": "Mic 6", "enabled": true, "thresholdDb": -35, "priority": 1, "cameraId": "cam6" },
    { "id": "mic7", "name": "Mic 7", "enabled": true, "thresholdDb": -35, "priority": 1, "cameraId": "cam6" },
    { "id": "mic8", "name": "Mic 8", "enabled": true, "thresholdDb": -35, "priority": 1, "cameraId": "cam6" }
  ]
}
```

- [ ] **Step 2: Write `requirements.txt`**

```
fastapi>=0.110
uvicorn[standard]>=0.29
PyATEMMax>=1.0
sounddevice>=0.4.6
numpy>=1.24
scipy>=1.10
pytest>=8.0
httpx>=0.27
```

(`httpx` is required by FastAPI's `TestClient`.)

- [ ] **Step 3: Verify default.json loads and matches the schema the API expects**

Run:
```bash
python -c "import json; c=json.load(open('config/default.json')); assert 'enabled' in c and 'advanced' in c['global'] and c['mics'][0].get('channelIndex') is None; print('schema ok, mics:', len(c['mics']), 'cams:', len(c['cameras']))"
```
Expected: `schema ok, mics: 8 cams: 6`

- [ ] **Step 4: Commit**

```bash
git add config/default.json requirements.txt
git commit -m "feat: default config template and Python requirements"
```

---

## Task 30: Full test suite green + README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Install dependencies and run the entire test suite**

Run:
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```
Expected: all tests PASS across `test_config.py` (4), `test_switch_engine.py` (25), `test_dsp.py` (7), `test_switch_log.py` (3), `test_calibration.py` (2), `test_edl_export.py` (8), `test_ltc_reader.py` (4), `test_api_config.py` (9). No failures, no errors.

- [ ] **Step 2: Start the server and smoke-check the UI loads**

Run:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 4590 &
sleep 3
curl -s http://localhost:4590/api/config | head -c 80
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:4590/
kill %1
```
Expected: config JSON prints; `/` returns `200` (static `index.html` served). If audio hardware is absent, `start_audio()` may log an error but must not crash the process — confirm the two curls still succeed.

- [ ] **Step 3: Write `README.md`**

````markdown
# Mic → Cam ATEM Auto-Switcher (Python)

Standalone audio-driven camera switcher for a Blackmagic ATEM, separate from your
main production switcher. Reads live mic levels from a multichannel audio interface
and auto-cuts the ATEM to the talking person's camera. Web UI for assignment/tuning.
Python port of the Node.js `mic-cam-switcher` prototype (see `reference/`).

## Requirements

- Python 3.10+
- Network access to the ATEM (same subnet or routed; standard ATEM UDP control).
- A multichannel input device visible to the OS (Sound Devices interface, or Dante
  Virtual Soundcard — both appear as ordinary PortAudio devices).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 4590
```

Open `http://localhost:4590`.

## Before trusting it live: run the smoke test

```bash
python -m app.smoke_test <atem-ip>
```

Connects, prints model/input info, and issues one cut + one auto on a harmless input.
Run this against the real switcher first — the dev environment can't reach hardware.

## Usage

1. Enter the ATEM IP, hit **Connect** (status dot goes green).
2. Under **Audio Device**, pick the interface, set channel count + sample rate,
   **Apply & Restart Capture**.
3. Per mic: name it, set threshold (or hit **Calibrate** for a suggestion), pick its
   camera. A mic's physical channel = its position in the list (mic 1 = channel 0).
4. Set cameras' ATEM inputs and ISO reel names (reel names must match the ATEM ISO
   recording filenames for Resolve auto-conform).
5. Tune **Global Timing**; expand **Advanced** for adaptive noise floor, speech-band
   filter, watchdog, and clip warning.
6. Toggle **Auto-Switch Active** to let the engine cut the ATEM. Off = meters only.
7. **Save Config** / **Presets** to persist and switch between setups.

## Timecode & EDL export

Optional. With `timecode.enabled` off (default), export uses a wall-clock estimate —
click **Mark Recording Start** when you start ISO recording. With it on, route a
jam-synced LTC feed into a spare channel and set its channel index; cuts are tagged
with decoded timecode. Accurate end-to-end EDLs require the ATEM itself to be
genlocked/timecode-referenced to the same master LTC (verify on your Constellation).

Export via the **Export Timeline** panel → downloads a CMX3600 `.edl`.

## Testing

`pytest` — pure-logic modules (switch engine, DSP, EDL export, LTC bit-decode,
config, calibration) are fully unit-tested. Hardware-facing modules (ATEM control,
audio capture, LTC analog decode) are validated via `smoke_test.py` and manual
testing against real gear.

## Config

`config/default.json` is the template (never overwritten). `config/live.json` is the
working copy (gitignored), written on save. Presets live in `config/presets/`.
````

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, usage, timecode, and testing notes"
```

---

## Task 31: Hardware validation checklist (manual, no code)

This task is a documented checklist for the operator to run against real gear — it has no unit tests because every item is hardware-dependent (design spec, Testing + timecode-caveat sections). Do not skip; these are the parts the dev environment provably cannot verify.

- [ ] **Step 1: ATEM control** — `python -m app.smoke_test <atem-ip>`. Confirm connect succeeds, model/input list prints, and the cut + auto visibly change program on the switcher.

- [ ] **Step 2: Audio capture** — start the app, select the real interface, Apply & Restart. Confirm each mic strip's meter moves when you talk into the corresponding physical channel, and that mic position → channel mapping is correct (mic 1 responds to channel 0, etc.).

- [ ] **Step 3: Live switching** — enable Auto-Switch; confirm cuts follow the talker, min-shot-hold prevents chatter, crosstalk cuts to the wide shot when two people overlap, and the latency readout shows plausible ms values.

- [ ] **Step 4: Clipping & watchdog** — overdrive a mic to confirm the CLIP badge lights; pull the audio device to confirm the AUDIO STALLED warning appears and the last shot holds (no spurious cuts).

- [ ] **Step 5: LTC timecode (if used)** — feed a real jam-synced LTC generator into the configured channel; confirm `/api/status` shows `timecode.hasSignal: true` and switch-log entries carry sane decoded timecodes. Confirm the ATEM's own ISO recordings are genlocked/timecode-referenced to the same master so decoded values match the recordings' embedded TC.

- [ ] **Step 6: EDL conform** — record a short session with ISO recordings, export an EDL for the range, import into DaVinci Resolve, and confirm cuts land on the right cameras at the right times and reels auto-conform to the ISO clips.

---

## Self-Review Notes (for the executor)

- **Schema:** every task treats the master switch as top-level `config["enabled"]` and `config["global"]` as timing-only, matching the design spec's JSON (lines 76–107). This differs from the Node prototype, which nested `enabled` in `global` — do not copy the Node nesting.
- **Positional mic channels:** there is no `channelIndex` in the config; `_consume_audio_queue` in `app/main.py` maps `mics[i]` → audio channel `i`. Extra mics beyond the device's channel count simply get no level (absent from `levels_by_mic_id`), matching the spec's "flatlined meter, no error" requirement.
- **`priority` default:** engine uses `mic.get("priority", 1)`; `default.json` sets it explicitly.
- **No `sourceType`:** the Python config schema drops the Node prototype's per-mic `sourceType`. Fairlight-direct capture remains an experimental, non-user-facing stub (Task 19), per the design spec's "Deferred / experimental" section.
- **Test-mode gating:** `MIC_CAM_SKIP_STARTUP=1` (set in the API test fixture) prevents the `startup` handler from touching real hardware under `TestClient`.
- **XSS note (Task 28):** the frontend builds mic/camera strips with `createElement` + `textContent`/`value` rather than `innerHTML` string interpolation, so operator-entered names can never inject markup. Keep it that way if extending the UI.
