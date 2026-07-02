from app.export.edl_export import ms_to_frames, frames_to_timecode, timecode_to_frames, build_cmx3600_edl, EdlExportError


CAMERAS = {
    "cam1": {"id": "cam1", "name": "Cam 1", "atemInput": 1, "isoReelName": "Input 1"},
    "cam2": {"id": "cam2", "name": "Cam 2", "atemInput": 2, "isoReelName": "Input 2"},
}


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
