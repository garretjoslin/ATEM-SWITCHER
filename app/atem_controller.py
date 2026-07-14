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
        # forever — it's meant to be called ONCE. Reconnecting a *reused* ATEMMax (e.g.
        # the app connects to the configured IP at startup, then the user Connects to the
        # real IP) leaves stale socket + parser-buffer state, which manifests as either
        # OSError EOPNOTSUPP (stacked threads on one socket) or IndexError deep in
        # PyATEMMax's packet parser (_handle_pin). So on every reconnect we tear the old
        # switcher down and build a brand-new one — giving the reconnect the same pristine
        # state as a first-ever connect (which is known-good).
        self.ip = ip
        if self._started:
            try:
                self.switcher.disconnect()
            except Exception:
                pass
            self.switcher = PyATEMMax.ATEMMax()
            self.switcher.registerEvent(self.switcher.atem.events.connect, self._on_connect)
            self.switcher.registerEvent(self.switcher.atem.events.disconnect, self._on_disconnect)
        self.connected = False
        self.current_input = None
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
