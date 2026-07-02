const { Atem } = require('atem-connection');

class AtemController {
  constructor() {
    this.atem = new Atem();
    this.connected = false;
    this.currentInput = null;
    this.ip = null;

    this.atem.on('connected', () => {
      this.connected = true;
      console.log(`[ATEM] connected to ${this.ip}`);
    });
    this.atem.on('disconnected', () => {
      this.connected = false;
      console.log('[ATEM] disconnected');
    });
    this.atem.on('error', (e) => {
      console.error('[ATEM] error', e);
    });
  }

  connect(ip) {
    this.ip = ip;
    try {
      this.atem.connect(ip);
    } catch (e) {
      console.error('[ATEM] connect failed', e);
    }
  }

  disconnect() {
    try {
      this.atem.disconnect();
    } catch (e) {
      /* ignore */
    }
  }

  // meIndex is the mix effect bus, 0 = Program bus 1 (most single-room setups use ME 0)
  async cutTo(atemInput, meIndex = 0) {
    if (!this.connected) return;
    if (this.currentInput === atemInput) return;
    try {
      await this.atem.setPreviewInput(atemInput, meIndex);
      await this.atem.cut(meIndex);
      this.currentInput = atemInput;
    } catch (e) {
      console.error('[ATEM] cut failed', e);
    }
  }

  async autoTo(atemInput, meIndex = 0) {
    if (!this.connected) return;
    if (this.currentInput === atemInput) return;
    try {
      await this.atem.setPreviewInput(atemInput, meIndex);
      await this.atem.autoTransition(meIndex);
      this.currentInput = atemInput;
    } catch (e) {
      console.error('[ATEM] auto transition failed', e);
    }
  }

  getStatus() {
    return {
      connected: this.connected,
      ip: this.ip,
      currentInput: this.currentInput,
    };
  }
}

module.exports = AtemController;
