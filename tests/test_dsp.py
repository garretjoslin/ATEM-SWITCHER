import numpy as np
from app.audio import dsp


def test_rms_dbfs_of_silence_is_floor():
    samples = np.zeros(480, dtype=np.float32)
    assert dsp.rms_dbfs(samples) == -100.0


def test_rms_dbfs_of_full_scale_sine_near_minus_3db():
    t = np.linspace(0, 1, 480, endpoint=False)
    samples = np.sin(2 * np.pi * 100 * t).astype(np.float32)
    db = dsp.rms_dbfs(samples)
    assert -3.5 < db < -2.5  # sine RMS = amplitude / sqrt(2) ~= -3.01dB for full-scale


def test_peak_dbfs_of_full_scale_sine_near_zero():
    t = np.linspace(0, 1, 480, endpoint=False)
    samples = np.sin(2 * np.pi * 100 * t).astype(np.float32)
    db = dsp.peak_dbfs(samples)
    assert -0.5 < db <= 0.0


def test_peak_dbfs_of_silence_is_floor():
    samples = np.zeros(480, dtype=np.float32)
    assert dsp.peak_dbfs(samples) == -100.0


def test_empty_array_returns_floor():
    empty = np.array([], dtype=np.float32)
    assert dsp.rms_dbfs(empty) == -100.0
    assert dsp.peak_dbfs(empty) == -100.0
