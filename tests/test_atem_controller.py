# tests/test_atem_controller.py
# Unit-tests the AtemController's connect/reconnect LOGIC with a fake switcher — this is
# pure wrapper logic (thread lifecycle), not hardware I/O, so it stays within the design
# spec's "hardware modules aren't unit-tested" boundary. Regression guard for the
# EOPNOTSUPP thread-stacking bug: PyATEMMax.connect() spawns comms threads and must be
# torn down before reconnecting.
import PyATEMMax
import pytest


class _FakeEvents:
    connect = "connect"
    disconnect = "disconnect"


class _FakeAtemNS:
    events = _FakeEvents()


class FakeSwitcher:
    def __init__(self):
        self.atem = _FakeAtemNS()
        self.calls = []

    def registerEvent(self, event, cb):
        pass

    def connect(self, ip):
        self.calls.append(("connect", ip))

    def disconnect(self):
        self.calls.append(("disconnect",))


@pytest.fixture
def controller(monkeypatch):
    fake = FakeSwitcher()
    monkeypatch.setattr(PyATEMMax, "ATEMMax", lambda: fake)
    from app.atem_controller import AtemController
    return AtemController(), fake


def test_first_connect_does_not_disconnect(controller):
    c, fake = controller
    c.connect("192.168.1.240")
    assert fake.calls == [("connect", "192.168.1.240")]


def test_reconnect_tears_down_previous_attempt_first(controller):
    c, fake = controller
    c.connect("192.168.1.240")
    c.connect("10.0.0.5")  # user changes the IP and reconnects
    assert fake.calls == [
        ("connect", "192.168.1.240"),
        ("disconnect",),
        ("connect", "10.0.0.5"),
    ]


def test_disconnect_before_any_connect_is_safe(controller):
    c, fake = controller
    c.disconnect()  # no comms threads were ever started -> must not call switcher.disconnect()
    assert fake.calls == []
    assert c.connected is False
