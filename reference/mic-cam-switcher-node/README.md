# Mic → Cam Switcher

Automatic audio-driven camera switching for a Blackmagic ATEM, decoupled from your
main production switcher. Runs as a local Node.js app with a web UI you open in a
browser on the same machine (or any machine on the same network).

## What it does

- Reads live levels from up to 8 mics (via a multichannel audio interface — your
  Sound Devices box, or Dante Virtual Soundcard both work the same way here).
- You assign each mic to a camera (many-to-one is fine — e.g. 3 mics on one wide shot).
- Tunable per-mic threshold, plus global attack/release/hold/hysteresis so it doesn't
  chatter on breath sounds or brief pauses.
- Optional "crosstalk" bias: if two people talk within a short window of each other,
  it cuts to a designated wide/group shot instead of ping-ponging between them.
- Sends Cut or Auto-transition commands to the ATEM over the network (standard
  ATEM UDP control, port 9910).
- Presets: save/load different mic/camera/threshold setups per room or event type.

## Requirements

- Node.js 18+
- The machine needs network access to the ATEM (same subnet or routed).
- Your audio source needs to show up as a standard multichannel input device to the OS:
  - **Sound Devices interface**: install its driver (ASIO on Windows, class-compliant
    on macOS) — it'll show up as a normal input device.
  - **Dante**: install **Dante Virtual Soundcard** (or use a Dante-to-USB/AVB bridge) —
    same deal, it appears as a system audio device once installed.
  - **Direct into the ATEM**: see the "ATEM-direct mics" note below — this path is
    experimental and needs validation against your specific model/firmware.

`naudiodon2` (the audio capture library) compiles native bindings on install. If it
fails to build:
- **macOS**: `xcode-select --install`
- **Windows**: install "Desktop development with C++" via Visual Studio Build Tools
- **Linux**: `sudo apt install libasound2-dev build-essential`

## Setup

```bash
npm install
npm start
```

Then open `http://localhost:4590` in a browser on that machine.

1. Enter the ATEM's IP and hit **Connect** — the status dot goes green when connected.
2. Under **Audio Device**, pick your interface from the dropdown, set channel count
   (8 for your setup) and sample rate, then **Apply & Restart Capture**.
3. For each mic strip: name it, set which input channel it's on, set a threshold
   (drag by eyeballing the live meter — the white line is your threshold), and pick
   which camera it should cut to.
4. Set your cameras' ATEM input numbers under **Cameras**.
5. Tune **Global Timing**:
   - **Attack** — how long a mic must stay above threshold before it's considered
     "talking." Higher = fewer false triggers on coughs/taps, but slightly laggier cuts.
   - **Release hold** — how long a mic stays "active" after dropping below threshold.
     This is what keeps it from cutting away during natural speech pauses.
   - **Min shot hold** — hard floor on how long any shot stays up before it can be
     cut away from, regardless of audio. Prevents rapid-fire cutting.
   - **Hysteresis** — how many dB louder a competing mic needs to be before it steals
     the cut from whoever's currently active. Higher = more stable, less twitchy
     between two people at similar volume.
   - **Crosstalk window / bias camera** — if two mics start talking within this
     window of each other, cut to the bias camera (your group/wide shot) instead of
     picking one.
6. Toggle **Auto-Switch Active** on when you want the engine actually cutting the
   ATEM. Leave it off to just watch levels/thresholds while you dial things in — the
   meters and threshold lines still update live either way.
7. **Save Config** persists your settings. Use **Presets** to save named setups you
   can switch between (different rooms, panel vs. interview format, etc).

## ATEM-direct mics (experimental)

If mics are wired straight into the ATEM's own audio inputs rather than through your
computer, `src/audio/atemFairlightSource.js` is a starting point for pulling levels
directly from the ATEM instead of a system audio device — but live per-channel meter
data isn't consistently exposed across ATEM models/firmware in the reverse-engineered
protocol. It's wired into the mic's `sourceType: "atem"` option in the config, but
will need testing/adjustment against your actual hardware.

The reliable workaround: split or tap the same mic feed into your Sound Devices
interface as well (most Sound Devices units have looped/aux outs for exactly this),
and use `sourceType: "system"` for that mic instead. Same UI, same engine, just a
different level source.

## Notes

- The engine always calls `setPreviewInput` + `cut`/`autoTransition` on ME (mix
  effect bus) 0. If you're running a multi-M/E ATEM and want this on a different
  bus, that's a one-line change in `src/atemController.js`.
- Config lives in `config/live.json` once you save; `config/default.json` is the
  fallback template and won't be overwritten by the app.
- This is fully separate from your production ATEM control — it just issues its own
  cut/auto commands over the network, same as any other ATEM control surface would.
