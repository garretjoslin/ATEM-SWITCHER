# tests/test_calibration.py
from app.calibration import suggest_threshold_db


def test_suggested_threshold_is_60_percent_from_floor_to_speech():
    assert suggest_threshold_db(noise_floor_db=-60, speech_level_db=-20) == -36.0


def test_suggested_threshold_handles_equal_floor_and_speech():
    assert suggest_threshold_db(noise_floor_db=-40, speech_level_db=-40) == -40.0
