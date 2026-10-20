// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { LiveAudio } from "./liveAudio";
afterEach(() => vi.unstubAllGlobals());
test("meters reflect actual playback, keep sampling muted input, and release all resources", async () => {
  let frame: FrameRequestCallback = () => {}, userLevel = .02, outputLevel = 0;
  const disconnect = vi.fn(), stop = vi.fn(), close = vi.fn(async () => {});
  const track = { enabled: true, stop };
  const node = () => ({ connect: vi.fn(), disconnect, gain: { value: 1 } });
  let meters = 0;
  vi.stubGlobal("AudioContext", class {
    currentTime = 1; destination = {};
    resume = async () => {};
    close = close;
    createGain = node;
    createAnalyser() {
      const output = meters++ === 0;
      return { ...node(), fftSize: 1024, getFloatTimeDomainData: (samples: Float32Array) => samples.fill(output ? outputLevel : userLevel) };
    }
    createMediaStreamSource = node;
    createScriptProcessor = node;
    createBuffer = (_channels: number, length: number, rate: number) => ({ duration: length / rate, getChannelData: () => new Float32Array(length) });
    createBufferSource = () => ({ ...node(), start: vi.fn(), stop: vi.fn() });
  });
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [track], getAudioTracks: () => [track] }) } });
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { frame = callback; return 1; });
  const cancel = vi.fn(); vi.stubGlobal("cancelAnimationFrame", cancel);
  const levels = vi.fn(), audio = new LiveAudio(vi.fn(), levels);
  await audio.prepare(); audio.begin(); frame(0);
  expect(levels.mock.lastCall?.[0]).toBeCloseTo(.02);
  audio.play(btoa("\0\0".repeat(2400)));
  frame(16); expect(levels.mock.lastCall?.[1]).toBe(0); // queued, not yet heard
  outputLevel = .08;
  frame(32); expect(levels.mock.lastCall?.[1]).toBeCloseTo(.08);
  audio.muteMic(true); frame(48);
  expect(track.enabled).toBe(false); expect(levels.mock.lastCall?.[0]).toBe(0);
  audio.muteOutput(true); frame(64); expect(levels.mock.lastCall?.[1]).toBe(0);
  userLevel = 0; audio.dispose(); audio.dispose();
  expect(stop).toHaveBeenCalledOnce(); expect(close).toHaveBeenCalledOnce(); expect(cancel).toHaveBeenCalled(); expect(disconnect).toHaveBeenCalled();
});
