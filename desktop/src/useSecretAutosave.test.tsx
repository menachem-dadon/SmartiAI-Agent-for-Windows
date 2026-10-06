// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useSecretAutosave } from "./useSecretAutosave";

afterEach(() => { cleanup(); vi.useRealTimers(); });
const deferred = () => {
  let resolve!: (value?: undefined) => void;
  const promise = new Promise<undefined>(done => { resolve = done; });
  return { promise, resolve };
};
function setup(overrides: Partial<Parameters<typeof useSecretAutosave<undefined>>[0]> = {}) {
  vi.useFakeTimers();
  const props = { identity: "openai", delay: 900, validate: vi.fn(async () => undefined),
    persist: vi.fn(async () => {}), onSaved: vi.fn(async () => {}), onError: vi.fn(), ...overrides };
  return { props, ...renderHook(next => useSecretAutosave(next), { initialProps: props }) };
}

it("debounces typing, flushes once on blur and never writes on safe-settings refresh", async () => {
  const { result, props, rerender } = setup();
  act(() => result.current.edit("first"));
  await act(() => vi.advanceTimersByTimeAsync(600));
  act(() => result.current.edit(" final-key "));
  await act(() => vi.advanceTimersByTimeAsync(899));
  expect(props.persist).not.toHaveBeenCalled();
  await act(async () => result.current.flush());
  expect(props.validate).toHaveBeenCalledExactlyOnceWith("final-key");
  expect(props.persist).toHaveBeenCalledExactlyOnceWith("final-key");
  expect(result.current.draft).toBe("");
  rerender({ ...props });
  await act(async () => { result.current.flush(); await vi.advanceTimersByTimeAsync(10000); });
  expect(props.persist).toHaveBeenCalledTimes(1);
});

it("retains a rejected draft, surfaces the failure and allows an edited retry", async () => {
  const validate = vi.fn().mockRejectedValueOnce(Error("invalid key")).mockResolvedValue(undefined);
  const { result, props } = setup({ validate });
  act(() => result.current.edit("bad-key"));
  await act(async () => result.current.flush());
  expect(props.persist).not.toHaveBeenCalled();
  expect(props.onError).toHaveBeenCalled();
  expect(result.current.draft).toBe("bad-key");
  act(() => result.current.edit("corrected-key"));
  await act(() => vi.advanceTimersByTimeAsync(900));
  expect(props.persist).toHaveBeenCalledExactlyOnceWith("corrected-key");
});

it("retains a draft after a storage failure and recovers the write queue without retry loops", async () => {
  const persist = vi.fn().mockRejectedValueOnce(Error("storage failure")).mockResolvedValue(undefined);
  const { result, props } = setup({ persist });
  act(() => result.current.edit("first-key"));
  await act(async () => result.current.flush());
  expect(result.current.draft).toBe("first-key");
  expect(props.onError).toHaveBeenCalled();
  expect(props.onSaved).not.toHaveBeenCalled();
  await act(() => vi.advanceTimersByTimeAsync(10000));
  expect(persist).toHaveBeenCalledTimes(1);
  act(() => result.current.edit("retry-key"));
  await act(() => vi.advanceTimersByTimeAsync(900));
  expect(persist.mock.calls.map(args => args[0])).toEqual(["first-key", "retry-key"]);
  expect(props.onSaved).toHaveBeenCalledTimes(1);
});

it("discards an earlier validation after the draft changes", async () => {
  const old = deferred();
  const { result, props } = setup({ validate: vi.fn().mockReturnValueOnce(old.promise).mockResolvedValue(undefined) });
  act(() => result.current.edit("old"));
  await act(async () => result.current.flush());
  act(() => result.current.edit("new"));
  await act(() => vi.advanceTimersByTimeAsync(900));
  await act(async () => old.resolve());
  expect(props.persist).toHaveBeenCalledExactlyOnceWith("new");
});

it("deletion invalidates an outstanding validation", async () => {
  const old = deferred();
  const { result, props } = setup({ validate: vi.fn(() => old.promise) });
  act(() => result.current.edit("old"));
  await act(async () => result.current.flush());
  await act(async () => result.current.remove());
  await act(async () => old.resolve());
  expect(props.persist).toHaveBeenCalledExactlyOnceWith("");
});

it("orders deletion after an already dispatched PUT and suppresses obsolete feedback", async () => {
  const old = deferred();
  const persist = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValue(undefined);
  const { result, props } = setup({ persist });
  act(() => result.current.edit("old"));
  await act(async () => result.current.flush());
  expect(persist).toHaveBeenCalledExactlyOnceWith("old");
  await act(async () => result.current.remove());
  expect(persist).toHaveBeenCalledTimes(1);
  await act(async () => old.resolve());
  expect(persist.mock.calls.map(args => args[0])).toEqual(["old", ""]);
  expect(props.onSaved).toHaveBeenCalledTimes(1);
});

it("cancels pending timers and validation when switching provider or closing settings", async () => {
  const old = deferred();
  const { result, props, rerender, unmount } = setup({ validate: vi.fn(() => old.promise) });
  act(() => result.current.edit("old"));
  await act(async () => result.current.flush());
  rerender({ ...props, identity: "gemini" });
  await act(async () => old.resolve());
  expect(props.persist).not.toHaveBeenCalled();
  act(() => result.current.edit("pending"));
  unmount();
  await act(() => vi.advanceTimersByTimeAsync(1000));
  expect(props.persist).not.toHaveBeenCalled();
});

it("supports generic secrets with automatic deletion and no provider validation", async () => {
  const persist = vi.fn(async (_value: string) => {});
  const { result } = setup({ persist, validate: undefined, delay: 350, deleteOnEmpty: true });
  act(() => result.current.edit("tavily-key"));
  await act(() => vi.advanceTimersByTimeAsync(350));
  act(() => result.current.edit(""));
  await act(() => vi.advanceTimersByTimeAsync(350));
  expect(persist.mock.calls.map(args => args[0])).toEqual(["tavily-key", ""]);
});
