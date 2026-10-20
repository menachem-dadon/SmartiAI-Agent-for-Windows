// @vitest-environment jsdom
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { LiveOrb } from "./LiveOrb";
const calls = vi.hoisted(() => ({ create: vi.fn(), state: vi.fn(), audio: vi.fn(), destroy: vi.fn() }));
vi.mock("./SmartyLiveOrb", () => ({ SmartyLiveOrb: class {
  constructor() { calls.create(); }
  setState = calls.state; feedAudioLevel = calls.audio; destroy = calls.destroy;
} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
test("conversation changes keep one continuous WebGL instance and read the current audio envelope", () => {
  let tick: FrameRequestCallback = () => {};
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { tick = callback; return 1; });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  const level = { current: .4 };
  const view = render(<LiveOrb state="listening" level={level} />);
  view.rerender(<LiveOrb state="userSpeaking" level={level} />);
  act(() => tick(16)); expect(calls.audio).toHaveBeenLastCalledWith(.4);
  level.current = .7; act(() => tick(32)); expect(calls.audio).toHaveBeenLastCalledWith(.7);
  view.rerender(<LiveOrb state="thinking" level={level} />);
  view.rerender(<LiveOrb state="smartySpeaking" level={level} />);
  expect(calls.create).toHaveBeenCalledOnce();
  expect(calls.state.mock.calls.map(([state]) => state)).toEqual(["listening", "userSpeaking", "thinking", "smartySpeaking"]);
  view.unmount(); expect(calls.destroy).toHaveBeenCalledOnce();
});
