// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { LiveAudio } from "./liveAudio";
import { renderLiveCues, type LiveCueBuffers } from "./liveCues";
vi.mock("./liveCues", () => ({ renderLiveCues: vi.fn() }));

function device() {
  vi.useFakeTimers();
  const sources: { onended: (() => void) | null; buffer: AudioBuffer | null; start: ReturnType<typeof vi.fn>;
    stop: ReturnType<typeof vi.fn>; connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }[] = [];
  const node = () => ({ connect: vi.fn(), disconnect: vi.fn(), gain: { value: 1 } });
  const track = { stop: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() };
  const context = {
    state: "running", sampleRate: 24000, currentTime: 1, destination: {},
    resume: vi.fn(async () => {}), close: vi.fn(async () => {}), addEventListener: vi.fn(), removeEventListener: vi.fn(),
    createGain: node, createAnalyser: () => ({ ...node(), fftSize: 1024, getFloatTimeDomainData: vi.fn() }),
    createMediaStreamSource: vi.fn(node), createScriptProcessor: node,
    createBuffer: (_channels: number, length: number, rate: number) => {
      const data = new Float32Array(length);
      return { duration: length / rate, sampleRate: rate, getChannelData: () => data };
    },
    createBufferSource: vi.fn(() => {
      const source = { ...node(), onended: null as (() => void) | null, buffer: null as AudioBuffer | null, start: vi.fn(), stop: vi.fn() };
      sources.push(source); return source;
    }),
  };
  vi.stubGlobal("AudioContext", vi.fn(function () { return context; }));
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [track], getAudioTracks: () => [track] }) } });
  vi.stubGlobal("requestAnimationFrame", vi.fn(() => 1)); vi.stubGlobal("cancelAnimationFrame", vi.fn());
  const buffers = { ready: context.createBuffer(1, 25726, 24000), end: context.createBuffer(1, 27304, 24000) } as unknown as LiveCueBuffers;
  vi.mocked(renderLiveCues).mockResolvedValue(buffers);
  const send = vi.fn(), playback = vi.fn(), notice = vi.fn();
  const audio = new LiveAudio(send, vi.fn(), playback, notice);
  return { audio, context, track, sources, send, playback, notice, buffers };
}
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.mocked(renderLiveCues).mockReset(); });

test("a failed cue render does not prevent microphone use or immediate cleanup", async () => {
  const { audio, context, sources, track } = device();
  vi.mocked(renderLiveCues).mockRejectedValue(new Error("offline rendering unavailable"));
  await audio.prepare(); audio.begin(); audio.dispose();
  expect(context.createMediaStreamSource).toHaveBeenCalledOnce(); expect(sources).toHaveLength(0);
  expect(track.stop).toHaveBeenCalledOnce(); expect(context.close).toHaveBeenCalledOnce();
});

test("ready sounds only when capture begins, once; cues never advance provider playback or send PCM", async () => {
  const { audio, context, track, sources, send, playback, buffers } = device();
  await audio.prepare(); expect(sources).toHaveLength(0);
  expect(renderLiveCues).toHaveBeenCalledWith(context.sampleRate);
  audio.begin(); audio.begin(); expect(sources).toHaveLength(1);
  expect(sources[0].buffer).toBe(buffers.ready);
  expect(context.createMediaStreamSource).toHaveBeenCalledOnce();
  expect(sources[0].start).toHaveBeenCalledOnce();
  expect(audio.receivedMs).toBe(0); expect(audio.playedMs).toBe(0);
  expect(send).not.toHaveBeenCalled(); expect(playback).not.toHaveBeenCalled();
  audio.dispose(); audio.dispose();
  expect(track.stop).toHaveBeenCalledOnce(); expect(sources[0].stop).toHaveBeenCalledOnce();
  expect(sources).toHaveLength(2); expect(sources[1].connect).toHaveBeenCalledWith(context.destination);
  expect(sources[1].buffer).toBe(buffers.end);
  expect(context.close).not.toHaveBeenCalled(); // Closing the microphone cannot cut off the end sound.
  sources[1].onended!();
  expect(context.close).toHaveBeenCalledOnce(); expect(sources[1].disconnect).toHaveBeenCalledOnce();
  expect(vi.getTimerCount()).toBe(0);
});

test("cancelled preparation and muted output stay silent and release audio immediately", async () => {
  for (const muted of [false, true]) {
    const { audio, context, sources, track } = device();
    await audio.prepare();
    if (muted) { audio.muteOutput(true); audio.begin(); }
    audio.dispose();
    expect(sources).toHaveLength(0); expect(track.stop).toHaveBeenCalledOnce(); expect(context.close).toHaveBeenCalledOnce();
  }
});

test("muting cuts off a ready cue and unmuting does not replay it", async () => {
  const { audio, sources, context } = device();
  await audio.prepare(); audio.begin(); audio.muteOutput(true);
  expect(sources[0].stop).toHaveBeenCalledOnce(); expect(sources[0].disconnect).toHaveBeenCalledOnce();
  audio.muteOutput(false); expect(sources).toHaveLength(1);
  audio.muteOutput(true); audio.dispose(); expect(sources).toHaveLength(1); expect(context.close).toHaveBeenCalledOnce();
});

test("an end cue that never finishes cannot retain an audio context or microphone", async () => {
  const { audio, context, sources, track } = device();
  await audio.prepare(); audio.begin(); audio.dispose();
  context.state = "suspended";
  expect(track.stop).toHaveBeenCalledOnce();
  await vi.advanceTimersByTimeAsync(750);
  expect(context.close).not.toHaveBeenCalled(); // The user's longer decay must not be truncated.
  await vi.advanceTimersByTimeAsync(1000);
  expect(context.close).toHaveBeenCalledOnce(); expect(sources[1].stop).toHaveBeenCalledOnce();
});

test("cancelling while the sounds render cannot restart capture or play a late cue", async () => {
  const { audio, context, sources, track, buffers } = device();
  let finish: (buffers: LiveCueBuffers) => void = () => {};
  vi.mocked(renderLiveCues).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const pending = audio.prepare();
  await Promise.resolve(); await Promise.resolve();
  expect(track.addEventListener).toHaveBeenCalled();
  audio.dispose(); finish(buffers); await pending; audio.begin();
  expect(track.stop).toHaveBeenCalledOnce(); expect(context.close).toHaveBeenCalledOnce();
  expect(context.createMediaStreamSource).not.toHaveBeenCalled(); expect(sources).toHaveLength(0);
});

test("cue playback failure does not break capture or teardown", async () => {
  const { audio, context, track, notice } = device();
  await audio.prepare(); context.createBufferSource.mockImplementation(() => { throw new Error("unavailable sound device"); });
  expect(() => audio.begin()).not.toThrow();
  expect(context.createMediaStreamSource).toHaveBeenCalledOnce();
  expect(() => audio.dispose()).not.toThrow();
  expect(track.stop).toHaveBeenCalledOnce(); expect(context.close).toHaveBeenCalledOnce(); expect(notice).not.toHaveBeenCalled();
});
