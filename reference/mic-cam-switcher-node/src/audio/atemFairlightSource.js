const { EventEmitter } = require('events');

/**
 * EXPERIMENTAL. Blackmagic's ATEM protocol is reverse-engineered, and how much
 * Fairlight audio meter data it exposes over the network varies by model/firmware.
 * atem-connection surfaces Fairlight mixer *state* (gain, EQ, dynamics) reliably,
 * but live peak/RMS meter ticks are not consistently available across all ATEM
 * hardware. This polls whatever level data atem-connection's state tree exposes
 * for each Fairlight input source and converts it to an approximate dB value.
 *
 * If your ATEM doesn't report live levels this way, the practical workaround is
 * to also tap the same mic feeds into the Sound Devices interface (a split or a
 * second output) and use SystemAudioSource instead - same UI, same switch engine,
 * just a different level source per mic.
 */
class AtemFairlightSource extends EventEmitter {
  constructor(atemController, { pollMs = 50 } = {}) {
    super();
    this.atemController = atemController;
    this.pollMs = pollMs;
    this.timer = null;
  }

  start() {
    this.timer = setInterval(() => this._poll(), this.pollMs);
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  _poll() {
    const atem = this.atemController.atem;
    if (!atem || !this.atemController.connected) return;

    const fairlight = atem.state && atem.state.fairlight;
    if (!fairlight || !fairlight.inputs) {
      this.emit('unavailable');
      return;
    }

    // Map of atemInputId -> approximate dB level, keyed by Fairlight input index.
    const levels = {};
    for (const [inputId, input] of Object.entries(fairlight.inputs)) {
      const sources = input.sources || {};
      const firstSource = Object.values(sources)[0];
      // faderGain is a mix-level setting, not a live meter - this is a placeholder
      // until confirmed against real hardware. Treat AtemFairlightSource as a
      // starting point to wire up against your actual switcher, not a finished part.
      const gain = firstSource && typeof firstSource.faderGain === 'number' ? firstSource.faderGain : -100;
      levels[inputId] = gain;
    }

    this.emit('levels', levels);
  }
}

module.exports = AtemFairlightSource;
