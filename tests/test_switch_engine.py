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
