let config = null;
let ws = null;
let devices = [];  // cached /api/devices list, so the device picker can read channel counts

const dbToPercent = (db) => {
  const clamped = Math.max(-60, Math.min(0, db));
  return ((clamped + 60) / 60) * 100;
};

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

// Small DOM helpers — never interpolate user data into markup strings.
function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => {
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k in node) node[k] = v;
    else node.setAttribute(k, v);
  });
  children.forEach((c) => node.appendChild(c));
  return node;
}

function cameraSelect(className, selectedId, includeNone = false) {
  const sel = el('select', { class: className });
  if (includeNone) sel.appendChild(el('option', { value: '', text: '(none)' }));
  config.cameras.forEach((c) => {
    const opt = el('option', { value: c.id, text: c.name });
    if (c.id === selectedId) opt.selected = true;
    sel.appendChild(opt);
  });
  return sel;
}

async function loadAll() {
  config = await fetchJSON('/api/config');
  devices = await fetchJSON('/api/devices').catch(() => []);
  renderHeader();
  renderAudioDevice();
  renderMics();
  renderCameras();
  renderGlobal();
  renderAdvanced();
  await refreshPresets();
  connectWS();
  refreshStatus();
  setInterval(refreshStatus, 4000);
}

function renderHeader() {
  document.getElementById('atemIp').value = config.atem.ip || '';
  document.getElementById('masterEnable').checked = !!config.enabled;
}

function renderAudioDevice() {
  const sel = document.getElementById('deviceSelect');
  sel.replaceChildren(el('option', { value: '', text: 'Default input' }));
  devices.forEach((d) => {
    const opt = el('option', { value: String(d.id), text: `${d.name} (${d.maxInputChannels} ch)` });
    if (config.audioDevice.deviceId === d.id) opt.selected = true;
    sel.appendChild(opt);
  });
  const channelInput = document.getElementById('channelCount');
  channelInput.value = config.audioDevice.channelCount;
  document.getElementById('sampleRate').value = config.audioDevice.sampleRate;

  // Selecting a device sets the channel count from that device and populates one
  // channel strip per physical channel (channel i = strip i). Existing strips keep
  // their thresholds/camera assignments; extra strips are added or trimmed to fit.
  sel.onchange = (e) => {
    const dev = devices.find((d) => String(d.id) === e.target.value);
    config.audioDevice.deviceId = dev ? dev.id : null;
    if (dev) {
      setChannelCount(dev.maxInputChannels);
    }
  };
  // Manually editing the channel count also re-populates the strips to match.
  channelInput.onchange = (e) => setChannelCount(parseInt(e.target.value, 10));
}

// Resize config.mics (the per-channel strips) to `n`, preserving existing entries.
function setChannelCount(n) {
  if (!Number.isFinite(n) || n < 0) return;
  config.audioDevice.channelCount = n;
  document.getElementById('channelCount').value = n;
  while (config.mics.length < n) {
    const idx = config.mics.length + 1;
    config.mics.push({
      id: nextId(config.mics, 'ch'),
      name: `Channel ${idx}`,
      enabled: true,
      thresholdDb: -35,
      priority: 1,
      cameraId: config.cameras[0] ? config.cameras[0].id : null,
    });
  }
  while (config.mics.length > n) config.mics.pop();
  renderMics();
}

function renderMics() {
  const container = document.getElementById('micStrips');
  container.replaceChildren();
  config.mics.forEach((mic) => {
    const nameInput = el('input', { type: 'text', class: 'mic-name', value: mic.name });
    nameInput.addEventListener('input', (e) => (mic.name = e.target.value));

    const enabledInput = el('input', { type: 'checkbox', class: 'mic-enabled', checked: mic.enabled });
    enabledInput.addEventListener('change', (e) => (mic.enabled = e.target.checked));
    const enabledLabel = el('label', {}, [enabledInput, document.createTextNode(' on')]);
    enabledLabel.setAttribute('style', 'font-size:11px;color:#9096a3;display:flex;gap:4px;align-items:center;');

    const meterFill = el('div', { class: 'meter-fill' });
    meterFill.style.width = '0%';
    const meterThreshold = el('div', { class: 'meter-threshold' });
    meterThreshold.style.left = `${dbToPercent(mic.thresholdDb)}%`;
    const meterWrap = el('div', { class: 'meter-wrap' }, [meterFill, meterThreshold]);

    const thresholdInput = el('input', { type: 'number', class: 'mic-threshold', value: mic.thresholdDb, step: '1', title: 'Threshold dB' });
    thresholdInput.addEventListener('input', (e) => {
      mic.thresholdDb = parseFloat(e.target.value);
      meterThreshold.style.left = `${dbToPercent(mic.thresholdDb)}%`;
    });

    const camSel = cameraSelect('mic-camera', mic.cameraId);
    camSel.addEventListener('change', (e) => (mic.cameraId = e.target.value));

    const calibrateBtn = el('button', { class: 'mic-calibrate', text: 'Calibrate' });

    const clipBadge = el('span', { class: 'badge clip', text: 'CLIP' });
    const stalledBadge = el('span', { class: 'badge stalled', text: 'STALL' });
    const badges = el('div', { class: 'mic-badges' }, [clipBadge, stalledBadge]);

    const strip = el('div', { class: 'mic-strip' }, [
      nameInput, enabledLabel, meterWrap, thresholdInput, camSel, calibrateBtn, badges,
    ]);
    strip.dataset.micId = mic.id;
    calibrateBtn.addEventListener('click', () => calibrateMic(mic, strip));
    container.appendChild(strip);
  });
}

function renderCameras() {
  const container = document.getElementById('cameraStrips');
  container.replaceChildren();
  config.cameras.forEach((cam) => {
    const nameInput = el('input', { type: 'text', class: 'cam-name', value: cam.name });
    nameInput.addEventListener('input', (e) => {
      cam.name = e.target.value;
      renderMics();
      renderGlobal();
    });

    const inputNum = el('input', { type: 'number', class: 'cam-input', value: cam.atemInput, min: '1' });
    inputNum.addEventListener('input', (e) => (cam.atemInput = parseInt(e.target.value, 10)));
    const inputLabel = el('label', {}, [document.createTextNode('ATEM input '), inputNum]);
    inputLabel.setAttribute('style', 'font-size:11px;color:#9096a3;');

    const reelInput = el('input', { type: 'text', class: 'cam-reel', value: cam.isoReelName || '' });
    reelInput.addEventListener('input', (e) => (cam.isoReelName = e.target.value));
    const reelLabel = el('label', {}, [document.createTextNode('ISO reel '), reelInput]);
    reelLabel.setAttribute('style', 'font-size:11px;color:#9096a3;');

    const strip = el('div', { class: 'camera-strip' }, [nameInput, inputLabel, reelLabel]);
    strip.dataset.cameraId = cam.id;
    container.appendChild(strip);
  });
}

function renderGlobal() {
  const g = config.global;
  document.getElementById('attackMs').value = g.attackMs;
  document.getElementById('releaseHoldMs').value = g.releaseHoldMs;
  document.getElementById('minShotHoldMs').value = g.minShotHoldMs;
  document.getElementById('hysteresisDb').value = g.hysteresisDb;
  document.getElementById('transitionType').value = g.transition.type;
  document.getElementById('autoDurationFrames').value = g.transition.autoDurationFrames;
  document.getElementById('crosstalkWindowMs').value = g.crosstalkWindowMs;
  document.getElementById('showLatencyReadout').checked = !!config.showLatencyReadout;

  const biasWrap = document.getElementById('crosstalkBiasCameraId');
  const newSel = cameraSelect('', g.crosstalkBiasCameraId, true);
  newSel.id = 'crosstalkBiasCameraId';
  newSel.onchange = (e) => (g.crosstalkBiasCameraId = e.target.value || null);
  biasWrap.replaceWith(newSel);

  document.getElementById('attackMs').oninput = (e) => (g.attackMs = parseInt(e.target.value, 10));
  document.getElementById('releaseHoldMs').oninput = (e) => (g.releaseHoldMs = parseInt(e.target.value, 10));
  document.getElementById('minShotHoldMs').oninput = (e) => (g.minShotHoldMs = parseInt(e.target.value, 10));
  document.getElementById('hysteresisDb').oninput = (e) => (g.hysteresisDb = parseFloat(e.target.value));
  document.getElementById('transitionType').onchange = (e) => (g.transition.type = e.target.value);
  document.getElementById('autoDurationFrames').oninput = (e) => (g.transition.autoDurationFrames = parseInt(e.target.value, 10));
  document.getElementById('crosstalkWindowMs').oninput = (e) => (g.crosstalkWindowMs = parseInt(e.target.value, 10));
  document.getElementById('showLatencyReadout').onchange = (e) => (config.showLatencyReadout = e.target.checked);
}

function renderAdvanced() {
  const adv = config.global.advanced;
  document.getElementById('noiseFloorAdaptiveEnabled').checked = !!adv.noiseFloorAdaptive.enabled;
  document.getElementById('noiseFloorMarginDb').value = adv.noiseFloorAdaptive.marginDb;
  document.getElementById('noiseFloorAdaptWindowSec').value = adv.noiseFloorAdaptive.adaptWindowSec;
  document.getElementById('speechBandFilterEnabled').checked = !!adv.speechBandFilter.enabled;
  document.getElementById('speechBandLowHz').value = adv.speechBandFilter.lowHz;
  document.getElementById('speechBandHighHz').value = adv.speechBandFilter.highHz;
  document.getElementById('audioWatchdogMs').value = adv.audioWatchdogMs;
  document.getElementById('clippingWarnDb').value = adv.clippingWarnDb;

  document.getElementById('noiseFloorAdaptiveEnabled').onchange = (e) => (adv.noiseFloorAdaptive.enabled = e.target.checked);
  document.getElementById('noiseFloorMarginDb').oninput = (e) => (adv.noiseFloorAdaptive.marginDb = parseFloat(e.target.value));
  document.getElementById('noiseFloorAdaptWindowSec').oninput = (e) => (adv.noiseFloorAdaptive.adaptWindowSec = parseInt(e.target.value, 10));
  document.getElementById('speechBandFilterEnabled').onchange = (e) => (adv.speechBandFilter.enabled = e.target.checked);
  document.getElementById('speechBandLowHz').oninput = (e) => (adv.speechBandFilter.lowHz = parseInt(e.target.value, 10));
  document.getElementById('speechBandHighHz').oninput = (e) => (adv.speechBandFilter.highHz = parseInt(e.target.value, 10));
  document.getElementById('audioWatchdogMs').oninput = (e) => (adv.audioWatchdogMs = parseInt(e.target.value, 10));
  document.getElementById('clippingWarnDb').oninput = (e) => (adv.clippingWarnDb = parseFloat(e.target.value));
}

async function calibrateMic(mic, strip) {
  const btn = strip.querySelector('.mic-calibrate');
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Stay quiet...';
  setTimeout(() => { btn.textContent = 'Now talk...'; }, 3000);
  try {
    const result = await fetchJSON(`/api/calibrate/${encodeURIComponent(mic.id)}`, { method: 'POST' });
    mic.thresholdDb = result.suggestedThresholdDb;
    strip.querySelector('.mic-threshold').value = mic.thresholdDb;
    strip.querySelector('.meter-threshold').style.left = `${dbToPercent(mic.thresholdDb)}%`;
    btn.textContent = `Suggest ${result.suggestedThresholdDb} dB`;
    setTimeout(() => { btn.textContent = original; }, 2500);
  } catch (e) {
    btn.textContent = 'Failed';
    setTimeout(() => { btn.textContent = original; }, 2000);
  } finally {
    btn.disabled = false;
  }
}

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === 'tick') updateMeters(msg.payload);
    if (msg.type === 'switch') logSwitch(msg.payload);
  };
  ws.onclose = () => setTimeout(connectWS, 2000);
}

function updateMeters(snapshot) {
  Object.entries(snapshot.mics).forEach(([micId, m]) => {
    const strip = document.querySelector(`.mic-strip[data-mic-id="${micId}"]`);
    if (!strip) return;
    strip.querySelector('.meter-fill').style.width = `${dbToPercent(m.level)}%`;
    strip.classList.toggle('talking', !!m.talking);
    strip.querySelector('.badge.clip').classList.toggle('active', !!m.clipping);
    strip.querySelector('.badge.stalled').classList.toggle('active', !!snapshot.stalled);
  });

  document.getElementById('stalledIndicator').classList.toggle('hidden', !snapshot.stalled);

  const activeMic = config.mics.find((m) => m.id === snapshot.activeMicId);
  const activeCam = config.cameras.find((c) => c.id === snapshot.activeCameraId);
  document.getElementById('activeMic').textContent = activeMic ? activeMic.name : '—';
  document.getElementById('activeCamera').textContent = activeCam ? activeCam.name : '—';

  document.querySelectorAll('.camera-strip').forEach((elem) => {
    elem.classList.toggle('active', elem.dataset.cameraId === snapshot.activeCameraId);
  });
}

function logSwitch(evt) {
  const cam = config.cameras.find((c) => c.id === evt.cameraId);
  const mic = config.mics.find((m) => m.id === evt.micId);
  const logEl = document.getElementById('log');
  const time = new Date(evt.at).toLocaleTimeString();
  let text = `${time} -> ${cam ? cam.name : evt.cameraId} (${mic ? mic.name : 'shared'})`;
  if (config.showLatencyReadout && evt.latencyMs != null) {
    text += ` [${Math.round(evt.latencyMs)}ms since trigger]`;
  }
  logEl.textContent = text;
}

async function refreshStatus() {
  try {
    const status = await fetchJSON('/api/status');
    const dot = document.getElementById('atemStatus');
    dot.classList.toggle('on', status.atem.connected);
    dot.classList.toggle('off', !status.atem.connected);

    const tcEl = document.getElementById('timecodeStatus');
    const markBtn = document.getElementById('markStartBtn');
    if (status.timecode && status.timecode.enabled) {
      tcEl.textContent = `Timecode: LTC decode (${status.timecode.hasSignal ? 'live' : 'no signal'})`;
      markBtn.style.display = 'none';
    } else {
      tcEl.textContent = 'Timecode: wall-clock estimate — mark recording start when you begin ISO recording';
      markBtn.style.display = '';
    }
  } catch (e) {
    /* ignore */
  }
}

async function refreshPresets() {
  const presets = await fetchJSON('/api/presets').catch(() => []);
  const sel = document.getElementById('presetList');
  sel.replaceChildren();
  presets.forEach((p) => sel.appendChild(el('option', { value: p.replace(/\.json$/, ''), text: p })));
}

function collectConfig() {
  config.audioDevice.deviceId = document.getElementById('deviceSelect').value || null;
  config.audioDevice.channelCount = parseInt(document.getElementById('channelCount').value, 10);
  config.audioDevice.sampleRate = parseInt(document.getElementById('sampleRate').value, 10);
  return config;
}

function nextId(items, prefix) {
  let n = items.length + 1;
  const existing = new Set(items.map((i) => i.id));
  while (existing.has(`${prefix}${n}`)) n += 1;
  return `${prefix}${n}`;
}

// Add/Remove a channel keeps the channel count and the strips in lockstep.
document.getElementById('addMicBtn').addEventListener('click', () => {
  setChannelCount(config.mics.length + 1);
});

document.getElementById('removeMicBtn').addEventListener('click', () => {
  if (config.mics.length === 0) return;
  setChannelCount(config.mics.length - 1);
});

document.getElementById('addCameraBtn').addEventListener('click', () => {
  if (config.cameras.length >= 10) return;
  const id = nextId(config.cameras, 'cam');
  const n = config.cameras.length + 1;
  config.cameras.push({ id, name: `Cam ${n}`, atemInput: n, isoReelName: `Input ${n}` });
  renderCameras();
  renderMics();
  renderGlobal();
});

document.getElementById('removeCameraBtn').addEventListener('click', () => {
  if (config.cameras.length === 0) return;
  config.cameras.pop();
  renderCameras();
  renderMics();
  renderGlobal();
});

document.getElementById('atemConnectBtn').addEventListener('click', async () => {
  const ip = document.getElementById('atemIp').value;
  await fetchJSON('/api/atem/connect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ip }) });
});

document.getElementById('masterEnable').addEventListener('change', async (e) => {
  await fetchJSON('/api/engine/enabled', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: e.target.checked }) });
});

document.getElementById('applyAudioBtn').addEventListener('click', async () => {
  collectConfig();
  await fetchJSON('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
  await fetchJSON('/api/config/apply-audio', { method: 'POST' });
});

document.getElementById('saveConfigBtn').addEventListener('click', async () => {
  collectConfig();
  await fetchJSON('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
  const btn = document.getElementById('saveConfigBtn');
  const original = btn.textContent;
  btn.textContent = 'Saved';
  setTimeout(() => (btn.textContent = original), 1200);
});

document.getElementById('savePresetBtn').addEventListener('click', async () => {
  const name = document.getElementById('presetName').value.trim();
  if (!name) return;
  collectConfig();
  await fetchJSON(`/api/presets/${encodeURIComponent(name)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
  await refreshPresets();
});

document.getElementById('loadPresetBtn').addEventListener('click', async () => {
  const name = document.getElementById('presetList').value;
  if (!name) return;
  await fetchJSON(`/api/presets/${encodeURIComponent(name)}/load`, { method: 'POST' });
  location.reload();
});

document.getElementById('markStartBtn').addEventListener('click', async () => {
  await fetchJSON('/api/timecode/mark-start', { method: 'POST' });
  const btn = document.getElementById('markStartBtn');
  const original = btn.textContent;
  btn.textContent = 'Marked';
  setTimeout(() => (btn.textContent = original), 1500);
});

document.getElementById('exportEdlBtn').addEventListener('click', () => {
  const fromVal = document.getElementById('exportFrom').value;
  const toVal = document.getElementById('exportTo').value;
  if (!fromVal || !toVal) return;
  const fromMs = new Date(fromVal).getTime();
  const toMs = new Date(toVal).getTime();
  window.location = `/api/export/edl?from=${fromMs}&to=${toMs}`;
});

loadAll();