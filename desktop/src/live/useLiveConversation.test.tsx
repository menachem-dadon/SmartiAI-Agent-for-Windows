// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { coreApi } from "../coreApi";
import { publishSettingsChange } from "../settingsChanges";
import { useLiveConversation } from "./useLiveConversation";
vi.mock("../coreApi", () => ({ coreApi: vi.fn(), encodePath: encodeURIComponent }));
vi.mock("../speechPlayback", () => ({ setLiveSpeechSuspended: vi.fn() }));
const options={coreReady:false,coreGeneration:0,conversation:"",provider:"local",model:"test",attachments:[],onConversation:vi.fn(),onMessage:vi.fn(),onNewUserMessage:vi.fn(),onRefresh:vi.fn(),onError:vi.fn()};
afterEach(()=>{cleanup();vi.useRealTimers();vi.mocked(coreApi).mockReset();});
test("waits for bootstrap, retries a transient failure, and reloads after Core restart",async()=>{
  vi.useFakeTimers();
  vi.mocked(coreApi).mockRejectedValueOnce(new Error("starting")).mockResolvedValue({available:true});
  const view=renderHook(props=>useLiveConversation(props),{initialProps:options});
  expect(coreApi).not.toHaveBeenCalled();
  await act(async()=>view.rerender({...options,coreReady:true,coreGeneration:1}));
  expect(view.result.current.available).toBe(false);
  await act(async()=>vi.advanceTimersByTimeAsync(500));
  expect(view.result.current.available).toBe(true);
  await act(async()=>view.rerender({...options,coreGeneration:2}));
  expect(view.result.current.available).toBe(false);
  await act(async()=>view.rerender({...options,coreReady:true,coreGeneration:2}));
  expect(view.result.current.available).toBe(true);
  expect(coreApi).toHaveBeenCalledTimes(3);
});
test("a late config response cannot overwrite a newer settings save",async()=>{
  let finish:(value:unknown)=>void=()=>{};
  vi.mocked(coreApi).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValue({available:false});
  const view=renderHook(()=>useLiveConversation({...options,coreReady:true}));
  await act(async()=>publishSettingsChange("PATCH","/v2/settings"));
  await act(async()=>finish({available:true}));
  expect(view.result.current.available).toBe(false);
});
