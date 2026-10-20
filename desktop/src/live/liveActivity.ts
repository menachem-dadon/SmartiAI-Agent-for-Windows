import type { OrbState } from "./SmartyLiveOrb";

/** Presentation only: never gates the audio sent to the provider. */
export class LiveActivity {
  private userUntil = -Infinity;
  private smartyUntil = -Infinity;
  private previousTime = 0;
  private envelope = 0;
  sample(userRms: number, smartyRms: number, now: number, busy: boolean) {
    // A short release bridges syllables without latching onto residual noise
    // below the speech threshold after the user stops talking.
    if (userRms > .008) this.userUntil = now + 220;
    if (smartyRms > .003) this.smartyUntil = now + 160;
    const state: OrbState = now < this.smartyUntil ? "smartySpeaking"
      : now < this.userUntil ? "userSpeaking" : busy ? "thinking" : "listening";
    const rms = state === "smartySpeaking" ? smartyRms : state === "userSpeaking" ? userRms : 0;
    // PCM RMS is usually far below 1. Map the useful voice range to the orb's
    // normalized input instead of constantly overriding its presets near zero.
    const normalized = rms > .003 ? Math.max(0, Math.min(1, (20 * Math.log10(rms) + 52) / 36)) : 0;
    const dt = this.previousTime ? Math.min(100, now - this.previousTime) : 16;
    this.previousTime = now;
    this.envelope += (normalized - this.envelope) * (1 - Math.exp(-dt / (normalized > this.envelope ? 50 : 180)));
    return { state, level: this.envelope };
  }
}
