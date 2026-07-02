# app/atem_controller.py
import asyncio
import PyATEMMax


class AtemController:
    def __init__(self):
        self.switcher = PyATEMMax.ATEMMax()
        self.connected = False
        self.current_input = None
        self.ip = None
        self.switcher.registerEvent(self.switcher.atem.events.connect, self._on_connect)
        self.switcher.registerEvent(self.switcher.atem.events.disconnect, self._on_disconnect)

    def _on_connect(self, params):
        self.connected = True

    def _on_disconnect(self, params):
        self.connected = False
        self.current_input = None

    def connect(self, ip):
        self.ip = ip
        self.switcher.connect(ip)

    def disconnect(self):
        self.switcher.disconnect()

    def cut_to(self, atem_input, me_index=0):
        if not self.connected:
            return
        if self.current_input == atem_input:
            return
        self.switcher.setPreviewInputVideoSource(me_index, atem_input)
        self.switcher.execCutME(me_index)
        self.current_input = atem_input

    def auto_to(self, atem_input, me_index=0):
        if not self.connected:
            return
        if self.current_input == atem_input:
            return
        self.switcher.setPreviewInputVideoSource(me_index, atem_input)
        self.switcher.execAutoME(me_index)
        self.current_input = atem_input

    def get_status(self):
        return {"connected": self.connected, "ip": self.ip, "currentInput": self.current_input}

    async def maintain_connection(self, poll_interval_sec=2, max_backoff_sec=30):
        """Background reconnect-with-backoff loop; run as an asyncio task from main.py."""
        backoff = poll_interval_sec
        while True:
            await asyncio.sleep(poll_interval_sec)
            if self.ip and not self.connected:
                try:
                    self.switcher.connect(self.ip)
                except Exception:
                    pass
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff_sec)
            else:
                backoff = poll_interval_sec
