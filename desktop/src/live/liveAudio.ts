import { LiveCaptureFilter } from "./liveCapture";
import captureWorkletUrl from "./liveCaptureWorklet.js?url&no-inline";
/** PCM transport, bounded queues, echo cancellation and deterministic disposal. */
export class LiveAudio {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private capture: ScriptProcessorNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private workletReady = false;
  private source: MediaStreamAudioSourceNode | null = null;
  private silent: GainNode | null = null;
  private output: GainNode | null = null;
  private userMeter: AnalyserNode | null = null;
  private outputMeter: AnalyserNode | null = null;
  private meterFrame = 0;
  private playing = new Set<AudioBufferSourceNode>();
  private pending: { pcm: Int16Array; offset: number; rate: number; position: number }[] = [];
  private queuedSeconds = 0;
  private nextTime = 0;
  private muted = false;
  private disposed = false;
  private outputMuted = false;
  private captureFilter = new LiveCaptureFilter();
  private acceptedInputLevel: number | null = null;
  private received = 0;
  private played = 0;
  private dropped: number[][] = [];
  get droppedRanges() { return this.dropped.map(span => [...span]); }
  private scheduled = new Map<AudioBufferSourceNode, { start: number; duration: number; position: number }>();
  get receivedMs() { return this.received * 1000; }
  get playedMs() {
    let position = this.played;
    for (const item of this.scheduled.values()) if ((this.context?.currentTime || 0) >= item.start)
      position = Math.max(position, item.position + Math.min(item.duration, (this.context?.currentTime || 0) - item.start));
    return position * 1000;
  }
  constructor(private onAudio: (audio: string) => void, private onLevels: (user: number, smarty: number) => void,
    private onPlayback: (playedMs: number) => void = () => {}, private onNotice: (message: string) => void = () => {}) {}
  async prepare() {
    // Called synchronously from the user's click, before the first network await.
    this.context = new AudioContext({ sampleRate: 24000 });
    this.output = this.context.createGain();
    this.outputMeter = this.context.createAnalyser(); this.outputMeter.fftSize = 1024;
    this.output.connect(this.outputMeter); this.outputMeter.connect(this.context.destination);
    this.context.addEventListener("statechange", this.contextChanged);
    await this.context.resume();
    if (this.context.audioWorklet && typeof AudioWorkletNode !== "undefined") {
      try { await this.context.audioWorklet.addModule(captureWorkletUrl); this.workletReady = true; }
      catch { this.onNotice("קליטת השמע פועלת במצב תאימות."); }
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: false } });
    if (this.disposed) { stream.getTracks().forEach(track => track.stop()); return; }
    this.stream = stream;
    const track = stream.getAudioTracks()[0];
    track?.addEventListener?.("ended", this.deviceEnded);
    navigator.mediaDevices.addEventListener?.("devicechange", this.deviceChanged);
    const modes = track?.getCapabilities?.().echoCancellation as unknown[] | undefined;
    if (modes?.includes("all")) {
      try { await track.applyConstraints({ echoCancellation: { exact: "all" } as unknown as ConstrainBoolean }); }
      catch { /* Keep the already enabled, supported boolean AEC. */ }
    }
  }
  begin() {
    if (this.disposed || !this.context || !this.stream) return;
    this.source = this.context.createMediaStreamSource(this.stream);
    this.userMeter = this.context.createAnalyser(); this.userMeter.fftSize = 1024;
    this.source.connect(this.userMeter);
    this.silent = this.context.createGain(); this.silent.gain.value = 0;
    const accept = (raw: Float32Array, rate: number) => {
      if (this.muted || this.disposed) return;
      const ratio = rate / 24000;
      const input = this.captureFilter.filter(raw, rate, this.context?.currentTime || 0);
      this.acceptedInputLevel = Math.sqrt(input.reduce((sum, value) => sum + value * value, 0) / input.length);
      const pcm = new Int16Array(Math.floor(input.length / ratio));
      for (let index = 0; index < pcm.length; index++) {
        const sample = Math.max(-1, Math.min(1, input[Math.floor(index * ratio)]));
        pcm[index] = sample < 0 ? sample * 32768 : sample * 32767;
      }
      const bytes = new Uint8Array(pcm.buffer);
      this.onAudio(btoa(String.fromCharCode(...bytes)));
    };
    if (this.workletReady) {
      this.worklet = new AudioWorkletNode(this.context, "smarti-live-capture", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
      this.worklet.port.onmessage = event => accept(new Float32Array(event.data.samples), Number(event.data.rate));
      this.source.connect(this.worklet); this.worklet.connect(this.silent);
    } else {
      this.capture = this.context.createScriptProcessor(2048, 1, 1);
      this.capture.onaudioprocess = event => accept(event.inputBuffer.getChannelData(0), event.inputBuffer.sampleRate);
      this.source.connect(this.capture); this.capture.connect(this.silent);
    }
    this.silent.connect(this.context.destination);
    const samples = new Float32Array(1024);
    const rms = (meter: AnalyserNode | null) => {
      if (!meter) return 0;
      meter.getFloatTimeDomainData(samples);
      return Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
    };
    const measure = () => {
      if (this.disposed) return;
      // Read actual playback, not one average per received audio chunk. Queued
      // audio must not animate the orb before it reaches the speakers.
      this.onLevels(this.muted ? 0 : this.acceptedInputLevel ?? rms(this.userMeter), this.outputMuted || !this.playing.size ? 0 : rms(this.outputMeter));
      this.onPlayback(this.playedMs);
      this.meterFrame = requestAnimationFrame(measure);
    };
    this.meterFrame = requestAnimationFrame(measure);
  }
  play(encoded: string, rate = 24000, startMs?: number) {
    const context = this.context;
    if (!context || this.disposed) return true;
    const binary = atob(encoded), bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
    if (bytes.length % 2) throw new Error("מקטע שמע לא תקין מהספק");
    if (!Number.isFinite(rate) || rate < 8000 || rate > 48000) throw new Error("קצב שמע לא תקין מהספק");
    const pcm = new Int16Array(bytes.buffer);
    const position = startMs === undefined ? this.received : startMs / 1000;
    const end = position + pcm.length / rate;
    if (end <= this.received && startMs !== undefined) return true;
    if (position > this.received) this.drop(this.received, position);
    this.received = Math.max(this.received, end);
    if (this.outputMuted) { this.drop(position, end); return true; }
    // Native audio can arrive much faster than playback. Keep PCM bounded in
    // memory and schedule only a short horizon, without closing the Live session.
    if (this.queuedSeconds + pcm.length / rate + Math.max(0, this.nextTime - context.currentTime) > 120) {
      this.interrupt(); return false;
    }
    this.pending.push({ pcm, offset: 0, rate, position }); this.queuedSeconds += pcm.length / rate;
    this.pump(); return true;
  }
  private pump = () => {
    const context = this.context;
    if (!context || this.disposed || this.outputMuted) return;
    while (this.pending.length && this.nextTime < context.currentTime + .4) {
      const head = this.pending[0], length = Math.min(head.pcm.length - head.offset, Math.round(head.rate * .2));
      if (!length) { this.pending.shift(); continue; }
      const buffer = context.createBuffer(1, length, head.rate), samples = buffer.getChannelData(0);
      for (let i = 0; i < length; i++) samples[i] = head.pcm[head.offset + i] / 32768;
      const position = head.position + head.offset / head.rate;
      head.offset += length; this.queuedSeconds = Math.max(0, this.queuedSeconds - buffer.duration);
      if (head.offset === head.pcm.length) this.pending.shift();
      const source = context.createBufferSource(); source.buffer = buffer; source.connect(this.output!);
      const start = Math.max(context.currentTime + .015, this.nextTime);
      this.nextTime = start + buffer.duration; this.playing.add(source);
      this.scheduled.set(source, { start, duration: buffer.duration, position });
      this.captureFilter.record(samples, head.rate, start);
      source.onended = () => { this.played = Math.max(this.played, position + buffer.duration); source.disconnect(); this.playing.delete(source); this.scheduled.delete(source); this.pump(); this.onPlayback(this.playedMs); };
      source.start(start);
    }
  };
  muteMic(muted: boolean) {
    this.muted = muted; this.stream?.getAudioTracks().forEach(track => { track.enabled = !muted; });
  }
  muteOutput(muted: boolean) { this.outputMuted = muted; if (this.output) this.output.gain.value = muted ? 0 : 1; if (muted) this.interrupt(); }
  private drop(start: number, end: number) {
    if (end <= start) return;
    const previous = this.dropped[this.dropped.length - 1];
    if (previous && previous[1] >= start * 1000) previous[1] = Math.max(previous[1], end * 1000);
    else this.dropped.push([start * 1000, end * 1000]);
    this.dropped = this.dropped.slice(-128);
  }
  rebase(positionMs: number) { this.interrupt(); this.drop(this.received, positionMs / 1000); this.received = Math.max(this.received, positionMs / 1000); }
  interrupt() {
    this.played = this.playedMs / 1000; this.drop(this.played, this.received);
    this.pending = []; this.queuedSeconds = 0; this.captureFilter.truncate(this.context?.currentTime || 0);
    for (const source of this.playing) { source.onended = null; source.disconnect(); try { source.stop(); } catch { /* already ended */ } }
    this.playing.clear(); this.scheduled.clear(); this.nextTime = 0;
  }
  private deviceEnded = () => { if (!this.disposed) this.onNotice("המיקרופון נותק. בחר התקן זמין והפעל את הלייב מחדש; המשימות ממשיכות."); };
  private deviceChanged = () => { if (this.stream?.getAudioTracks().some(track => track.readyState === "ended")) this.deviceEnded(); };
  private contextChanged = () => {
    if (this.disposed) return;
    if (this.context?.state === "suspended") void this.context.resume().catch(() => this.onNotice("השמעת השמע הושהתה. יש להפעיל את הלייב מחדש כדי לחדש אותה."));
    else if (this.context?.state === "closed") this.onNotice("התקן השמע נסגר. ניתן לחדש את הלייב; המשימות ממשיכות בצ׳אט.");
    else this.pump();
  };
  dispose() {
    if (this.disposed) return;
    this.disposed = true; this.interrupt();
    cancelAnimationFrame(this.meterFrame);
    this.context?.removeEventListener("statechange", this.contextChanged);
    if (this.capture) this.capture.onaudioprocess = null;
    if (this.worklet) this.worklet.port.onmessage = null;
    this.worklet?.disconnect(); this.worklet?.port.close();
    this.capture?.disconnect(); this.source?.disconnect(); this.silent?.disconnect(); this.output?.disconnect(); this.userMeter?.disconnect(); this.outputMeter?.disconnect();
    navigator.mediaDevices.removeEventListener?.("devicechange", this.deviceChanged);
    this.stream?.getTracks().forEach(track => { track.removeEventListener?.("ended", this.deviceEnded); track.stop(); }); this.stream = null;
    if (this.context) void this.context.close().catch(() => undefined);
  }
}
