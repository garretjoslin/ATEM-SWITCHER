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
