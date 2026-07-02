# app/audio/atem_fairlight_source.py
import asyncio

"""
EXPERIMENTAL. See docs/superpowers/specs/2026-06-30-mic-cam-atem-switcher-design.md,
"Deferred / experimental" section. PyATEMMax exposes Fairlight mixer *state* (gain,
EQ, dynamics) but not consistent live meter ticks across ATEM firmware/models. Kept
as a documented starting point -- confirm the state-tree attribute names below
against your actual switcher's PyATEMMax object before relying on this; the reliable
path is tapping mics into the audio interface and using system_audio_source.py.
"""


class AtemFairlightSource:
    def __init__(self, atem_controller, poll_ms=50):
        self.atem_controller = atem_controller
        self.poll_ms = poll_ms
        self._on_levels_cb = None
        self._on_unavailable_cb = None

    def on_levels(self, callback):
        self._on_levels_cb = callback

    def on_unavailable(self, callback):
        self._on_unavailable_cb = callback

    async def start(self):
        while True:
            self._poll()
            await asyncio.sleep(self.poll_ms / 1000)

    def _poll(self):
        if not self.atem_controller.connected:
            return
        fairlight_state = getattr(self.atem_controller.switcher, "fairlightAudioMixerInput", None)
        if not fairlight_state:
            if self._on_unavailable_cb:
                self._on_unavailable_cb()
            return
        # Unconfirmed against real hardware: PyATEMMax's Fairlight state-tree layout
        # and attribute names need verification (see module docstring above).
        levels = {}
        if self._on_levels_cb:
            self._on_levels_cb(levels)
