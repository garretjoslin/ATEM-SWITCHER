const fs = require('fs');
const path = require('path');

const DEFAULT_PATH = path.join(__dirname, '..', 'config', 'default.json');
const LIVE_PATH = path.join(__dirname, '..', 'config', 'live.json');

function loadConfig() {
  const source = fs.existsSync(LIVE_PATH) ? LIVE_PATH : DEFAULT_PATH;
  const raw = fs.readFileSync(source, 'utf8');
  return JSON.parse(raw);
}

function saveConfig(config) {
  fs.writeFileSync(LIVE_PATH, JSON.stringify(config, null, 2), 'utf8');
}

function listPresets() {
  const dir = path.join(__dirname, '..', 'config', 'presets');
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return fs.readdirSync(dir).filter((f) => f.endsWith('.json'));
}

function savePreset(name, config) {
  const dir = path.join(__dirname, '..', 'config', 'presets');
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  const safeName = name.replace(/[^a-z0-9_\-]/gi, '_');
  fs.writeFileSync(path.join(dir, `${safeName}.json`), JSON.stringify(config, null, 2), 'utf8');
  return safeName;
}

function loadPreset(name) {
  const dir = path.join(__dirname, '..', 'config', 'presets');
  const safeName = name.replace(/[^a-z0-9_\-]/gi, '_');
  const raw = fs.readFileSync(path.join(dir, `${safeName}.json`), 'utf8');
  return JSON.parse(raw);
}

module.exports = { loadConfig, saveConfig, listPresets, savePreset, loadPreset };
