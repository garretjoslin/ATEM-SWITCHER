# Mic → Cam ATEM Auto-Switcher (Python)

Standalone audio-driven camera switcher for a Blackmagic ATEM, separate from your
main production switcher. Reads live mic levels from a multichannel audio interface
and auto-cuts the ATEM to the talking person's camera. Web UI for assignment/tuning.
Python port of the Node.js `mic-cam-switcher` prototype (see `reference/`).

## Requirements

- Python 3.10+
- Network access to the ATEM (same subnet or routed; standard ATEM UDP control).
- A multichannel input device visible to the OS (Sound Devices interface, or Dante
  Virtual Soundcard — both appear as ordinary PortAudio devices).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 4590
```

Open `http://localhost:4590`.

## Before trusting it live: run the smoke test

```bash
python -m app.smoke_test <atem-ip>
```

Connects, prints model/input info, and issues one cut + one auto on a harmless input.
Run this against the real switcher first — the dev environment can't reach hardware.

## Usage

1. Enter the ATEM IP, hit **Connect** (status dot goes green).
2. Under **Audio Device**, pick the interface, set channel count + sample rate,
   **Apply & Restart Capture**.
3. Per mic: name it, set threshold (or hit **Calibrate** for a suggestion), pick its
   camera. A mic's physical channel = its position in the list (mic 1 = channel 0).
4. Set cameras' ATEM inputs and ISO reel names (reel names must match the ATEM ISO
   recording filenames for Resolve auto-conform).
5. Tune **Global Timing**; expand **Advanced** for adaptive noise floor, speech-band
   filter, watchdog, and clip warning.
6. Toggle **Auto-Switch Active** to let the engine cut the ATEM. Off = meters only.
7. **Save Config** / **Presets** to persist and switch between setups.

## Timecode & EDL export

Optional. With `timecode.enabled` off (default), export uses a wall-clock estimate —
click **Mark Recording Start** when you start ISO recording. With it on, route a
jam-synced LTC feed into a spare channel and set its channel index; cuts are tagged
with decoded timecode. Accurate end-to-end EDLs require the ATEM itself to be
genlocked/timecode-referenced to the same master LTC (verify on your Constellation).

Export via the **Export Timeline** panel → downloads a CMX3600 `.edl`.

## Testing

`pytest` — pure-logic modules (switch engine, DSP, EDL export, LTC bit-decode,
config, calibration) are fully unit-tested. Hardware-facing modules (ATEM control,
audio capture, LTC analog decode) are validated via `smoke_test.py` and manual
testing against real gear.

## Config

`config/default.json` is the template (never overwritten). `config/live.json` is the
working copy (gitignored), written on save. Presets live in `config/presets/`.
