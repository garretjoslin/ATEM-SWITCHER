# Mic → Cam Auto-Switcher for ATEM (Python) — Design Spec

Date: 2026-06-30

## Goal

A standalone Python app, separate from the main production switcher, that auto-cuts a
Blackmagic ATEM based on live mic levels. Web UI for assignment/tuning. Supports 0–10
mics and 0–10 cameras, configurable per install. Targets ATEM Constellation (primary,
multi-M/E) and ATEM Mini Pro (smaller setups) without model-specific branching.

This is a ground-up Python port of an existing working Node.js prototype
(`mic-cam-switcher`), preserving its exact switch-decision behavior, plus several
additions: flexible mic/camera counts, a live latency readout, an optional
timecode-driven DaVinci Resolve EDL export for post-production touch-up of mis-cuts,
and a set of auto-switching quality improvements (adaptive false-trigger rejection,
calibration tooling, runtime robustness) covered in their own section below.

## Stack

- Python 3.10+
- **PyATEMMax** — pure-Python ATEM control, no native deps. Verified API surface:
  `switcher.connect(ip)`, `switcher.connected` (bool), `switcher.registerEvent(switcher.atem.events.connect / .disconnect, cb)`,
  `switcher.setPreviewInputVideoSource(meIndex, atemInput)`, `switcher.execCutME(meIndex)`,
  `switcher.execAutoME(meIndex)`.
- **sounddevice** (PortAudio bindings, prebuilt wheels) for multichannel audio capture —
  replaces the Node prototype's `naudiodon2`, which requires a native build toolchain.
- **FastAPI** + built-in WebSocket support for the backend API + live meter streaming.
- Plain HTML/CSS/JS frontend, served as static files by FastAPI.

## Confirmed finding: no live timecode over the ATEM protocol

Checked PyATEMMax's switcher state tree directly — there is no timecode field exposed
anywhere in the network protocol. The app cannot query the ATEM for "what timecode is
it right now." This is why the timecode subsystem (below) decodes LTC locally instead
of trying to read it from the switcher.

## Project layout

```
app/
  main.py                     FastAPI app: REST routes + /ws endpoint
  config.py                   load/save JSON config, preset save/load
  atem_controller.py          PyATEMMax wrapper: cut_to(input) / auto_to(input), ME-bus aware
  switch_engine.py            pure-logic state machine, no I/O — unit-testable headless
  audio/
    system_audio_source.py    sounddevice capture -> per-channel dBFS, pushed to asyncio.Queue
    dsp.py                     speech-band-pass filter + peak tracking used before dBFS calc
    atem_fairlight_source.py  experimental stub (see "Deferred / experimental" below)
  timecode/
    ltc_reader.py             optional LTC decoder on a dedicated audio channel
  export/
    edl_export.py             builds a CMX3600 EDL from a time-range slice of the switch log
  switch_log.py                append-only persistence of every cut event
  smoke_test.py                standalone script: connect, list inputs, cut, auto — run
                                against real hardware before trusting the full app
web/
  index.html / app.js / style.css
config/
  default.json                 template, never overwritten by the app
  live.json                    working copy (gitignored)
  presets/*.json
logs/
  switch_log.jsonl             append-only cut history, read by the EDL exporter
requirements.txt
README.md
```

`switch_engine.py` takes no ATEM/audio dependencies — it consumes a stream of per-mic
level readings and yields switch decisions, which is what makes it unit-testable
without any hardware attached.

## Config data model

```json
{
  "atem": { "ip": "192.168.1.240", "meIndex": 0 },
  "audioDevice": { "type": "system", "deviceId": null, "sampleRate": 48000, "channelCount": 8 },
  "timecode": { "enabled": false, "channelIndex": null },
  "enabled": false,
  "showLatencyReadout": true,
  "global": {
    "attackMs": 150,
    "releaseHoldMs": 2500,
    "minShotHoldMs": 2000,
    "hysteresisDb": 4,
    "crosstalkWindowMs": 400,
    "crosstalkBiasCameraId": "cam1",
    "transition": { "type": "cut", "autoDurationFrames": 15 },
    "timelineFps": 29.97,
    "advanced": {
      "noiseFloorAdaptive": { "enabled": true, "marginDb": 10, "adaptWindowSec": 30 },
      "speechBandFilter": { "enabled": true, "lowHz": 300, "highHz": 3400 },
      "audioWatchdogMs": 500,
      "clippingWarnDb": -1
    }
  },
  "cameras": [
    { "id": "cam1", "name": "Cam 1", "atemInput": 1, "isoReelName": "Input 1" }
    // ... up to 10 entries
  ],
  "mics": [
    { "id": "mic1", "name": "Mic 1", "enabled": true, "thresholdDb": -35, "priority": 1, "cameraId": "cam1" }
    // ... up to 10 entries; position in this array = physical audio channel
  ]
}
```
(Abbreviated to one entry each for illustration — `default.json` ships with 8 mics / 6 cameras, per the earlier Node prototype's template.)

Notes on changes from the Node prototype's schema:

- `atem.meIndex` is new (default `0`) — targets a specific Mix Effect bus on a
  multi-M/E Constellation. Mini Pro / single-M/E setups leave it at `0`.
- Mic entries **no longer have a `channelIndex` field.** A mic's physical audio
  channel is always its position in the `mics` array (mic at index 0 reads channel 0,
  etc.) — this is a fixed 1:1 binding to the physical input port, so it can't be
  misconfigured. The `name` field remains freely editable as a display label,
  independent of that port binding. Adding a mic appends the next port; removing a
  mic shifts every subsequent mic's port assignment down by one — operators re-patch
  cables to match after a removal, or only add/remove from the end to avoid needing to.
  If a selected audio device has fewer physical channels than configured mics, the
  extra mics simply read no signal (flatlined meter) rather than erroring.
- `mics` and `cameras` are both capped at 10 entries, floor of 0. `default.json` still
  ships pre-populated with 8 mics / 6 cameras as a starting template; nothing hardcodes
  that count.
- `timecode` block is new and optional. See "Timecode subsystem" below.
- `showLatencyReadout` is new — toggles the "ms since trigger" readout in the UI log.
- `global.timelineFps` and each camera's `isoReelName` are new, used only by the EDL
  exporter.
- `global.advanced` is new — see "Auto-switching quality" below. Every sub-feature in
  it defaults to a value that preserves the Node prototype's original flat-RMS
  behavior when set to `enabled: false`.
- All other field names (`enabled`, `thresholdDb`, `priority`, `crosstalkBiasCameraId`,
  `crosstalkWindowMs`, `transition.type/autoDurationFrames`) are unchanged from the
  Node prototype's `config/default.json`, so existing presets remain structurally
  compatible aside from the removed `channelIndex` field.

## ATEM & audio compatibility

- `atem_controller.py` targets the generic ATEM protocol via `PyATEMMax.ATEMMax()` —
  no model-specific branching. Camera → input mapping is just an integer the user
  assigns (`atemInput`), so it's naturally portable across Mini Pro (fewer inputs) and
  Constellation (many inputs, multiple M/Es).
- `smoke_test.py` connects, prints firmware/model info and the input list, then issues
  one `cut` and one `auto` on a harmless input. Run this against the real switcher
  before relying on the full app — this environment has no network access to the
  hardware to do that validation itself.
- Audio: no special-casing for Sound Devices interfaces vs. Dante Virtual Soundcard —
  both present as ordinary PortAudio devices. `system_audio_source.py` enumerates
  `sounddevice.query_devices()` and the UI picks device + channel count.

## Switch engine algorithm (ported from the Node prototype's `switchEngine.js`)

Per mic, per audio tick (level computed as smoothed dBFS):

- A mic becomes `talking = true` once its level has stayed at/above `thresholdDb`
  continuously for `attackMs` (rejects transient spikes).
- A mic becomes `talking = false` once its level has stayed below `thresholdDb`
  continuously for `releaseHoldMs` (rejects mid-sentence breath pauses).
- `hysteresisDb` is **not** a second threshold — it's a stickiness margin used only
  during winner selection: a challenger mic can only steal the shot from the
  currently active mic if it beats the active mic's level by at least `hysteresisDb`,
  and only while the active mic is still `talking`.
- Winner selection among all currently-`talking`, `enabled` mics: highest `priority`
  wins; ties broken by highest level.
- **Crosstalk bias:** if 2+ *distinct* mics started talking within `crosstalkWindowMs`
  of each other, cut to the dedicated `crosstalkBiasCameraId` (a wide/group shot)
  instead of picking either individual mic's camera.
- `minShotHoldMs` gates only actual ATEM camera changes — if the winning mic's
  camera is already the one on air, `activeMicId` updates with no ATEM call and no
  hold-check. If nobody is `talking`, hold the last shot indefinitely.
- The global `enabled` flag: when false, the engine still computes/broadcasts levels
  for the UI meters, it just never calls the ATEM.
- Transition style is global: `"cut"` or `"auto"` (with `autoDurationFrames`).

## Auto-switching quality

Everything here is additive and individually toggleable via `global.advanced` —
turning a sub-feature off restores exactly the Node prototype's original flat-RMS
behavior for that piece. All of it is hidden behind a closed-by-default "Advanced"
disclosure in the UI so day-to-day use isn't cluttered.

**Adaptive noise-floor threshold** (`advanced.noiseFloorAdaptive`) — a per-mic
tracker, implemented as pure logic inside `switch_engine.py` (so it stays
unit-testable with synthetic level sequences, no audio I/O needed). It maintains a
slowly-adapting noise floor sampled only during periods a mic is *not* `talking`,
over a rolling `adaptWindowSec` window, and derives the effective threshold each
tick as `noiseFloor + marginDb`. This replaces the static `thresholdDb` comparison
when enabled, so the engine keeps working correctly as ambient noise changes (e.g.
HVAC cycling on) without manual re-tuning mid-show. When disabled, `thresholdDb` is
used exactly as in the base algorithm.

**Speech-band pre-filtering** (`advanced.speechBandFilter`) — a light band-pass
(`lowHz`–`highHz`, default 300Hz–3.4kHz) applied per channel in
`audio/dsp.py` before RMS/dBFS is computed in `system_audio_source.py`. This changes
what level number reaches the engine (de-emphasizing low-frequency thumps and
high-frequency hiss/clicks relative to speech energy) — it does not change any
engine logic. Disabling it reverts to full-band RMS.

**Calibration tooling** — `POST /api/calibrate/{micId}` runs a synchronous ~6-7s
sequence against live audio: ~3s sampling ambient noise floor ("stay quiet"), then
~3s sampling normal speech level ("talk normally"), returning
`{ noiseFloorDb, speechLevelDb, suggestedThresholdDb }` where the suggestion is
roughly 60% of the way from floor to speech peak. The UI times its on-screen prompts
("Listening... stay quiet" / "Now talk normally") to match the server-side phases,
then fills the suggested value into that mic's threshold field for the operator to
accept or adjust — it never applies a threshold without confirmation.

**Runtime robustness:**
- *Audio watchdog* — if `system_audio_source` hasn't delivered a fresh levels update
  within `advanced.audioWatchdogMs` (default 500ms), the engine treats that tick as a
  distinct `stalled` state rather than silence: it holds the last shot (never cuts to
  the crosstalk-bias camera or anywhere else based on stale/zero data) and the `/ws`
  `tick` snapshot carries a `stalled: true` flag so the UI can show a clear "AUDIO
  STALLED" warning instead of implying nobody's talking.
- *Mic clipping detection* — `system_audio_source.py` tracks per-channel peak
  alongside RMS; sustained peaks at/above `advanced.clippingWarnDb` (default -1 dBFS)
  set a `clipping: true` flag per mic in the tick snapshot. This is purely an
  operator hint (fix gain staging) and never affects switching decisions.
- ATEM reconnect-with-backoff and pause-while-disconnected (already specified above)
  are the third leg of runtime robustness.

## REST API + WebSocket (ported from the Node prototype's `server.js`)

- `GET/POST /api/config` — load/replace full config, persists to `config/live.json`.
- `POST /api/config/apply-audio` — restart audio capture with current config.
- `GET /api/devices` — list available sounddevice input devices.
- `GET /api/status` — ATEM connection status + whether audio capture is running.
- `POST /api/atem/connect` — set IP, persist, connect.
- `POST /api/engine/enabled` — toggle master auto-switch on/off.
- `GET /api/presets`, `POST/GET /api/presets/{name}`, `POST /api/presets/{name}/load`.
- `POST /api/calibrate/{micId}` — new. Runs the ~6-7s noise-floor/speech-level
  calibration sequence for one mic (see "Auto-switching quality") and returns a
  suggested threshold.
- `POST /api/timecode/mark-start` — new. Records the current epoch as the session's
  `recordStartEpoch`, used by the EDL exporter's wall-clock fallback (see below).
- `GET /api/export/edl?from=...&to=...` — new. Returns a CMX3600 EDL file built from
  the switch log in that time range.
- `/ws` — broadcasts `tick` (per-mic level + talking state snapshot) and `switch`
  (cut event) messages, same shapes as the Node prototype.

## Web UI

Same layout as the Node prototype's `index.html`/`app.js`/`style.css`: mic strips
(live meter + threshold line + talking indicator + camera assignment), camera strips
(name + ATEM input + ISO reel name), global timing controls, presets panel, master
enable toggle, ATEM connect/status indicator. Changes:

- Mic strips lose the "channel index" number field (now implicit/positional). Add/remove
  buttons on the mic and camera lists, capped at 10 each.
- Each mic strip gets a "Calibrate" button (walks through the stay-quiet/talk-normally
  sequence and fills in the suggested threshold) and small "CLIP" / "STALLED"
  indicators that light up per the flags in the `tick` snapshot.
- Switch-event log entries show a "ms since trigger" latency value next to each cut,
  gated by `showLatencyReadout` (default on, one checkbox to disable).
- New closed-by-default **Advanced** disclosure under Global Timing, housing the
  `global.advanced` knobs (noise-floor margin/window, band-pass on/off + band edges,
  watchdog timeout, clip warning level) — opening it doesn't change any behavior,
  it's purely about not cluttering the simple case.
- New **Export Timeline** panel: time-range picker, an "Export Timeline (.edl)" button
  that downloads the file, a status line showing which timecode mode is active
  ("Timecode: LTC decode (live)" or "Timecode: wall-clock estimate — mark recording
  start when you begin ISO recording"), and a "Mark Recording Start" button (shown
  only when timecode is disabled).

## Timecode subsystem (optional)

Timecode is an accuracy upgrade, not a requirement — the entire app, including export,
functions with it off.

- **Off (default):** `timecode.enabled = false`. No LTC reader starts. Switch log
  entries carry only epoch timestamps.
- **On:** route a spare channel of a jam-synced LTC generator into an unused channel
  on the same audio interface used for mic capture. `ltc_reader.py` decodes it in
  real time; every switch-log entry is tagged with the actual decoded timecode at
  the moment of the cut.
- **Caveat to verify against the real hardware (not verifiable from this
  environment):** this only produces accurate EDLs end-to-end if the ATEM itself is
  also genlocked/timecode-referenced to that same master LTC source, so its ISO
  recordings' embedded timecode matches what the app decodes. This is a
  switcher-settings question specific to the Constellation unit in use.

## EDL export (CMX3600)

- Every cut is appended to `logs/switch_log.jsonl`: `{cameraId, atemInput, epochMs, timecode | null}`.
- `edl_export.py` takes a time range, and for each cut, computes source in/out:
  - **Timecode mode:** use the decoded `timecode` values directly.
  - **Wall-clock fallback:** `sourceTimecode = (epochMs - recordStartEpoch)` converted
    to frames at `global.timelineFps`, counting from `00:00:00:00`. Requires
    `POST /api/timecode/mark-start` to have been called for the session; if it
    wasn't, the export endpoint returns an error asking the user to mark a start
    point first.
  - Record in/out are the running cumulative position in the assembled timeline.
  - Reel name per event = the camera's configured `isoReelName`, which must match
    the actual ATEM ISO recording's filename/reel for Resolve to auto-conform.
- Export is manual only (an explicit UI button / API call), never automatic.

## Error handling

- ATEM disconnect: `atem_controller.py` auto-retries with backoff, broadcasts status
  over `/ws`; the switch engine stops issuing cuts while disconnected (no queued
  commands fire on reconnect).
- Audio device open failure: reported via REST error, doesn't crash the FastAPI
  process; the engine simply has no levels until a valid device is picked.
- LTC decode loss (timecode enabled but signal drops): reported via `/api/status`,
  export falls back to requiring a fresh "Mark Recording Start" for that stretch.

## Testing

- `switch_engine.py` is pure logic with no I/O — real pytest unit tests feed it
  synthetic level sequences and assert cut decisions/timing for each mechanism
  individually (attack, release-hold, hysteresis stickiness, priority tie-breaks,
  crosstalk-window bias, min-shot-hold gating, adaptive noise-floor threshold,
  audio-stalled handling) **and** their interactions (e.g. crosstalk firing while
  min-shot-hold is still active; hysteresis blocking a steal right as release-hold
  expires; adaptive threshold enabled together with crosstalk bias).
- `edl_export.py` is pure logic given a switch log — unit tests feed synthetic logs
  in both timecode and wall-clock-fallback modes and assert the generated EDL text.
- `audio/dsp.py` (band-pass filter, peak tracking) is pure signal processing given
  raw sample arrays — unit tests feed synthetic tones/impulses and assert the filter
  attenuates out-of-band energy and peak detection flags clipping correctly.
- `atem_controller.py`, `system_audio_source.py`, and `ltc_reader.py` are
  hardware-dependent — validated via `smoke_test.py` and manual testing against real
  gear, not unit tests.

## Deferred / experimental

- `atem_fairlight_source.py`: same experimental status as the Node prototype's
  `atemFairlightSource.js`. PyATEMMax exposes Fairlight mixer *state* (gain, EQ,
  dynamics) but not consistent live meter ticks across ATEM firmware. Kept as a
  documented stub; the reliable path is tapping mics into the audio interface too.
- DaVinci export currently targets CMX3600 EDL only (straight cuts, no transitions
  beyond hard cut/dissolve). AAF/FCPXML export is out of scope unless a future need
  for richer metadata (multicam grouping, per-clip color notes) comes up.
