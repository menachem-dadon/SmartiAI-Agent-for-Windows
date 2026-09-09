// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { WindowTitleBar } from "./WindowTitleBar";

const native = vi.hoisted(() => ({
  isMaximized: vi.fn<() => Promise<boolean>>(),
  onResized: vi.fn<(handler: () => void) => Promise<() => void>>(),
  minimize: vi.fn(),
  toggleMaximize: vi.fn(),
  close: vi.fn(),
  dispose: vi.fn(),
}));

// Tauri returns a new window wrapper per call; renders must keep one subscription.
vi.mock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({ ...native }) }));

beforeEach(() => {
  vi.clearAllMocks();
  native.isMaximized.mockResolvedValue(false);
  native.onResized.mockResolvedValue(native.dispose);
});
afterEach(cleanup);

test("caption buttons invoke only their own actions, including double clicks", async () => {
  const { container } = render(<WindowTitleBar />);
  await waitFor(() => expect(native.isMaximized).toHaveBeenCalledOnce());
  for (const [label, action] of [
    ["מזער", native.minimize],
    ["הגדל", native.toggleMaximize],
    ["סגירה", native.close],
  ] as const) {
    const button = screen.getByRole("button", { name: label });
    fireEvent.click(button);
    expect(action).toHaveBeenCalledOnce();
    fireEvent.doubleClick(button);
    expect(action).toHaveBeenCalledOnce();
  }
  expect(native.toggleMaximize).toHaveBeenCalledOnce();
  // The native drag-region handler owns double-click maximize, with no React duplicate.
  const dragRegion = container.querySelector("[data-tauri-drag-region]")!;
  expect(dragRegion.querySelector("button")).toBeNull();
  fireEvent.doubleClick(dragRegion);
  expect(native.toggleMaximize).toHaveBeenCalledOnce();
});

test("tracks restored startup and external maximize changes without resubscribing", async () => {
  native.isMaximized.mockResolvedValue(true);
  const { rerender, unmount } = render(<WindowTitleBar />);
  const restore = await screen.findByRole("button", { name: "שחזר" });
  expect(restore.textContent).toBe("\uE923");
  expect(restore.querySelector("[aria-hidden='true']")).not.toBeNull();

  native.isMaximized.mockResolvedValue(false);
  await act(async () => native.onResized.mock.calls[0][0]());
  const maximize = await screen.findByRole("button", { name: "הגדל" });
  expect(maximize.textContent).toBe("\uE922");
  rerender(<WindowTitleBar />);
  expect(native.onResized).toHaveBeenCalledOnce();
  unmount();
  await waitFor(() => expect(native.dispose).toHaveBeenCalledOnce());
});

test("ignores older state reads that finish after a newer resize", async () => {
  render(<WindowTitleBar />);
  await waitFor(() => expect(native.isMaximized).toHaveBeenCalledOnce());
  let resolveOlder!: (value: boolean) => void;
  native.isMaximized.mockImplementationOnce(() => new Promise((resolve) => {
    resolveOlder = resolve;
  }));
  await act(async () => native.onResized.mock.calls[0][0]());
  native.isMaximized.mockResolvedValue(true);
  await act(async () => native.onResized.mock.calls[0][0]());
  await screen.findByRole("button", { name: "שחזר" });
  await act(async () => resolveOlder(false));
  expect(screen.getByRole("button", { name: "שחזר" }).textContent).toBe("\uE923");
});

test("disposes a native subscription that finishes registering after unmount", async () => {
  let registered!: (dispose: () => void) => void;
  native.onResized.mockImplementationOnce(() => new Promise((resolve) => {
    registered = resolve;
  }));
  const { unmount } = render(<WindowTitleBar />);
  unmount();
  await act(async () => registered(native.dispose));
  expect(native.dispose).toHaveBeenCalledOnce();
  expect(native.isMaximized).not.toHaveBeenCalled();
});
