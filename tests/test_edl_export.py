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
