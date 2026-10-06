// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useStartupWatchdog } from "./InterfaceRecovery";
afterEach(() => { cleanup(); vi.useRealTimers(); });
it("offers recovery for a stalled ready-Core startup and clears it when startup finishes", () => {
  vi.useFakeTimers();
  const view = renderHook(({pending}) => useStartupWatchdog(pending), {initialProps:{pending:true}});
  act(() => vi.advanceTimersByTime(14999)); expect(view.result.current).toBe(false);
  act(() => vi.advanceTimersByTime(1)); expect(view.result.current).toBe(true);
  view.rerender({pending:false}); expect(view.result.current).toBe(false);
  view.rerender({pending:true}); expect(view.result.current).toBe(false);
  view.unmount(); expect(vi.getTimerCount()).toBe(0);
});
