// @vitest-environment jsdom
import { useRef, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DismissibleDetails, useDismissiblePopup } from "./popupDismissal";

afterEach(() => cleanup());

function StatePopup({ onOutside }: { onOutside: () => void }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);
  useDismissiblePopup({
    open,
    roots: [root],
    onDismiss: () => setOpen(false),
  });
  return (
    <>
      <div ref={root}>
        <button type="button" onClick={() => setOpen((value) => !value)}>
          פתח תפריט
        </button>
        {open && <div role="menu">תוכן</div>}
      </div>
      <button type="button" onClick={onOutside}>
        פעולה חיצונית
      </button>
    </>
  );
}

describe("dismissible popup behavior", () => {
  it("closes on an outside pointer without swallowing the outside action", () => {
    let outsideClicks = 0;
    render(<StatePopup onOutside={() => outsideClicks++} />);
    fireEvent.click(screen.getByRole("button", { name: "פתח תפריט" }));
    expect(screen.getByRole("menu")).toBeTruthy();

    const outside = screen.getByRole("button", { name: "פעולה חיצונית" });
    fireEvent.pointerDown(outside);
    fireEvent.click(outside);

    expect(screen.queryByRole("menu")).toBeNull();
    expect(outsideClicks).toBe(1);
  });

  it("treats a repeated trigger click as close and dismisses details outside", () => {
    render(
      <>
        <DismissibleDetails>
          <summary>מודלים</summary>
          <div role="menu">מודל ראשי</div>
        </DismissibleDetails>
        <button type="button">מחוץ</button>
      </>,
    );
    const trigger = screen.getByText("מודלים");
    const details = trigger.closest("details")!;

    fireEvent.click(trigger);
    expect(details.open).toBe(true);
    fireEvent.click(trigger);
    expect(details.open).toBe(false);

    fireEvent.click(trigger);
    expect(details.open).toBe(true);
    fireEvent.pointerDown(screen.getByRole("button", { name: "מחוץ" }));
    expect(details.open).toBe(false);
  });
});
