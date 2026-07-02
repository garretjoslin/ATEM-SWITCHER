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
