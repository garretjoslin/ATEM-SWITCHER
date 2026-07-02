const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const path = require('path');

const { loadConfig, saveConfig, listPresets, savePreset, loadPreset } = require('./config');
const AtemController = require('./atemController');
const SystemAudioSource = require('./audio/systemAudioSource');
const AtemFairlightSource = require('./audio/atemFairlightSource');
const SwitchEngine = require('./switchEngine');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, '..', 'public')));

const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

let config = loadConfig();
const atemController = new AtemController();
const switchEngine = new SwitchEngine(atemController);
switchEngine.setConfig(config);

let systemAudioSource = null;

function micsBySourceType(type) {
  return config.mics.filter((m) => m.sourceType === type && m.enabled);
}

function startAudio() {
  if (systemAudioSource) {
    systemAudioSource.stop();
    systemAudioSource = null;
  }

  const systemMics = micsBySourceType('system');
  if (systemMics.length > 0) {
    systemAudioSource = new SystemAudioSource({
      deviceId: config.audioDevice.deviceId,
      sampleRate: config.audioDevice.sampleRate,
      channelCount: config.audioDevice.channelCount,
    });

    systemAudioSource.on('levels', (levelsArray) => {
      const levelsByMicId = {};
      for (const mic of systemMics) {
        if (levelsArray[mic.channelIndex] != null) {
          levelsByMicId[mic.id] = levelsArray[mic.channelIndex];
        }
      }
      switchEngine.updateLevels(levelsByMicId);
    });

    systemAudioSource.on('error', (e) => console.error('[audio] error', e));
    systemAudioSource.start();
    console.log(`[audio] started system capture, ${config.audioDevice.channelCount} channels`);
  }
}

function broadcast(type, payload) {
  const msg = JSON.stringify({ type, payload });
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) client.send(msg);
  });
}

switchEngine.on('tick', (snapshot) => broadcast('tick', snapshot));
switchEngine.on('switch', (evt) => broadcast('switch', evt));

// ---- REST API ----

app.get('/api/config', (req, res) => res.json(config));

app.post('/api/config', (req, res) => {
  config = req.body;
  saveConfig(config);
  switchEngine.setConfig(config);
  res.json({ ok: true });
});

app.post('/api/config/apply-audio', (req, res) => {
  // re-reads config's audioDevice settings and restarts capture
  startAudio();
  res.json({ ok: true });
});

app.get('/api/devices', (req, res) => {
  try {
    res.json(SystemAudioSource.listDevices());
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/status', (req, res) => {
  res.json({
    atem: atemController.getStatus(),
    audio: { running: !!systemAudioSource },
  });
});

app.post('/api/atem/connect', (req, res) => {
  const ip = req.body.ip || config.atem.ip;
  config.atem.ip = ip;
  saveConfig(config);
  atemController.connect(ip);
  res.json({ ok: true });
});

app.post('/api/engine/enabled', (req, res) => {
  config.global.enabled = !!req.body.enabled;
  saveConfig(config);
  switchEngine.setConfig(config);
  res.json({ ok: true });
});

app.get('/api/presets', (req, res) => res.json(listPresets()));

app.post('/api/presets/:name', (req, res) => {
  const name = savePreset(req.params.name, config);
  res.json({ ok: true, name });
});

app.get('/api/presets/:name', (req, res) => {
  try {
    const preset = loadPreset(req.params.name);
    res.json(preset);
  } catch (e) {
    res.status(404).json({ error: 'preset not found' });
  }
});

app.post('/api/presets/:name/load', (req, res) => {
  try {
    config = loadPreset(req.params.name);
    saveConfig(config);
    switchEngine.setConfig(config);
    startAudio();
    res.json({ ok: true });
  } catch (e) {
    res.status(404).json({ error: 'preset not found' });
  }
});

const PORT = process.env.PORT || 4590;
server.listen(PORT, () => {
  console.log(`mic-cam-switcher listening on http://localhost:${PORT}`);
  if (config.atem.ip) atemController.connect(config.atem.ip);
  startAudio();
});
