/** A conservative residual-echo guard after the browser's own AEC. */
export class LiveCaptureFilter {
  private rate = 2000;
  private samples = new Float32Array(12000);
  private stamps = new Float64Array(12000).fill(-1);
  record(samples: Float32Array, rate: number, start: number) {
    const first = Math.ceil(start * this.rate), last = Math.floor((start + samples.length / rate) * this.rate);
    for (let tick = first; tick < last; tick++) {
      const index = tick % this.samples.length;
      this.samples[index] = samples[Math.min(samples.length - 1, Math.floor((tick / this.rate - start) * rate))];
      this.stamps[index] = tick;
    }
  }
  truncate(time: number) {
    for (let index = 0; index < this.stamps.length; index++) if (this.stamps[index] > time * this.rate) this.stamps[index] = -1;
  }
  filter(input: Float32Array, rate: number, end: number): Float32Array {
    const size = Math.floor(input.length * this.rate / rate);
    const values = new Float32Array(size);
    let energy = 0;
    for (let index = 0; index < size; index++) { const value = input[Math.floor(index * rate / this.rate)]; values[index] = value; energy += value * value; }
    // Keep sending silence at the original cadence, so server VAD still ends
    // real utterances. Never use transcript words to decide what was speech.
    if (Math.sqrt(energy / Math.max(1, size)) < .0015) return new Float32Array(input.length);
    const beginning = Math.round((end - input.length / rate) * this.rate);
    for (let delay = -80; delay <= 900; delay += 4) {
      let dot = 0, referenceEnergy = 0, valid = true;
      for (let index = 0; index < size; index++) {
        const tick = beginning - delay + index, slot = ((tick % this.samples.length) + this.samples.length) % this.samples.length;
        if (this.stamps[slot] !== tick) { valid = false; break; }
        const reference = this.samples[slot]; dot += values[index] * reference; referenceEnergy += reference * reference;
      }
      // Only suppress a strong waveform match. Independent user speech mixed
      // with the echo reduces correlation and remains available for barge-in.
      if (valid && referenceEnergy > 1e-6 && dot * dot / (energy * referenceEnergy) > .88) return new Float32Array(input.length);
    }
    return input;
  }
}
