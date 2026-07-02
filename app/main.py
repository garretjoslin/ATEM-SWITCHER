# app/main.py
import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import config as config_store
from app import switch_log
from app.export.edl_export import build_cmx3600_edl, EdlExportError

APP_DIR = Path(__file__).resolve().parent.parent

app = FastAPI()

_config_base_dir = os.environ.get("MIC_CAM_CONFIG_DIR")

state = {
    "config": config_store.load_config(base_dir=_config_base_dir),
    "audio_source": None,
    "record_start_epoch": None,
    "last_levels_at": None,
    "latest_levels": {},
    "ltc_reader": None,
}

from app.atem_controller import AtemController
from app.switch_engine import SwitchEngine
from app.audio.system_audio_source import SystemAudioSource
from app.calibration import suggest_threshold_db
from app.timecode.ltc_reader import LtcReader

atem_controller = AtemController()

switch_engine = SwitchEngine(atem_controller)
switch_engine.set_config(state["config"])

ws_clients: set[WebSocket] = set()


async def broadcast(msg_type, payload):
    msg = json.dumps({"type": msg_type, "payload": payload})
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


def _on_tick(snapshot):
    asyncio.create_task(broadcast("tick", snapshot))


def _on_switch(evt):
    asyncio.create_task(broadcast("switch", evt))
    timecode = None
    if state["config"]["timecode"]["enabled"] and state.get("ltc_reader"):
        timecode = state["ltc_reader"].current_timecode()
    switch_log.append_entry(evt["cameraId"], evt["atemInput"], int(evt["at"]), timecode=timecode)


switch_engine.on_tick(_on_tick)
switch_engine.on_switch(_on_switch)

audio_queue = None


def start_audio():
    global audio_queue
    if state["audio_source"]:
        state["audio_source"].stop()
        state["audio_source"] = None

    loop = asyncio.get_running_loop()
    audio_queue = asyncio.Queue()
    cfg = state["config"]
    adv = cfg["global"].get("advanced", {})
    speech_filter_cfg = adv.get("speechBandFilter")
    clip_warn_db = adv.get("clippingWarnDb", -1.0)

    ltc_reader = None
    ltc_channel_index = None
    if cfg["timecode"]["enabled"] and cfg["timecode"]["channelIndex"] is not None:
        ltc_reader = LtcReader(sample_rate=cfg["audioDevice"]["sampleRate"], fps=cfg["global"]["timelineFps"])
        ltc_channel_index = cfg["timecode"]["channelIndex"]
    state["ltc_reader"] = ltc_reader

    source = SystemAudioSource(
        loop=loop,
        queue=audio_queue,
        device_id=cfg["audioDevice"]["deviceId"],
        sample_rate=cfg["audioDevice"]["sampleRate"],
        channel_count=cfg["audioDevice"]["channelCount"],
        speech_band_filter=speech_filter_cfg,
        clip_warn_db=clip_warn_db,
        ltc_reader=ltc_reader,
        ltc_channel_index=ltc_channel_index,
    )
    source.start()
    state["audio_source"] = source
    asyncio.create_task(_consume_audio_queue(audio_queue))


async def _consume_audio_queue(my_queue):
    mic_ids = [m["id"] for m in state["config"]["mics"]]
    while state["audio_source"] is not None and audio_queue is my_queue:
        levels, clipping = await my_queue.get()
        state["last_levels_at"] = time.time() * 1000
        levels_by_mic_id = {}
        clipping_by_mic_id = {}
        for idx, mic_id in enumerate(mic_ids):
            if idx < len(levels):
                levels_by_mic_id[mic_id] = levels[idx]
                clipping_by_mic_id[mic_id] = clipping[idx]
        state["latest_levels"] = levels_by_mic_id
        switch_engine.update_levels(levels_by_mic_id, clipping_by_mic_id)


async def _watchdog_loop():
    while True:
        await asyncio.sleep(0.1)
        watchdog_ms = state["config"]["global"].get("advanced", {}).get("audioWatchdogMs", 500)
        last = state["last_levels_at"]
        if last is not None and (time.time() * 1000 - last) > watchdog_ms and state["audio_source"] is not None:
            switch_engine.mark_stalled()


@app.get("/api/config")
def get_config():
    return state["config"]


@app.post("/api/config")
async def post_config(request: Request):
    body = await request.json()
    state["config"] = body
    config_store.save_config(body, base_dir=_config_base_dir)
    return {"ok": True}


@app.get("/api/devices")
def get_devices():
    from app.audio.system_audio_source import SystemAudioSource
    try:
        return SystemAudioSource.list_devices()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/presets")
def get_presets():
    return config_store.list_presets(base_dir=_config_base_dir)


@app.post("/api/presets/{name}")
async def post_preset(name: str, request: Request):
    body = await request.json()
    saved_name = config_store.save_preset(name, body, base_dir=_config_base_dir)
    return {"ok": True, "name": saved_name}


@app.get("/api/presets/{name}")
def get_preset(name: str):
    try:
        return config_store.load_preset(name, base_dir=_config_base_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="preset not found")


@app.post("/api/presets/{name}/load")
def load_preset_route(name: str):
    try:
        preset = config_store.load_preset(name, base_dir=_config_base_dir)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="preset not found")
    state["config"] = preset
    config_store.save_config(preset, base_dir=_config_base_dir)
    return {"ok": True}


@app.post("/api/atem/connect")
async def atem_connect(request: Request):
    body = await request.json()
    ip = body.get("ip") or state["config"]["atem"]["ip"]
    state["config"]["atem"]["ip"] = ip
    config_store.save_config(state["config"], base_dir=_config_base_dir)
    atem_controller.connect(ip)
    return {"ok": True}


@app.post("/api/engine/enabled")
async def engine_enabled(request: Request):
    body = await request.json()
    state["config"]["enabled"] = bool(body.get("enabled"))
    config_store.save_config(state["config"], base_dir=_config_base_dir)
    return {"ok": True}


@app.get("/api/status")
def get_status():
    ltc_reader = state.get("ltc_reader")
    return {
        "atem": atem_controller.get_status(),
        "audio": {"running": state["audio_source"] is not None},
        "timecode": {
            "enabled": state["config"]["timecode"]["enabled"],
            "hasSignal": ltc_reader.has_signal() if ltc_reader else False,
        },
    }


@app.post("/api/config/apply-audio")
async def apply_audio():
    start_audio()
    return {"ok": True}


@app.post("/api/calibrate/{mic_id}")
async def calibrate(mic_id: str):
    mic = next((m for m in state["config"]["mics"] if m["id"] == mic_id), None)
    if mic is None:
        raise HTTPException(status_code=404, detail="mic not found")

    async def sample_for(seconds):
        samples = []
        deadline = time.time() + seconds
        while time.time() < deadline:
            level = state["latest_levels"].get(mic_id)
            if level is not None:
                samples.append(level)
            await asyncio.sleep(0.03)
        return samples

    floor_samples = await sample_for(3.0)
    speech_samples = await sample_for(3.0)

    noise_floor_db = sum(floor_samples) / len(floor_samples) if floor_samples else -100.0
    speech_level_db = max(speech_samples) if speech_samples else -100.0
    suggested = suggest_threshold_db(noise_floor_db, speech_level_db)
    return {
        "noiseFloorDb": round(noise_floor_db, 1),
        "speechLevelDb": round(speech_level_db, 1),
        "suggestedThresholdDb": round(suggested, 1),
    }


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_clients.discard(websocket)


@app.post("/api/timecode/mark-start")
def mark_start():
    state["record_start_epoch"] = int(time.time() * 1000)
    return {"ok": True, "recordStartEpoch": state["record_start_epoch"]}


@app.get("/api/export/edl")
def export_edl(from_ms: int = Query(..., alias="from"), to_ms: int = Query(..., alias="to")):
    entries = switch_log.read_entries(from_ms=from_ms, to_ms=to_ms)
    cameras_by_id = {c["id"]: c for c in state["config"]["cameras"]}
    fps = state["config"]["global"]["timelineFps"]
    mode = "timecode" if state["config"]["timecode"]["enabled"] else "wallclock"
    try:
        edl_text = build_cmx3600_edl(
            entries, cameras_by_id, fps, mode, to_ms=to_ms, record_start_epoch=state["record_start_epoch"],
        )
    except EdlExportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PlainTextResponse(
        edl_text, media_type="application/x-cmx3600",
        headers={"Content-Disposition": "attachment; filename=export.edl"},
    )


@app.on_event("startup")
async def on_startup():
    if os.environ.get("MIC_CAM_SKIP_STARTUP"):
        return
    if state["config"]["atem"]["ip"]:
        atem_controller.connect(state["config"]["atem"]["ip"])
    asyncio.create_task(atem_controller.maintain_connection())
    start_audio()
    asyncio.create_task(_watchdog_loop())


app.mount("/", StaticFiles(directory=str(APP_DIR / "web"), html=True), name="web")
