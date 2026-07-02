# app/calibration.py
def suggest_threshold_db(noise_floor_db: float, speech_level_db: float) -> float:
    return noise_floor_db + 0.6 * (speech_level_db - noise_floor_db)
