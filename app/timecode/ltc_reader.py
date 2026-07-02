# app/timecode/ltc_reader.py
SYNC_WORD_BITS = [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1]
FRAME_BIT_COUNT = 80


def _bcd_value(bits):
    value = 0
    for i, b in enumerate(bits):
        value += b * (2 ** i)
    return value


def decode_ltc_frame_bits(bits):
    if len(bits) != FRAME_BIT_COUNT:
        return None
    if list(bits[64:80]) != SYNC_WORD_BITS:
        return None

    hours = _bcd_value(bits[56:58]) * 10 + _bcd_value(bits[48:52])
    minutes = _bcd_value(bits[40:43]) * 10 + _bcd_value(bits[32:36])
    seconds = _bcd_value(bits[24:27]) * 10 + _bcd_value(bits[16:20])
    frames = _bcd_value(bits[8:10]) * 10 + _bcd_value(bits[0:4])
    return {"hours": hours, "minutes": minutes, "seconds": seconds, "frames": frames}


def timecode_dict_to_str(tc):
    return f"{tc['hours']:02d}:{tc['minutes']:02d}:{tc['seconds']:02d}:{tc['frames']:02d}"


class LtcReader:
    """Decodes LTC from a raw audio channel via biphase-mark zero-crossing
    demodulation. A '1' bit has a transition at both cell edges and the cell
    midpoint (two short intervals); a '0' bit has a transition only at cell
    edges (one long interval). Needs tuning/validation against a real LTC
    generator before trusting decoded values in production."""

    def __init__(self, sample_rate, fps=29.97):
        self.sample_rate = sample_rate
        self.fps = fps
        self._prev_sample = 0.0
        self._samples_since_transition = 0
        self._half_bit_samples = sample_rate / (fps * FRAME_BIT_COUNT * 2)
        self._pending_half = False
        self._bit_buffer = []
        self._last_timecode_str = None
        self._has_signal = False

    def process(self, samples) -> None:
        for sample in samples:
            self._samples_since_transition += 1
            crossed = (sample >= 0) != (self._prev_sample >= 0)
            self._prev_sample = sample
            if not crossed:
                continue

            interval = self._samples_since_transition
            self._samples_since_transition = 0

            if interval < self._half_bit_samples * 1.5:
                if self._pending_half:
                    self._bit_buffer.append(1)
                    self._pending_half = False
                    self._maybe_decode_frame()
                else:
                    self._pending_half = True
            else:
                self._pending_half = False
                self._bit_buffer.append(0)
                self._maybe_decode_frame()

    def _maybe_decode_frame(self):
        if len(self._bit_buffer) < FRAME_BIT_COUNT:
            return
        window = self._bit_buffer[-FRAME_BIT_COUNT:]
        tc = decode_ltc_frame_bits(window)
        if tc:
            self._last_timecode_str = timecode_dict_to_str(tc)
            self._has_signal = True
            self._bit_buffer = []

    def current_timecode(self):
        return self._last_timecode_str

    def has_signal(self):
        return self._has_signal
