# app/main.py
import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app import config as config_store

APP_DIR = Path(__file__).resolve().parent.parent

app = FastAPI()

_config_base_dir = os.environ.get("MIC_CAM_CONFIG_DIR")

state = {
    "config": config_store.load_config(base_dir=_config_base_dir),
    "audio_source": None,
    "record_start_epoch": None,
    "last_levels_at": None,
    "latest_levels": {},
}

from app.atem_controller import AtemController

atem_controller = AtemController()


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


@app.on_event("startup")
async def on_startup():
    if os.environ.get("MIC_CAM_SKIP_STARTUP"):
        return
    if state["config"]["atem"]["ip"]:
        atem_controller.connect(state["config"]["atem"]["ip"])
    asyncio.create_task(atem_controller.maintain_connection())
