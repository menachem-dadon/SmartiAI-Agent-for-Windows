// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { BrowserAgentControls } from "./BrowserAgentControls";
import { BrowserPreviewCard } from "./BrowserPreviewCard";
import type { BrowserAgentActivity } from "./browserState";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const agent: BrowserAgentActivity = { tabId: "owned-target", workspaceId: "owned-workspace", sessionId: "session-a", action: "click", state: "running", presentation: "preview" };
test("takeover and resume address the owned native target", async () => {
  vi.mocked(invoke).mockResolvedValue({});
  const view = render(<BrowserAgentControls agent={agent} />);
  fireEvent.click(screen.getByRole("button", { name: "השהיה והעברת השליטה אליי" }));
  await waitFor(() => expect(invoke).toHaveBeenCalledWith("browser_agent_control", { tabId: "owned-target", action: "pause" }));
  view.rerender(<BrowserAgentControls agent={{ ...agent, state: "paused" }} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "החזרת השליטה ל־Smarti" }).hasAttribute("disabled")).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "החזרת השליטה ל־Smarti" }));
  await waitFor(() => expect(invoke).toHaveBeenLastCalledWith("browser_agent_control", { tabId: "owned-target", action: "resume" }));
});
test("dismiss hides the card without issuing a stop or closing its target", () => {
  const dismiss=vi.fn(),open=vi.fn();
  render(<BrowserPreviewCard activity={{ workspaceId: agent.workspaceId, tabId: agent.tabId, title: "משימה", url: "https://example.test", loading: false, agent }} onOpen={open} onDismiss={dismiss} />);
  fireEvent.click(screen.getByRole("button", { name: "סגירת התצוגה המקדימה" }));
  expect(dismiss).toHaveBeenCalledOnce();expect(invoke).not.toHaveBeenCalled();
});
test("control failure is visible and permits a retry", async () => {
  vi.mocked(invoke).mockRejectedValue(Error("closed target"));
  render(<BrowserAgentControls agent={agent} />);
  fireEvent.click(screen.getByRole("button", { name: "עצירת פעולות Smarti בכרטיסייה" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "השהיה והעברת השליטה אליי" }).hasAttribute("disabled")).toBe(false);
});
