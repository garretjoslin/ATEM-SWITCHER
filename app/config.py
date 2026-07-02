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
