// @vitest-environment jsdom
import { useState } from "react";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button, ConfirmDialog, DesignSystemProvider, Dialog, Field, IconButton, Menu, MessageFrame, RangeField, Switch, Tabs, Textarea, Tooltip, UserBubble } from "./primitives";
afterEach(() => { cleanup(); vi.useRealTimers(); });
beforeAll(() => {
  // jsdom lacks native dialog behavior; real modality is tested in Edge.
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
const wrap = (children: React.ReactNode) => <DesignSystemProvider theme="light">{children}</DesignSystemProvider>;
describe("UX-2 shared interaction contracts", () => {
  test("dialog Escape stays inside the dialog before native cancellation", () => {
    const ancestor = vi.fn(), close = vi.fn();
    window.addEventListener("keydown", ancestor);
    try {
      render(wrap(<Dialog open title="עריכה" onClose={close}><Field label="טיוטה" /></Dialog>));
      fireEvent.keyDown(screen.getByRole("textbox"), { key: "Escape" });
      expect(ancestor).not.toHaveBeenCalled();
      fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: false, cancelable: true }));
      expect(close).toHaveBeenCalledTimes(1);
    } finally { window.removeEventListener("keydown", ancestor); }
  });
  test("loading actions suppress duplicate clicks and keep the accessible name", async () => {
    const onClick = vi.fn(); render(wrap(<Button loading onClick={onClick}>שמירה</Button>));
    const button = screen.getByRole("button", { name: "שמירה" }); await userEvent.click(button);
    expect(button.getAttribute("aria-busy")).toBe("true"); expect(onClick).not.toHaveBeenCalled();
  });
  test("field help and errors reference unique labels without losing external descriptions", () => {
    render(wrap(<><Field label="שם" hint="עזרה" error="תקלה" aria-describedby="external" /><Field label="שם נוסף" /><Textarea label="הערות" /></>));
    const field = screen.getByRole("textbox", { name: "שם" });
    expect(field.getAttribute("aria-invalid")).toBe("true");
    const references = field.getAttribute("aria-describedby")!.split(" ");
    expect(references).toContain("external"); expect(document.getElementById(references[1])?.textContent).toBe("עזרה");
    expect(document.getElementById(references[2])?.getAttribute("role")).toBe("alert");
    expect(field.id).not.toBe(screen.getByRole("textbox", { name: "שם נוסף" }).id);
    expect(screen.getByRole("textbox", { name: "הערות" }).getAttribute('dir')).toBe('auto');
  });
  test("switch remains controlled, supports Space and respects disabled", async () => {
    function Example() { const [checked, update] = useState(false); return <Switch label="כלי" checked={checked} onCheckedChange={update} />; }
    render(wrap(<Example />)); const control = screen.getByRole("switch", { name: "כלי" });
    control.focus(); await userEvent.keyboard(" "); expect((control as HTMLInputElement).checked).toBe(true);
    cleanup(); const onChange = vi.fn(); render(wrap(<Switch label="כלי" checked={false} disabled onCheckedChange={onChange} />));
    await userEvent.click(screen.getByRole("switch")); expect(onChange).not.toHaveBeenCalled();
  });
  test("range passes the numeric value directly without inventing persistence or unlimited semantics", () => {
    const change = vi.fn(); render(wrap(<RangeField label="עוצמה" min={0} max={100} value={0} onValueChange={change} formatValue={(v) => v === 0 ? "ללא הגבלה" : `${v}%`} />));
    const range = screen.getByRole("slider"); expect(range.getAttribute("aria-valuetext")).toBe("ללא הגבלה");
    fireEvent.change(range, { target: { value: "60" } }); expect(change).toHaveBeenCalledWith(60);
  });
  test("menu skips disabled actions, toggles, handles arrows and returns focus on Escape", async () => {
    const select = vi.fn(); render(wrap(<Menu label="פעולות" items={[{ id: "one", label: "עריכה", onSelect: select }, { id: "two", label: "מושבת", disabled: true, onSelect: select }, { id: "three", label: "מחיקה", onSelect: select }]} />));
    const trigger = screen.getByRole("button", { name: "פעולות" }); trigger.focus(); await userEvent.keyboard("{ArrowDown}");
    expect(document.activeElement?.textContent).toBe("עריכה"); await userEvent.keyboard("{ArrowDown}"); expect(document.activeElement?.textContent).toBe("מחיקה");
    await userEvent.keyboard("{Escape}"); expect(screen.queryByRole("menu")).toBeNull(); expect(document.activeElement).toBe(trigger);
    await userEvent.click(trigger); await userEvent.click(trigger); expect(screen.queryByRole("menu")).toBeNull();
    await userEvent.click(trigger); await userEvent.click(screen.getByRole("menuitem", { name: "עריכה" })); expect(select).toHaveBeenCalledTimes(1); expect(document.activeElement).toBe(trigger);
  });
  test("outside interaction closes a menu without stealing the destination focus", async () => {
    render(wrap(<><Menu label="פעולות" items={[{ id: "one", label: "עריכה", onSelect: () => undefined }]} /><Button>בחוץ</Button></>));
    await userEvent.click(screen.getByRole("button", { name: "פעולות" })); const outside = screen.getByRole("button", { name: "בחוץ" }); await userEvent.click(outside);
    expect(screen.queryByRole("menu")).toBeNull(); expect(document.activeElement).toBe(outside);
  });
  test("tabs use linked panels and visual RTL arrows, preserving panel content", async () => {
    function Example() { const [active, set] = useState("a"); return <Tabs label="עמודים" active={active} onSelect={set} tabs={[{ id: "a", label: "א", panel: <input aria-label="טיוטה" defaultValue="שמור" /> }, { id: "disabled", label: "מושבת", disabled: true, panel: null }, { id: "b", label: "ב", panel: "תוכן ב" }]} />; }
    render(wrap(<Example />)); const first = screen.getByRole("tab", { name: "א" }); first.focus(); await userEvent.keyboard("{ArrowLeft}");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "ב" })); expect(screen.getByRole("tabpanel").textContent).toBe("תוכן ב");
    await userEvent.keyboard("{Home}"); expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("שמור");
    expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe(first.id);
  });
  test("dialog titles are unique and focus is restored when closing", async () => {
    function Example() { const [open, set] = useState(false); return <><Button onClick={() => set(true)}>פתח</Button><Dialog open={open} title="חלונית" onClose={() => set(false)}>תוכן</Dialog></>; }
    render(wrap(<Example />)); const trigger = screen.getByRole("button", { name: "פתח" }); await userEvent.click(trigger);
    const dialog = screen.getByRole("dialog"); expect(document.getElementById(dialog.getAttribute("aria-labelledby")!)?.textContent).toBe("חלונית");
    expect(document.activeElement).toBe(dialog); await userEvent.click(screen.getByRole("button", { name: "סגירה" })); expect(document.activeElement).toBe(trigger);
  });
  test("confirmation focuses cancel, reports failure, and never confirms on cancel", async () => {
    const confirm = vi.fn(); const close = vi.fn(); render(wrap(<ConfirmDialog open title="מחיקה" description="פריט" confirmLabel="מחק" error="נכשל" onConfirm={confirm} onClose={close} />));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "ביטול" })); expect(screen.getByRole("alert").textContent).toContain("נכשל");
    await userEvent.click(screen.getByRole("button", { name: "ביטול" })); expect(close).toHaveBeenCalledOnce(); expect(confirm).not.toHaveBeenCalled();
  });
  test("tooltip appears on focus, preserves description and dismisses on Escape", async () => {
    render(wrap(<Tooltip label="עזרה"><button aria-describedby="help">פקד</button></Tooltip>));
    await userEvent.tab(); expect(screen.getByRole("tooltip").textContent).toBe("עזרה"); expect(screen.getByRole("button").getAttribute("aria-describedby")).toContain("help");
    await userEvent.keyboard("{Escape}"); expect(screen.queryByRole("tooltip")).toBeNull();
  });
  test("tooltip escapes a clipped provider and disappears immediately on pointer leave", async () => {
    render(wrap(<div style={{ overflow: "hidden" }}><Tooltip label="משימות"><button>פתח משימות</button></Tooltip></div>));
    const button = screen.getByRole("button", { name: "פתח משימות" });
    await userEvent.hover(button);
    expect(screen.getByRole("tooltip").closest(".sds-floating-layer")?.parentElement).toBe(document.body);
    await userEvent.unhover(button);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
  test("a self-explanatory icon retains its accessible name without a tooltip", async () => {
    render(wrap(<IconButton icon="copy" label="העתק" tooltip={false} />));
    const button = screen.getByRole("button", { name: "העתק" });
    await userEvent.hover(button); await userEvent.tab();
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(button.getAttribute("aria-label")).toBe("העתק");
  });
  test("a hovered tooltip cannot intercept Escape from an open menu", async () => {
    render(wrap(<><Tooltip label="הכתבה"><button>קול</button></Tooltip><Menu label="פעולות" items={[{ id: "one", label: "עריכה", onSelect: () => undefined }]} /></>));
    await userEvent.hover(screen.getByRole('button', { name: 'קול' }));
    const trigger = screen.getByRole('button', { name: 'פעולות' }); trigger.focus(); await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('tooltip')).not.toBeNull(); await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).toBeNull(); expect(document.activeElement).toBe(trigger);
  });
  test("message outputs precede all actions in an explicit slot", () => {
    const { container } = render(wrap(<MessageFrame outputs={<span>תוצר</span>} actions={<Button>העתקה</Button>}>תוכן</MessageFrame>));
    const order = Array.from(container.querySelector("article")!.children).map((node) => node.textContent);
    expect(order).toEqual(["תוכן", "תוצר", "העתקה"]);
  });
  test("new-message entry is consumed even without an animationend event and does not replay on rerender", () => {
    vi.useFakeTimers(); const { container, rerender } = render(wrap(<UserBubble isNew>חדש</UserBubble>));
    expect(container.querySelector('.sds-user-bubble--new')).not.toBeNull();
    act(() => vi.advanceTimersByTime(240)); expect(container.querySelector('.sds-user-bubble--new')).toBeNull();
    rerender(wrap(<UserBubble isNew>תוכן מעודכן</UserBubble>)); expect(container.querySelector('.sds-user-bubble--new')).toBeNull();
  });
});
