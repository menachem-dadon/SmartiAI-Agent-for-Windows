// @vitest-environment jsdom
import { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ChoiceField } from "./ChoiceField";
import { Button, DesignSystemProvider } from "./primitives";

afterEach(cleanup);
const options = [{ value: "auto", label: "אוטומטית — ברירת הספק" }, { value: "disabled", label: "מושבתת", disabled: true }, { value: "high", label: "גבוהה" }];

test("opens on the saved value, skips disabled choices and saves only on explicit selection", async () => {
  const save = vi.fn();
  function Example() {
    const [value, setValue] = useState("high");
    return <ChoiceField label="חשיבה" value={value} options={options} onValueChange={next => { save(next); setValue(next); }} />;
  }
  render(<DesignSystemProvider theme="light"><Example /></DesignSystemProvider>);
  const trigger = screen.getByRole("button", { name: "חשיבה" });
  trigger.focus(); await userEvent.keyboard("{ArrowDown}");
  expect(document.activeElement).toBe(screen.getByRole("option", { name: "גבוהה" }));
  await userEvent.keyboard("{Home}{ArrowDown}");
  expect(document.activeElement).toBe(screen.getByRole("option", { name: "גבוהה" }));
  expect(save).not.toHaveBeenCalled();
  await userEvent.keyboard("{Home}{Enter}");
  expect(save).toHaveBeenCalledExactlyOnceWith("auto");
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(document.activeElement).toBe(trigger);
  const description = document.getElementById(trigger.getAttribute("aria-describedby")!.split(" ")[0]);
  expect(description?.textContent).toBe("אוטומטית — ברירת הספק");
});

test("Escape and Tab resume from the trigger; outside focus is preserved", async () => {
  const save = vi.fn();
  render(<><ChoiceField label="חשיבה" value="auto" options={options} onValueChange={save} /><Button>הבא</Button></>);
  const trigger = screen.getByRole("button", { name: "חשיבה" }), next = screen.getByRole("button", { name: "הבא" });
  await userEvent.click(trigger); await userEvent.keyboard("{End}{Escape}");
  expect(screen.queryByRole("listbox")).toBeNull(); expect(document.activeElement).toBe(trigger);
  await userEvent.click(trigger); await userEvent.tab();
  expect(screen.queryByRole("listbox")).toBeNull(); expect(document.activeElement).toBe(next);
  await userEvent.click(trigger); await userEvent.click(next);
  expect(screen.queryByRole("listbox")).toBeNull(); expect(document.activeElement).toBe(next);
  await userEvent.click(trigger); await userEvent.click(trigger);
  expect(screen.queryByRole("listbox")).toBeNull(); expect(save).not.toHaveBeenCalled();
});

test("lookup moves focus without saving, and an unknown saved value stays intact until selected", async () => {
  const save = vi.fn();
  render(<ChoiceField label="חשיבה" value="legacy" options={options} onValueChange={save} />);
  const trigger = screen.getByRole("button", { name: "חשיבה" });
  await userEvent.click(trigger); expect(document.activeElement).toBe(screen.getByRole("option", { name: "אוטומטית — ברירת הספק" }));
  await userEvent.keyboard("ג"); expect(document.activeElement).toBe(screen.getByRole("option", { name: "גבוהה" }));
  await userEvent.keyboard("{Escape}"); expect(save).not.toHaveBeenCalled();
  expect(trigger.textContent).toContain("legacy");
});

test("disabled and empty controls cannot open; help and errors remain associated", async () => {
  render(<><ChoiceField label="חשיבה" hiddenLabel value="auto" options={options} onValueChange={vi.fn()} disabled hint="עזרה" error="כשל" />
    <ChoiceField label="ריק" value="" options={[]} onValueChange={vi.fn()} /></>);
  const trigger = screen.getByLabelText("חשיבה");
  expect(trigger.getAttribute("aria-invalid")).toBe("true");
  expect(trigger.getAttribute("aria-haspopup")).toBe("dialog");
  expect(trigger.getAttribute("aria-describedby")!.split(" ").map(id => document.getElementById(id)?.textContent)).toEqual(["אוטומטית — ברירת הספק", "עזרה", "כשל"]);
  expect(screen.getByRole("alert").textContent).toBe("כשל");
  await userEvent.click(trigger); await userEvent.click(screen.getByRole("button", { name: "ריק" }));
  expect(screen.queryByRole("listbox")).toBeNull();
});
