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
