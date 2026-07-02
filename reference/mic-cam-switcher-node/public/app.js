let config = null;
let ws = null;

const dbToPercent = (db) => {
  const clamped = Math.max(-60, Math.min(0, db));
  return ((clamped + 60) / 60) * 100;
};

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

async function loadAll() {
  config = await fetchJSON('/api/config');
  const devices = await fetchJSON('/api/devices').catch(() => []);
  renderHeader();
  renderAudioDevice(devices);
  renderMics();
  renderCameras();
  renderGlobal();
  await refreshPresets();
  connectWS();
  refreshStatus();
  setInterval(refreshStatus, 4000);
}

function renderHeader() {
  document.getElementById('atemIp').value = config.atem.ip || '';
  document.getElementById('masterEnable').checked = !!config.global.enabled;
}

function renderAudioDevice(devices) {
  const sel = document.getElementById('deviceSelect');
  sel.innerHTML = '<option value="">Default input</option>';
  devices.forEach((d) => {
    const opt = document.createElement('option');
    opt.value = d.id;
    opt.textContent = `${d.name} (${d.maxInputChannels} ch)`;
    if (config.audioDevice.deviceId === d.id) opt.selected = true;
    sel.appendChild(opt);
  });
  document.getElementById('channelCount').value = config.audioDevice.channelCount;
  document.getElementById('sampleRate').value = config.audioDevice.sampleRate;
}

function cameraOptionsHTML(selectedId) {
  return config.cameras
    .map((c) => `<option value="${c.id}" ${c.id === selectedId ? 'selected' : ''}>${c.name}</option>`)
    .join('');
}

function renderMics() {
  const container = document.getElementById('micStrips');
  container.innerHTML = '';
  config.mics.forEach((mic, idx) => {
    const strip = document.createElement('div');
    strip.className = 'mic-strip';
    strip.dataset.micId = mic.id;
    strip.innerHTML = `
      <input type="text" class="mic-name" value="${mic.name}" />
      <label style="font-size:11px;color:#9096a3;display:flex;gap:4px;align-items:center;">
        <input type="checkbox" class="mic-enabled" ${mic.enabled ? 'checked' : ''}/> on
      </label>
      <select class="mic-source">
        <option value="system" ${mic.sourceType === 'system' ? 'selected' : ''}>System</option>
        <option value="atem" ${mic.sourceType === 'atem' ? 'selected' : ''}>ATEM</option>
      </select>
      <div>
        <div class="meter-wrap">
          <div class="meter-fill" style="width:0%"></div>
          <div class="meter-threshold" style="left:${dbToPercent(mic.thresholdDb)}%"></div>
        </div>
      </div>
      <input type="number" class="mic-threshold" value="${mic.thresholdDb}" step="1" title="Threshold dB" />
      <input type="number" class="mic-channel" value="${mic.channelIndex}" min="0" title="Channel index" />
      <select class="mic-camera">${cameraOptionsHTML(mic.cameraId)}</select>
    `;
    container.appendChild(strip);

    strip.querySelector('.mic-threshold').addEventListener('input', (e) => {
      mic.thresholdDb = parseFloat(e.target.value);
      strip.querySelector('.meter-threshold').style.left = `${dbToPercent(mic.thresholdDb)}%`;
    });
    strip.querySelector('.mic-name').addEventListener('input', (e) => (mic.name = e.target.value));
    strip.querySelector('.mic-enabled').addEventListener('change', (e) => (mic.enabled = e.target.checked));
    strip.querySelector('.mic-source').addEventListener('change', (e) => (mic.sourceType = e.target.value));
    strip.querySelector('.mic-channel').addEventListener('input', (e) => (mic.channelIndex = parseInt(e.target.value, 10)));
    strip.querySelector('.mic-camera').addEventListener('change', (e) => (mic.cameraId = e.target.value));
  });
}

function renderCameras() {
  const container = document.getElementById('cameraStrips');
  container.innerHTML = '';
  config.cameras.forEach((cam) => {
    const strip = document.createElement('div');
    strip.className = 'camera-strip';
    strip.dataset.cameraId = cam.id;
    strip.innerHTML = `
      <input type="text" class="cam-name" value="${cam.name}" />
      <label style="font-size:11px;color:#9096a3;">ATEM input
        <input type="number" class="cam-input" value="${cam.atemInput}" min="1" />
      </label>
    `;
    container.appendChild(strip);
    strip.querySelector('.cam-name').addEventListener('input', (e) => {
      cam.name = e.target.value;
      renderMics(); // refresh routing dropdown labels
      renderGlobal();
    });
    strip.querySelector('.cam-input').addEventListener('input', (e) => (cam.atemInput = parseInt(e.target.value, 10)));
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

  const sel = document.getElementById('crosstalkBiasCameraId');
  sel.innerHTML = '<option value="">(none)</option>' + cameraOptionsHTML(g.crosstalkBiasCameraId);

  document.getElementById('attackMs').oninput = (e) => (g.attackMs = parseInt(e.target.value, 10));
  document.getElementById('releaseHoldMs').oninput = (e) => (g.releaseHoldMs = parseInt(e.target.value, 10));
  document.getElementById('minShotHoldMs').oninput = (e) => (g.minShotHoldMs = parseInt(e.target.value, 10));
  document.getElementById('hysteresisDb').oninput = (e) => (g.hysteresisDb = parseFloat(e.target.value));
  document.getElementById('transitionType').onchange = (e) => (g.transition.type = e.target.value);
  document.getElementById('autoDurationFrames').oninput = (e) => (g.transition.autoDurationFrames = parseInt(e.target.value, 10));
  document.getElementById('crosstalkWindowMs').oninput = (e) => (g.crosstalkWindowMs = parseInt(e.target.value, 10));
  sel.onchange = (e) => (g.crosstalkBiasCameraId = e.target.value || null);
}

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}`);
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
  });

  const activeMic = config.mics.find((m) => m.id === snapshot.activeMicId);
  const activeCam = config.cameras.find((c) => c.id === snapshot.activeCameraId);
  document.getElementById('activeMic').textContent = activeMic ? activeMic.name : '—';
  document.getElementById('activeCamera').textContent = activeCam ? activeCam.name : '—';

  document.querySelectorAll('.camera-strip').forEach((el) => {
    el.classList.toggle('active', el.dataset.cameraId === snapshot.activeCameraId);
  });
}

function logSwitch(evt) {
  const cam = config.cameras.find((c) => c.id === evt.cameraId);
  const mic = config.mics.find((m) => m.id === evt.micId);
  const el = document.getElementById('log');
  const time = new Date(evt.at).toLocaleTimeString();
  el.textContent = `${time} -> ${cam ? cam.name : evt.cameraId} (${mic ? mic.name : 'shared'})`;
}

async function refreshStatus() {
  try {
    const status = await fetchJSON('/api/status');
    const dot = document.getElementById('atemStatus');
    dot.classList.toggle('on', status.atem.connected);
    dot.classList.toggle('off', !status.atem.connected);
  } catch (e) {
    /* ignore */
  }
}

async function refreshPresets() {
  const presets = await fetchJSON('/api/presets').catch(() => []);
  const sel = document.getElementById('presetList');
  sel.innerHTML = presets.map((p) => `<option value="${p.replace(/\.json$/, '')}">${p}</option>`).join('');
}

function collectConfig() {
  config.audioDevice.deviceId = document.getElementById('deviceSelect').value || null;
  config.audioDevice.channelCount = parseInt(document.getElementById('channelCount').value, 10);
  config.audioDevice.sampleRate = parseInt(document.getElementById('sampleRate').value, 10);
  return config;
}

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

loadAll();
