import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

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


class SpeechBandFilter:
    def __init__(self, low_hz, high_hz, sample_rate, order=4):
        nyq = sample_rate / 2
        self.sos = butter(order, [low_hz / nyq, high_hz / nyq], btype="band", output="sos")
        self.zi = sosfilt_zi(self.sos)

    def process(self, samples: np.ndarray) -> np.ndarray:
        filtered, self.zi = sosfilt(self.sos, samples, zi=self.zi)
        return filtered.astype(np.float32)
