const { EventEmitter } = require('events');
const portAudio = require('naudiodon2');

const SAMPLE_FORMAT_16 = 16;
const WINDOW_MS = 30; // how often we emit a level update

class SystemAudioSource extends EventEmitter {
  constructor({ deviceId = null, sampleRate = 48000, channelCount = 8 } = {}) {
    super();
    this.sampleRate = sampleRate;
    this.channelCount = channelCount;
    this.deviceId = deviceId;
    this.io = null;
    this.buffer = Buffer.alloc(0);
    this.bytesPerSample = 2; // 16-bit
    this.frameBytes = this.bytesPerSample * this.channelCount;
    this.samplesPerWindow = Math.floor((this.sampleRate * WINDOW_MS) / 1000);
  }

  static listDevices() {
    return portAudio.getDevices().map((d) => ({
      id: d.id,
      name: d.name,
      maxInputChannels: d.maxInputChannels,
      defaultSampleRate: d.defaultSampleRate,
    }));
  }

  start() {
    const deviceId = this.deviceId != null ? this.deviceId : -1; // -1 = default input in naudiodon2

    this.io = portAudio.AudioIO({
      inOptions: {
        channelCount: this.channelCount,
        sampleFormat: SAMPLE_FORMAT_16,
        sampleRate: this.sampleRate,
        deviceId,
        closeOnError: false,
      },
    });

    this.io.on('data', (chunk) => this._onData(chunk));
    this.io.on('error', (err) => this.emit('error', err));
    this.io.start();
  }

  stop() {
    if (this.io) {
      try {
        this.io.quit();
      } catch (e) {
        /* ignore */
      }
      this.io = null;
    }
  }

  _onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);

    const windowBytes = this.frameBytes * this.samplesPerWindow;
    while (this.buffer.length >= windowBytes) {
      const slice = this.buffer.subarray(0, windowBytes);
      this.buffer = this.buffer.subarray(windowBytes);
      this._emitLevels(slice);
    }
  }

  _emitLevels(slice) {
    const sums = new Array(this.channelCount).fill(0);
    const frameCount = slice.length / this.frameBytes;

    for (let frame = 0; frame < frameCount; frame++) {
      const frameOffset = frame * this.frameBytes;
      for (let ch = 0; ch < this.channelCount; ch++) {
        const sampleOffset = frameOffset + ch * this.bytesPerSample;
        const sample = slice.readInt16LE(sampleOffset);
        const norm = sample / 32768;
        sums[ch] += norm * norm;
      }
    }

    const levels = sums.map((sumSq) => {
      const rms = Math.sqrt(sumSq / frameCount);
      const db = rms > 0 ? 20 * Math.log10(rms) : -100;
      return Math.max(db, -100);
    });

    this.emit('levels', levels); // array of dBFS values, index = channelIndex
  }
}

module.exports = SystemAudioSource;
