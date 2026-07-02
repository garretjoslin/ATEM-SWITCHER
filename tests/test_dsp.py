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


def test_bandpass_filter_attenuates_out_of_band_tone_more_than_in_band():
    sample_rate = 48000
    t = np.linspace(0, 1, sample_rate, endpoint=False)
    low_tone = np.sin(2 * np.pi * 80 * t).astype(np.float32)  # below 300-3400 band
    in_band_tone = np.sin(2 * np.pi * 1000 * t).astype(np.float32)  # inside band

    low_filter = dsp.SpeechBandFilter(low_hz=300, high_hz=3400, sample_rate=sample_rate)
    in_band_filter = dsp.SpeechBandFilter(low_hz=300, high_hz=3400, sample_rate=sample_rate)

    filtered_low = low_filter.process(low_tone)
    filtered_in_band = in_band_filter.process(in_band_tone)

    low_attenuation_db = dsp.rms_dbfs(low_tone) - dsp.rms_dbfs(filtered_low)
    in_band_attenuation_db = dsp.rms_dbfs(in_band_tone) - dsp.rms_dbfs(filtered_in_band)

    assert low_attenuation_db > in_band_attenuation_db + 10  # low tone attenuated much more


def test_bandpass_filter_preserves_state_across_chunks():
    sample_rate = 48000
    t = np.linspace(0, 1, sample_rate, endpoint=False)
    tone = np.sin(2 * np.pi * 1000 * t).astype(np.float32)

    whole_filter = dsp.SpeechBandFilter(low_hz=300, high_hz=3400, sample_rate=sample_rate)
    whole_output = whole_filter.process(tone)

    chunked_filter = dsp.SpeechBandFilter(low_hz=300, high_hz=3400, sample_rate=sample_rate)
    chunk_size = 480
    chunked_output = np.concatenate([
        chunked_filter.process(tone[i:i + chunk_size]) for i in range(0, len(tone), chunk_size)
    ])

    np.testing.assert_allclose(whole_output, chunked_output, atol=1e-5)
