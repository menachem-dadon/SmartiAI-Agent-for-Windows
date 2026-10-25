export type LiveCue = "ready" | "end";
export type LiveCueBuffers = Record<LiveCue, AudioBuffer>;

type Glide = [startHz: number, midHz: number, endHz: number, start: number, mid: number, end: number, peak: number];
type Partial = [hz: number, onset: number, attack: number, tauMs: number, peak: number];

// Sound recipe supplied by the user, 2026-10-25. Keep its pitches, automation,
// master gain and diffusion paths intact; LiveAudio owns playback and muting.
const recipes: Record<LiveCue, { glides: Glide[]; partials: Partial[] }> = {
  ready: {
    glides: [
      [216.0, 256.0, 308.0, .010, .088, .159, .195],
      [329.6, 298.0, 277.2, .012, .085, .159, .062],
      [146.6, 175.0, 213.1, .012, .085, .159, .018],
    ],
    partials: [
      [331.24, .159, .005, 111.8, .215],
      [554.44, .159, .004, 91.9, .152],
      [277.22, .159, .006, 129.1, .102],
      [432.90, .159, .003, 24.0, .024],
      [651.90, .159, .003, 24.0, .018],
    ],
  },
  end: {
    glides: [
      [345.0, 282.0, 234.0, .018, .072, .118, .150],
      [333.0, 331.0, 329.8, .025, .075, .118, .036],
      [215.0, 185.0, 148.0, .025, .075, .118, .014],
    ],
    partials: [
      [219.91, .118, .006, 144.8, .218],
      [439.82, .118, .005, 85.7, .235],
      [329.77, .118, .006, 101.8, .056],
      [880.37, .118, .004, 82.9, .011],
      [538.50, .118, .003, 22.0, .025],
    ],
  },
};

function createMaster(ctx: BaseAudioContext) {
  const now = ctx.currentTime, master = ctx.createGain();
  master.gain.setValueAtTime(.95, now); master.connect(ctx.destination);
  const left = ctx.createDelay(.05), right = ctx.createDelay(.05), side = ctx.createGain();
  left.delayTime.setValueAtTime(.011, now); right.delayTime.setValueAtTime(.017, now);
  side.gain.setValueAtTime(.045, now);
  master.connect(left); master.connect(right); left.connect(side); right.connect(side); side.connect(ctx.destination);
  return master;
}

function glide(ctx: BaseAudioContext, master: GainNode, [fStart, fMid, fEnd, tStart, tMid, tEnd, peak]: Glide) {
  const now = ctx.currentTime + .008, t0 = now + tStart, tm = now + tMid, t1 = now + tEnd;
  const osc = ctx.createOscillator(), gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(fStart, t0);
  osc.frequency.exponentialRampToValueAtTime(fMid, tm);
  osc.frequency.exponentialRampToValueAtTime(fEnd, t1);
  gain.gain.setValueAtTime(.0001, t0);
  gain.gain.linearRampToValueAtTime(peak, t0 + (tEnd - tStart) * .62);
  gain.gain.linearRampToValueAtTime(peak * .68, t1);
  gain.gain.exponentialRampToValueAtTime(.0001, t1 + .035);
  osc.connect(gain); gain.connect(master); osc.start(t0); osc.stop(t1 + .04);
}

function partial(ctx: BaseAudioContext, master: GainNode, [freq, onset, attack, tauMs, peak]: Partial) {
  const t0 = ctx.currentTime + .008 + onset, tau = tauMs / 1000;
  const osc = ctx.createOscillator(), gain = ctx.createGain();
  osc.type = "sine"; osc.frequency.setValueAtTime(freq, t0);
  gain.gain.setValueAtTime(.0001, t0);
  gain.gain.linearRampToValueAtTime(peak, t0 + attack);
  gain.gain.setTargetAtTime(.00001, t0 + attack, tau);
  osc.connect(gain); gain.connect(master); osc.start(t0); osc.stop(t0 + tau * 6.8);
}

async function renderCue(kind: LiveCue, rate: number): Promise<AudioBuffer> {
  const recipe = recipes[kind];
  const lastStop = Math.max(...recipe.glides.map(item => item[5] + .04),
    ...recipe.partials.map(item => item[1] + item[3] / 1000 * 6.8));
  // Include the final oscillator's release and both diffusion paths, plus 10ms
  // of silence. The supplied graph has no panning, so its channels are identical.
  const duration = .008 + lastStop + .017 + .010;
  const ctx = new OfflineAudioContext(1, Math.ceil(duration * rate), rate);
  const master = createMaster(ctx);
  recipe.glides.forEach(item => glide(ctx, master, item));
  recipe.partials.forEach(item => partial(ctx, master, item));
  return ctx.startRendering();
}

const cache = new Map<number, Promise<LiveCueBuffers>>();

/** Render the supplied Web Audio graph once per device rate, before Live is ready. */
export function renderLiveCues(rate: number): Promise<LiveCueBuffers> {
  let rendered = cache.get(rate);
  if (!rendered) {
    rendered = Promise.all([renderCue("ready", rate), renderCue("end", rate)])
      .then(([ready, end]) => ({ ready, end }))
      .catch(error => { cache.delete(rate); throw error; });
    cache.set(rate, rendered);
  }
  return rendered;
}
