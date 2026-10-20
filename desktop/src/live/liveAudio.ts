/** PCM transport, bounded queues, echo cancellation and deterministic disposal. */
export class LiveAudio {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private capture: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private silent: GainNode | null = null;
  private output: GainNode | null = null;
  private playing = new Set<AudioBufferSourceNode>();
  private nextTime = 0;
  private muted = false;
  private disposed = false;
  private outputMuted = false;
  constructor(private onAudio: (audio: string) => void, private onLevel: (level: number, speaker: "user" | "smarty") => void) {}
  async prepare() {
    // Called synchronously from the user's click, before the first network await.
    this.context = new AudioContext({ sampleRate: 24000 });
    this.output = this.context.createGain(); this.output.connect(this.context.destination);
    await this.context.resume();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    if (this.disposed) { stream.getTracks().forEach(track => track.stop()); return; }
    this.stream = stream;
  }
  begin() {
    if (this.disposed || !this.context || !this.stream) return;
    this.source = this.context.createMediaStreamSource(this.stream);
    // WebView2 supports this path without a separate worklet URL/CSP exception.
    this.capture = this.context.createScriptProcessor(2048, 1, 1);
    this.silent = this.context.createGain(); this.silent.gain.value = 0;
    this.capture.onaudioprocess = event => {
      if (this.muted || this.disposed) return;
      const input = event.inputBuffer.getChannelData(0), ratio = event.inputBuffer.sampleRate / 24000;
      const pcm = new Int16Array(Math.floor(input.length / ratio));
      let power = 0;
      for (let index = 0; index < pcm.length; index++) {
        const sample = Math.max(-1, Math.min(1, input[Math.floor(index * ratio)]));
        power += sample * sample; pcm[index] = sample < 0 ? sample * 32768 : sample * 32767;
      }
      this.onLevel(Math.min(1, Math.sqrt(power / pcm.length)), "user");
      const bytes = new Uint8Array(pcm.buffer);
      this.onAudio(btoa(String.fromCharCode(...bytes)));
    };
    this.source.connect(this.capture); this.capture.connect(this.silent); this.silent.connect(this.context.destination);
  }
  play(encoded: string, rate = 24000) {
    const context = this.context;
    if (!context || this.disposed || this.outputMuted) return;
    const binary = atob(encoded), bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
    if (bytes.length % 2) throw new Error("מקטע שמע לא תקין מהספק");
    const pcm = new Int16Array(bytes.buffer), buffer = context.createBuffer(1, pcm.length, rate);
    const samples = buffer.getChannelData(0); let power = 0;
    for (let i = 0; i < pcm.length; i++) { samples[i] = pcm[i] / 32768; power += samples[i] ** 2; }
    if (this.nextTime - context.currentTime > 8) throw new Error("השהיית השמע גדלה מדי; יש לחדש את הלייב");
    const source = context.createBufferSource(); source.buffer = buffer; source.connect(this.output!);
    const start = Math.max(context.currentTime + .015, this.nextTime);
    this.nextTime = start + buffer.duration;
    this.playing.add(source);
    const delay = Math.max(0, (start - context.currentTime) * 1000);
    const timer = setTimeout(() => { if (!this.disposed && this.playing.has(source)) this.onLevel(Math.min(1, Math.sqrt(power / pcm.length)), "smarty"); }, delay);
    source.onended = () => { clearTimeout(timer); source.disconnect(); this.playing.delete(source); if (!this.playing.size) this.onLevel(0, "smarty"); };
    source.start(start);
  }
  muteMic(muted: boolean) {
    this.muted = muted; this.stream?.getAudioTracks().forEach(track => { track.enabled = !muted; });
    if (muted) this.onLevel(0, "user");
  }
  muteOutput(muted: boolean) { this.outputMuted = muted; if (this.output) this.output.gain.value = muted ? 0 : 1; if (muted) this.interrupt(); }
  interrupt() { for (const source of this.playing) { try { source.stop(); } catch { /* already ended */ } } this.playing.clear(); this.nextTime = 0; this.onLevel(0, "smarty"); }
  dispose() {
    if (this.disposed) return;
    this.disposed = true; this.interrupt();
    if (this.capture) this.capture.onaudioprocess = null;
    this.capture?.disconnect(); this.source?.disconnect(); this.silent?.disconnect(); this.output?.disconnect();
    this.stream?.getTracks().forEach(track => track.stop()); this.stream = null;
    if (this.context) void this.context.close().catch(() => undefined);
  }
}
