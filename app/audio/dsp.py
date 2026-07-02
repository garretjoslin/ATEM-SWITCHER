import numpy as np

SILENCE_DB = -100.0


def rms_dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return SILENCE_DB
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    db = 20 * np.log10(rms) if rms > 0 else SILENCE_DB
    return max(db, SILENCE_DB)


def peak_dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return SILENCE_DB
    peak = float(np.max(np.abs(samples)))
    db = 20 * np.log10(peak) if peak > 0 else SILENCE_DB
    return max(db, SILENCE_DB)
