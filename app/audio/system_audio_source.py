# app/audio/system_audio_source.py
import sounddevice as sd

from . import dsp

WINDOW_MS = 30


class SystemAudioSource:
    def __init__(self, loop, queue, device_id=None, sample_rate=48000, channel_count=8,
                 speech_band_filter=None, clip_warn_db=-1.0, ltc_reader=None, ltc_channel_index=None):
        self.loop = loop
        self.queue = queue
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.channel_count = channel_count
        self.blocksize = int(sample_rate * WINDOW_MS / 1000)
        self.clip_warn_db = clip_warn_db
        self.ltc_reader = ltc_reader
        self.ltc_channel_index = ltc_channel_index
        self._filters = None
        if speech_band_filter and speech_band_filter.get("enabled"):
            self._filters = [
                dsp.SpeechBandFilter(speech_band_filter["lowHz"], speech_band_filter["highHz"], sample_rate)
                for _ in range(channel_count)
            ]
        self.stream = None

    @staticmethod
    def list_devices():
        devices = sd.query_devices()
        return [
            {
                "id": i,
                "name": d["name"],
                "maxInputChannels": d["max_input_channels"],
                "defaultSampleRate": d["default_samplerate"],
            }
            for i, d in enumerate(devices)
            if d["max_input_channels"] > 0
        ]

    def start(self):
        self.stream = sd.InputStream(
            device=self.device_id,
            channels=self.channel_count,
            samplerate=self.sample_rate,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._on_audio,
        )
        self.stream.start()

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def _on_audio(self, indata, frames, time_info, status):
        levels = []
        clipping = []
        for ch in range(self.channel_count):
            raw = indata[:, ch]
            clipping.append(dsp.peak_dbfs(raw) >= self.clip_warn_db)
            channel_samples = self._filters[ch].process(raw) if self._filters else raw
            levels.append(dsp.rms_dbfs(channel_samples))

        if self.ltc_reader is not None and self.ltc_channel_index is not None:
            if self.ltc_channel_index < self.channel_count:
                self.ltc_reader.process(indata[:, self.ltc_channel_index])

        self.loop.call_soon_threadsafe(self.queue.put_nowait, (levels, clipping))
