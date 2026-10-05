// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { coreApi } from "./coreApi";
import { TasksView } from "./ManagementPages";

vi.mock("./coreApi", () => ({ coreApi: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("task-center conversation routing", () => {
  it.each(["dedicated", "new"])("creates tasks with %s routing and no source-chat choice", async (mode) => {
    vi.mocked(coreApi).mockResolvedValue({ items: [] });
    render(<TasksView />);
    await waitFor(() => expect(coreApi).toHaveBeenCalledWith("GET", "/v2/management/tasks"));

    fireEvent.click(screen.getAllByRole("button", { name: "משימה חדשה" })[0]);
    const routing = screen.getByRole("combobox", { name: "שיחת המשימה" }) as HTMLSelectElement;
    expect(routing.value).toBe("dedicated");
    expect(Array.from(routing.options, (option) => option.value)).toEqual(["dedicated", "new"]);
    fireEvent.change(routing, { target: { value: mode } });
    fireEvent.change(screen.getByPlaceholderText("מה Smarti יבצע?"), { target: { value: "בדוק עדכונים" } });
    fireEvent.click(screen.getByRole("button", { name: "יצירת משימה" }));

    await waitFor(() => expect(coreApi).toHaveBeenCalledWith(
      "POST", "/v2/management/tasks",
      expect.objectContaining({ action: "create", prompt: "בדוק עדכונים", conversation_mode: mode }),
      true,
    ));
    await waitFor(() => expect((screen.getByPlaceholderText("מה Smarti יבצע?") as HTMLTextAreaElement).value).toBe(""));
  });
});
