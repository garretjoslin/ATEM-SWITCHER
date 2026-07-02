# tests/test_ltc_reader.py
from app.timecode.ltc_reader import decode_ltc_frame_bits, timecode_dict_to_str, SYNC_WORD_BITS


def _bits_for_bcd(value, width):
    return [(value >> i) & 1 for i in range(width)]


def _build_frame(hours, minutes, seconds, frames):
    bits = [0] * 80
    bits[0:4] = _bits_for_bcd(frames % 10, 4)
    bits[8:10] = _bits_for_bcd(frames // 10, 2)
    bits[16:20] = _bits_for_bcd(seconds % 10, 4)
    bits[24:27] = _bits_for_bcd(seconds // 10, 3)
    bits[32:36] = _bits_for_bcd(minutes % 10, 4)
    bits[40:43] = _bits_for_bcd(minutes // 10, 3)
    bits[48:52] = _bits_for_bcd(hours % 10, 4)
    bits[56:58] = _bits_for_bcd(hours // 10, 2)
    bits[64:80] = SYNC_WORD_BITS
    return bits


def test_decode_known_frame():
    bits = _build_frame(hours=1, minutes=2, seconds=3, frames=4)
    tc = decode_ltc_frame_bits(bits)
    assert tc == {"hours": 1, "minutes": 2, "seconds": 3, "frames": 4}
    assert timecode_dict_to_str(tc) == "01:02:03:04"


def test_decode_rejects_wrong_length():
    assert decode_ltc_frame_bits([0] * 79) is None


def test_decode_rejects_bad_sync_word():
    bits = _build_frame(hours=0, minutes=0, seconds=0, frames=0)
    bits[64] = 1  # corrupt the sync word
    assert decode_ltc_frame_bits(bits) is None


def test_decode_max_values():
    bits = _build_frame(hours=23, minutes=59, seconds=59, frames=29)
    tc = decode_ltc_frame_bits(bits)
    assert tc == {"hours": 23, "minutes": 59, "seconds": 59, "frames": 29}
