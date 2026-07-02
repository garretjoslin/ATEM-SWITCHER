# app/main.py
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
