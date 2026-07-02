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
