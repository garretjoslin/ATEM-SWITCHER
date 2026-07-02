const { EventEmitter } = require('events');

class SwitchEngine extends EventEmitter {
  constructor(atemController) {
    super();
    this.atemController = atemController;
    this.config = null;
    this.micState = new Map(); // micId -> { level, aboveSince, belowSince, talking }
    this.activeMicId = null;
    this.activeCameraId = null;
    this.lastSwitchAt = 0;
    this.recentTalkStarts = []; // [{ micId, at }] for crosstalk detection
  }

  setConfig(config) {
    this.config = config;
    for (const mic of config.mics) {
      if (!this.micState.has(mic.id)) {
        this.micState.set(mic.id, { level: -100, aboveSince: null, belowSince: Date.now(), talking: false });
      }
    }
  }

  // levels: { [micId]: dBValue }
  updateLevels(levelsByMicId) {
    if (!this.config || !this.config.global.enabled) {
      // still track levels for UI meters even when auto-switch is off
      this._updateMeterStateOnly(levelsByMicId);
      this.emit('tick', this._snapshot());
      return;
    }

    const now = Date.now();
    const { attackMs, releaseHoldMs, minShotHoldMs, hysteresisDb, crosstalkWindowMs, crosstalkBiasCameraId } =
      this.config.global;

    for (const mic of this.config.mics) {
      if (!(mic.id in levelsByMicId)) continue;
      const state = this.micState.get(mic.id);
      const level = levelsByMicId[mic.id];
      state.level = level;

      const isAboveThreshold = level >= mic.thresholdDb;

      if (isAboveThreshold) {
        if (state.aboveSince == null) state.aboveSince = now;
        state.belowSince = null;
        if (!state.talking && now - state.aboveSince >= attackMs) {
          state.talking = true;
          this.recentTalkStarts.push({ micId: mic.id, at: now });
        }
      } else {
        if (state.belowSince == null) state.belowSince = now;
        state.aboveSince = null;
        if (state.talking && now - state.belowSince >= releaseHoldMs) {
          state.talking = false;
        }
      }
    }

    this.recentTalkStarts = this.recentTalkStarts.filter((t) => now - t.at <= crosstalkWindowMs);

    this._decideAndSwitch(now, { minShotHoldMs, hysteresisDb, crosstalkWindowMs, crosstalkBiasCameraId });
    this.emit('tick', this._snapshot());
  }

  _updateMeterStateOnly(levelsByMicId) {
    if (!this.config) return;
    for (const mic of this.config.mics) {
      if (!(mic.id in levelsByMicId)) continue;
      const state = this.micState.get(mic.id);
      state.level = levelsByMicId[mic.id];
    }
  }

  _decideAndSwitch(now, { minShotHoldMs, hysteresisDb, crosstalkWindowMs, crosstalkBiasCameraId }) {
    const eligible = this.config.mics.filter((m) => m.enabled && this.micState.get(m.id).talking);

    if (eligible.length === 0) return; // hold last shot, nobody's talking

    // Crosstalk: two+ different mics started talking within the window -> bias to wide shot
    const distinctRecentMics = new Set(
      this.recentTalkStarts.filter((t) => now - t.at <= crosstalkWindowMs).map((t) => t.micId)
    );
    let targetCameraId;
    let targetMicId;

    if (distinctRecentMics.size > 1 && crosstalkBiasCameraId) {
      targetCameraId = crosstalkBiasCameraId;
      targetMicId = null; // shared shot, not tied to one mic
    } else {
      // pick winner: highest priority, tie-break highest level
      const winner = eligible.reduce((best, m) => {
        if (!best) return m;
        const bp = best.priority ?? 1;
        const mp = m.priority ?? 1;
        if (mp !== bp) return mp > bp ? m : best;
        const bl = this.micState.get(best.id).level;
        const ml = this.micState.get(m.id).level;
        return ml > bl ? m : best;
      }, null);

      // hysteresis: only switch away from current mic if winner beats it by hysteresisDb
      if (this.activeMicId && this.activeMicId !== winner.id) {
        const activeStillTalking = this.micState.get(this.activeMicId)?.talking;
        if (activeStillTalking) {
          const activeLevel = this.micState.get(this.activeMicId).level;
          const winnerLevel = this.micState.get(winner.id).level;
          if (winnerLevel - activeLevel < hysteresisDb) {
            targetMicId = this.activeMicId;
            const activeMicConfig = this.config.mics.find((m) => m.id === this.activeMicId);
            targetCameraId = activeMicConfig ? activeMicConfig.cameraId : winner.cameraId;
            this._applySwitch(now, targetMicId, targetCameraId, minShotHoldMs);
            return;
          }
        }
      }

      targetMicId = winner.id;
      targetCameraId = winner.cameraId;
    }

    this._applySwitch(now, targetMicId, targetCameraId, minShotHoldMs);
  }

  _applySwitch(now, micId, cameraId, minShotHoldMs) {
    if (cameraId === this.activeCameraId) {
      this.activeMicId = micId;
      return;
    }
    if (now - this.lastSwitchAt < minShotHoldMs) return;

    const camera = this.config.cameras.find((c) => c.id === cameraId);
    if (!camera) return;

    const { type, autoDurationFrames } = this.config.global.transition;
    if (type === 'auto') {
      this.atemController.autoTo(camera.atemInput);
    } else {
      this.atemController.cutTo(camera.atemInput);
    }

    this.activeMicId = micId;
    this.activeCameraId = cameraId;
    this.lastSwitchAt = now;
    this.emit('switch', { micId, cameraId, atemInput: camera.atemInput, at: now });
  }

  _snapshot() {
    const mics = {};
    for (const [id, s] of this.micState.entries()) {
      mics[id] = { level: Math.round(s.level * 10) / 10, talking: s.talking };
    }
    return {
      mics,
      activeMicId: this.activeMicId,
      activeCameraId: this.activeCameraId,
      enabled: this.config ? this.config.global.enabled : false,
    };
  }
}

module.exports = SwitchEngine;
