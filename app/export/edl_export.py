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


def build_cmx3600_edl(entries, cameras_by_id, fps, mode, to_ms, record_start_epoch=None,
                       title="mic-cam-switcher export"):
    if mode == "wallclock" and record_start_epoch is None:
        raise EdlExportError("recording start not marked; call POST /api/timecode/mark-start first")

    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    if not entries:
        return "\n".join(lines) + "\n"

    record_frame_cursor = 0
    event_num = 1
    for i, entry in enumerate(entries):
        camera = cameras_by_id.get(entry["cameraId"])
        if camera is None:
            continue

        next_epoch_ms = entries[i + 1]["epochMs"] if i + 1 < len(entries) else to_ms
        duration_ms = max(next_epoch_ms - entry["epochMs"], 0)
        duration_frames = max(ms_to_frames(duration_ms, fps), 1)

        if mode == "timecode":
            if entry.get("timecode") is None:
                raise EdlExportError(f"entry at {entry['epochMs']} has no decoded timecode")
            src_in_frames = timecode_to_frames(entry["timecode"], fps)
        else:
            src_in_frames = ms_to_frames(entry["epochMs"] - record_start_epoch, fps)
        src_out_frames = src_in_frames + duration_frames

        rec_in_frames = record_frame_cursor
        rec_out_frames = rec_in_frames + duration_frames
        record_frame_cursor = rec_out_frames

        reel = camera.get("isoReelName") or camera.get("name") or entry["cameraId"]
        lines.append(
            f"{event_num:03d}  {reel:<8} V     C        "
            f"{frames_to_timecode(src_in_frames, fps)} {frames_to_timecode(src_out_frames, fps)} "
            f"{frames_to_timecode(rec_in_frames, fps)} {frames_to_timecode(rec_out_frames, fps)}"
        )
        lines.append(f"* FROM CLIP NAME: {reel}")
        lines.append("")
        event_num += 1

    return "\n".join(lines) + "\n"
