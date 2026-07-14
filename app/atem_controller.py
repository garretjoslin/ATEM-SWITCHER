# app/atem_controller.py
import PyATEMMax


class AtemController:
    def __init__(self):
        self.switcher = PyATEMMax.ATEMMax()
        self.connected = False
        self.current_input = None
        self.ip = None
        self._started = False  # True once switcher.connect() has spawned its comms threads
        self.switcher.registerEvent(self.switcher.atem.events.connect, self._on_connect)
        self.switcher.registerEvent(self.switcher.atem.events.disconnect, self._on_disconnect)

    def _on_connect(self, params):
        self.connected = True

    def _on_disconnect(self, params):
        self.connected = False
        self.current_input = None

    def connect(self, ip):
        # PyATEMMax.connect() spawns comms + event threads and reconnects internally
        # forever — it's meant to be called ONCE. Calling it again (e.g. the user changes
        # the IP) without tearing down the previous attempt stacks threads that all share
        # one UDP socket, racing into OSError EOPNOTSUPP. So always disconnect first.
        self.ip = ip
        if self._started:
            try:
                self.switcher.disconnect()
            except Exception:
                pass
            self._started = False
        self.switcher.connect(ip)
        self._started = True

    def disconnect(self):
        if self._started:
            try:
                self.switcher.disconnect()
            except Exception:
                pass
            self._started = False
        self.connected = False
        self.current_input = None

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

    # NOTE: no reconnect loop here on purpose. PyATEMMax's comms thread keeps the
    # connection alive and retries forever after a single connect(), so an external
    # reconnect loop only stacks duplicate comms threads (the EOPNOTSUPP bug).
