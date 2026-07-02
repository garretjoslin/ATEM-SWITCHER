# app/smoke_test.py
"""
Run this against real ATEM hardware before trusting the full app:

    python -m app.smoke_test <atem-ip> [atem-input-to-cut-to]

Connects, prints firmware/model info and the input list, then issues one cut
and one auto-transition on the given input (defaults to input 2, assumed
harmless -- change if input 2 is live on your switcher).
"""
import sys
import time

from app.atem_controller import AtemController


def main():
    if len(sys.argv) < 2:
        print("usage: python -m app.smoke_test <atem-ip> [atem-input]")
        sys.exit(1)

    ip = sys.argv[1]
    test_input = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    controller = AtemController()
    print(f"connecting to {ip} ...")
    controller.connect(ip)

    deadline = time.time() + 10
    while not controller.connected and time.time() < deadline:
        time.sleep(0.2)

    if not controller.connected:
        print("FAILED to connect within 10s")
        sys.exit(1)

    print("connected.")
    print("switcher info:", controller.switcher.atemModel, controller.switcher.protocolVersion)
    print("inputs:")
    for key, value in controller.switcher.inputProperties.items():
        print(f"  {key}: {getattr(value, 'name', value)}")

    print(f"issuing cut to input {test_input} ...")
    controller.cut_to(test_input)
    time.sleep(1)

    print(f"issuing auto-transition to input {test_input + 1} ...")
    controller.auto_to(test_input + 1)
    time.sleep(1)

    print("smoke test complete.")


if __name__ == "__main__":
    main()
