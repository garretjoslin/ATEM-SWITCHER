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

## Quick start (one command)

```bash
./run.sh
```

Creates the virtualenv and installs dependencies on first run, then starts the server on
`http://127.0.0.1:4590`. Override host/port: `HOST=0.0.0.0 PORT=8080 ./run.sh`
(use `0.0.0.0` to reach it from other devices on the LAN).

## Setup (manual)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 4590
```

Open `http://localhost:4590`. Use Python 3.10+ (the code uses 3.10+ syntax); on Linux also
install PortAudio for audio capture: `sudo apt install libportaudio2`.

## Deploying & updating

Install on a new machine:

```bash
git clone https://github.com/garretjoslin/ATEM-SWITCHER.git
cd ATEM-SWITCHER
./run.sh
```

Push a revision (dev machine):

```bash
# edit files, then:
.venv/bin/python -m pytest -q          # keep the suite green
git add -A && git commit -m "describe the change"
git push
```

Pull a revision (deployed machine):

```bash
git pull
.venv/bin/pip install -r requirements.txt   # only if requirements.txt changed
./run.sh                                     # restart (Ctrl-C the old one first)
```

For fast local iteration, run with auto-reload so backend edits restart the server:
`.venv/bin/python -m uvicorn app.main:app --reload --port 4590` (frontend edits under
`web/` just need a browser refresh). Per-machine settings live in `config/live.json`
(gitignored), so pulling never clobbers a machine's device/IP selection; presets in
`config/presets/` are tracked and shared across machines.

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

## Troubleshooting

**ATEM won't connect (status dot stays red).** Control is over IP/UDP via PyATEMMax, so
the machine must reach the switcher on the network. Check, in order:

1. Confirm the ATEM's actual IP (Blackmagic ATEM Setup, or the unit's front-panel/menu).
   The default in `config/default.json` is `192.168.1.240` — likely not yours.
2. `ping <atem-ip>` from this machine. No reply → it's a network/subnet issue, not the app
   (same subnet? right NIC? no VLAN/firewall between them?).
3. Run the standalone probe — it prints exactly what the connection is doing:
   `.venv/bin/python -m app.smoke_test <atem-ip>`. If this can't connect, the app can't either.
4. Give it a few seconds — connection is asynchronous and the UI polls status every ~4s.

## Roadmap / not yet implemented

- **USB control of the ATEM.** The current control path is Ethernet/IP (PyATEMMax). USB
  *audio* interfaces already work today — they enumerate as ordinary PortAudio input devices
  and are selectable in the Audio Device panel. USB *switcher control* is a separate protocol
  and would be added as an alternate transport behind the same `AtemController` interface.
