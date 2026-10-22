/* Capture runs on the audio render thread; no network or Core work here. */
class SmartiLiveCapture extends AudioWorkletProcessor {
  constructor() { super(); this.samples = new Float32Array(2048); this.used = 0; }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (input) for (let offset = 0; offset < input.length;) {
      const count = Math.min(input.length - offset, this.samples.length - this.used);
      this.samples.set(input.subarray(offset, offset + count), this.used);
      offset += count; this.used += count;
      if (this.used === this.samples.length) {
        this.port.postMessage({ samples: this.samples.buffer, rate: sampleRate }, [this.samples.buffer]);
        this.samples = new Float32Array(2048); this.used = 0;
      }
    }
    return true;
  }
}
registerProcessor("smarti-live-capture", SmartiLiveCapture);
