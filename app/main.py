"""Placeholder FastAPI app.

Task 25 of the current implementation plan wires this up into the real
mic-cam-switcher backend (REST + WebSocket + audio + ATEM). This stub
exists only so the dev server can boot in the meantime.
"""
from fastapi import FastAPI

app = FastAPI(title="mic-cam-switcher (placeholder)")


@app.get("/")
def root():
    return {"status": "placeholder", "message": "Real backend lands in Task 25"}


@app.get("/api/status")
def status():
    return {"placeholder": True}
