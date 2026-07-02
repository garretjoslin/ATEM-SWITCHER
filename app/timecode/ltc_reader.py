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
