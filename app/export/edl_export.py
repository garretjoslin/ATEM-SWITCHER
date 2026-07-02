class EdlExportError(Exception):
    pass


def ms_to_frames(ms: float, fps: float) -> int:
    return round(ms / 1000 * fps)


def frames_to_timecode(total_frames: int, fps: float) -> str:
    fps_int = round(fps)
    frames = total_frames % fps_int
    total_seconds = total_frames // fps_int
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def timecode_to_frames(tc: str, fps: float) -> int:
    h, m, s, f = (int(x) for x in tc.split(":"))
    fps_int = round(fps)
    return ((h * 60 + m) * 60 + s) * fps_int + f
