// AudioWorklet processor — converts incoming Float32 audio frames to Int16 PCM
// and posts batched buffers back to the main thread.
//
// Input is whatever sample rate the AudioContext runs at (we resample with
// linear interpolation to 16000 Hz before posting).
//
// Output: ArrayBuffer of Int16 little-endian PCM @ 16kHz mono.

class PCM16Worklet extends AudioWorkletProcessor {
  constructor(opts) {
    super();
    this.targetRate = 16000;
    this.inputRate = sampleRate; // global in worklet scope
    this.ratio = this.inputRate / this.targetRate;
    this.batchMs = (opts?.processorOptions?.batchMs) || 100;
    this.batchSamples = Math.floor(this.targetRate * this.batchMs / 1000);
    this.acc = []; // accumulator of resampled samples
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const ch = input[0];
    if (!ch) return true;

    // Linear-interpolation downsample to 16k mono
    const outLen = Math.floor(ch.length / this.ratio);
    for (let i = 0; i < outLen; i++) {
      const srcIdx = i * this.ratio;
      const i0 = Math.floor(srcIdx);
      const i1 = Math.min(i0 + 1, ch.length - 1);
      const frac = srcIdx - i0;
      const sample = ch[i0] * (1 - frac) + ch[i1] * frac;
      // clamp + Int16 scale
      const clamped = Math.max(-1, Math.min(1, sample));
      this.acc.push(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff);
    }

    while (this.acc.length >= this.batchSamples) {
      const chunk = this.acc.splice(0, this.batchSamples);
      const buf = new ArrayBuffer(chunk.length * 2);
      const view = new DataView(buf);
      for (let i = 0; i < chunk.length; i++) {
        view.setInt16(i * 2, chunk[i] | 0, true);
      }
      this.port.postMessage(buf, [buf]);
    }
    return true;
  }
}

registerProcessor('pcm16-worklet', PCM16Worklet);
