// @vitest-environment jsdom
import { afterEach, expect, test } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Icon, iconNames, tablerIcons } from "./icons";
import { Button, DesignSystemProvider, Field } from "./primitives";

afterEach(cleanup);

test("every semantic action has a decorative scalable Tabler SVG", () => {
  const { container } = render(<DesignSystemProvider theme="dark">{iconNames.map(name => <Icon key={name} name={name} size={32} />)}</DesignSystemProvider>);
  const icons = container.querySelectorAll("svg.sds-icon");
  expect(icons.length).toBe(64);
  expect(container.querySelector("img")).toBeNull();
  for (const icon of icons) {
    expect(icon.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(icon.getAttribute("width")).toBe("32");
    expect(icon.getAttribute("aria-hidden")).toBe("true");
    expect(icon.getAttribute("focusable")).toBe("false");
    expect(icon.querySelector("path,line,polyline,polygon,circle,ellipse,rect")).not.toBeNull();
  }
});

test("physical action directions and the original folding baseline stay explicit", () => {
  const { container } = render(<><Icon name="send" /><Icon name="back" /><Icon name="forward" /><Icon name="chevron" /></>);
  expect(container.querySelector('[data-icon="send"]')?.classList.contains("tabler-icon-arrow-up")).toBe(true);
  expect(tablerIcons.back).not.toBe(tablerIcons.forward);
  expect(container.querySelector('[data-icon="back"]')?.classList.contains("tabler-icon-arrow-left")).toBe(true);
  expect(container.querySelector('[data-icon="forward"]')?.classList.contains("tabler-icon-arrow-right")).toBe(true);
  // The retained PNG is drawn down; a shared 90deg rotation must mean collapsed-left in both families.
  expect(container.querySelector('[data-icon="chevron"]')?.classList.contains("tabler-icon-chevron-down")).toBe(true);
});

test("changing artwork preserves typed content, focus and accessible action names", () => {
  const content = <><Field label="שם" defaultValue="טיוטה" /><Button icon="send">שליחה</Button></>;
  const { container, rerender } = render(<DesignSystemProvider theme="light">{content}</DesignSystemProvider>);
  const field = screen.getByRole("textbox", { name: "שם" });
  fireEvent.change(field, { target: { value: "טיוטה חדשה" } }); field.focus();
  rerender(<DesignSystemProvider theme="dark" iconFamily="original">{content}</DesignSystemProvider>);
  const original = container.querySelector<HTMLImageElement>('img[data-icon="send"]');
  expect(original?.src).toContain("send-dark.png");
  expect(document.activeElement).toBe(field);
  expect((field as HTMLInputElement).value).toBe("טיוטה חדשה");
  expect(screen.getByRole("button", { name: "שליחה" })).not.toBeNull();
  rerender(<DesignSystemProvider theme="dark">{content}</DesignSystemProvider>);
  expect(container.querySelector('svg[data-icon="send"]')).not.toBeNull();
  expect((field as HTMLInputElement).value).toBe("טיוטה חדשה");
});
