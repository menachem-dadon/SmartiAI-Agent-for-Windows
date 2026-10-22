// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { LiveAudio } from "./liveAudio";
afterEach(() => vi.unstubAllGlobals());
test("meters reflect actual playback, keep sampling muted input, and release all resources", async () => {
  let frame: FrameRequestCallback = () => {}, userLevel = .02, outputLevel = 0;
  let capture: { onaudioprocess?: (event: any) => void } = {};
  const disconnect = vi.fn(), stop = vi.fn(), close = vi.fn(async () => {});
  const applyConstraints=vi.fn(async()=>{}), getUserMedia=vi.fn(async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]}));
  const track = { enabled: true, stop, getCapabilities:()=>({echoCancellation:[true,"all"]}), applyConstraints };
  const node = () => ({ connect: vi.fn(), disconnect, gain: { value: 1 } });
  let meters = 0;
  vi.stubGlobal("AudioContext", class {
    currentTime = 1; destination = {};
    addEventListener = vi.fn(); removeEventListener = vi.fn();
    resume = async () => {};
    close = close;
    createGain = node;
    createAnalyser() {
      const output = meters++ === 0;
      return { ...node(), fftSize: 1024, getFloatTimeDomainData: (samples: Float32Array) => samples.fill(output ? outputLevel : userLevel) };
    }
    createMediaStreamSource = node;
    createScriptProcessor = () => { capture={...node(),onaudioprocess:undefined};return capture; };
    createBuffer = (_channels: number, length: number, rate: number) => ({ duration: length / rate, getChannelData: () => new Float32Array(length) });
    createBufferSource = () => ({ ...node(), start: vi.fn(), stop: vi.fn() });
  });
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { frame = callback; return 1; });
  const cancel = vi.fn(); vi.stubGlobal("cancelAnimationFrame", cancel);
  const levels = vi.fn(), send=vi.fn(), audio = new LiveAudio(send, levels);
  await audio.prepare(); audio.begin(); frame(0);
  expect(getUserMedia).toHaveBeenCalledWith({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:false}});
  expect(applyConstraints).toHaveBeenCalledWith({echoCancellation:{exact:"all"}});
  expect(levels.mock.lastCall?.[0]).toBeCloseTo(.02);
  audio.play(btoa("\0\0".repeat(2400)));
  frame(16); expect(levels.mock.lastCall?.[1]).toBe(0); // queued, not yet heard
  outputLevel = .08;
  frame(32); expect(levels.mock.lastCall?.[1]).toBeCloseTo(.08);
  capture.onaudioprocess?.({inputBuffer:{sampleRate:24000,getChannelData:()=>new Float32Array(2048).fill(.0003)}});
  expect([...atob(send.mock.lastCall![0])].every(value=>value.charCodeAt(0)===0)).toBe(true);
  frame(40);expect(levels.mock.lastCall?.[0]).toBe(0);
  audio.muteMic(true); frame(48);
  expect(track.enabled).toBe(false); expect(levels.mock.lastCall?.[0]).toBe(0);
  audio.muteOutput(true); frame(64); expect(levels.mock.lastCall?.[1]).toBe(0);
  userLevel = 0; audio.dispose(); audio.dispose();
  expect(stop).toHaveBeenCalledOnce(); expect(close).toHaveBeenCalledOnce(); expect(cancel).toHaveBeenCalled(); expect(disconnect).toHaveBeenCalled();
});
test("bursty replies longer than eight seconds drain in order through a short scheduling horizon", async () => {
  let clock=1;
  const sources: {buffer?:{duration:number};onended?:()=>void;start:ReturnType<typeof vi.fn>;stop:ReturnType<typeof vi.fn>;connect:ReturnType<typeof vi.fn>;disconnect:ReturnType<typeof vi.fn>}[]=[];
  const node=()=>({connect:vi.fn(),disconnect:vi.fn(),gain:{value:1}});
  const values: number[]=[];
  vi.stubGlobal("AudioContext",class {
    get currentTime(){return clock;} destination={};resume=async()=>{};close=async()=>{};
    addEventListener=vi.fn();removeEventListener=vi.fn();createGain=node;
    createAnalyser=()=>({...node(),fftSize:1024,getFloatTimeDomainData:()=>{}});
    createBuffer(_channels:number,length:number,rate:number){const data=new Float32Array(length);return {duration:length/rate,getChannelData:()=>data};}
    createBufferSource(){const source={...node(),buffer:undefined as any,onended:undefined as (()=>void)|undefined,start:vi.fn(),stop:vi.fn()};
      source.start.mockImplementation(()=>values.push(source.buffer.getChannelData(0)[0]));sources.push(source);return source;}
  });
  vi.stubGlobal("navigator",{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[],getAudioTracks:()=>[]})}});
  vi.stubGlobal("cancelAnimationFrame",vi.fn());
  const audio=new LiveAudio(vi.fn(),vi.fn());await audio.prepare();
  for(let i=1;i<=20;i++) {
    const pcm=new Int16Array(24000).fill(i*100);
    const encoded=btoa(String.fromCharCode(...new Uint8Array(pcm.buffer)));
    expect(audio.play(encoded)).toBe(true);
  }
  expect(sources.length).toBeLessThan(5);
  expect(audio.receivedMs).toBeCloseTo(20000);expect(audio.playedMs).toBe(0);
  let ended=0;
  while(ended<sources.length){const source=sources[ended++];clock+=source.buffer!.duration;source.onended!();}
  expect(values.length).toBe(100);
  expect(audio.playedMs).toBeCloseTo(20000);
  expect(values.map(value=>Math.round(value*32768))).toEqual(Array.from({length:20},(_,i)=>Array(5).fill((i+1)*100)).flat());
  // A pathological backlog is recovered locally and never throws or closes audio.
  const huge=btoa("\0\0".repeat(24000*121));
  expect(audio.play(huge)).toBe(false);
  expect(audio.playedMs).toBeCloseTo(20000); // Dropped audio was never heard.
  expect(audio.droppedRanges[0]).toEqual([20000, 141000]);
  audio.rebase(160000);
  expect(audio.playedMs).toBeCloseTo(20000);
  expect(audio.droppedRanges[0]).toEqual([20000, 160000]);
  audio.muteOutput(true);
  expect(audio.play(btoa("\0\0".repeat(2400)), 24000, 160000)).toBe(true);
  expect(audio.playedMs).toBeCloseTo(20000);
  audio.muteOutput(false);
  expect(audio.play(btoa("\0\0".repeat(2400)))).toBe(true);
  audio.dispose();
});
