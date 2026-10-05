// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { MessageTable } from "./MessageTable";
import { RichMessage } from "./RichMessage";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

const write = vi.fn();
const writeText = vi.fn();
const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
class TestClipboardItem {
  constructor(readonly data: Record<string, Blob>) {}
}
function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsText(blob);
  });
}
function sampleTable() {
  return <MessageTable style={{ direction: "rtl" }}>
    <thead><tr><th>שם</th><th>הערה</th><th>סכום</th></tr></thead>
    <tbody>
      <tr><td>דנה</td><td>{'אמר "שלום", שוב'}</td><td>-12.5</td></tr>
      <tr><td>עוד</td><td>שורה<br />שנייה</td><td>=1+1</td></tr>
      <tr><td></td><td>00123</td><td></td></tr>
    </tbody>
  </MessageTable>;
}

beforeEach(() => {
  vi.mocked(invoke).mockReset();
  write.mockReset().mockResolvedValue(undefined);
  writeText.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { write, writeText } });
  vi.stubGlobal("ClipboardItem", TestClipboardItem);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  if (originalClipboard) Object.defineProperty(navigator, "clipboard", originalClipboard);
  else Reflect.deleteProperty(navigator, "clipboard");
});

describe("chat table copy and export", () => {
  test("copies only the selected Markdown table and keeps it mounted across message updates", async () => {
    vi.stubGlobal("ClipboardItem", undefined);
    const message = {
      role: "assistant" as const,
      content: "טקסט מסביב\n\n| שם | כמות |\n| --- | ---: |\n| ראשון | 1 |\n\nוגם\n\n| סוג | כמות |\n| --- | ---: |\n| שני | 2 |",
    };
    const view = render(<RichMessage message={message} />);
    const tables = screen.getAllByRole("table");
    expect(tables).toHaveLength(2);
    expect(tables[1].querySelectorAll("th")[1].style.textAlign).toBe("right");
    const frame = tables[1].closest(".message-table-frame") as HTMLElement;
    fireEvent.click(within(frame).getByRole("button", { name: "העתק טבלה" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("סוג\tכמות\r\nשני\t2"));
    expect(within(frame).queryByRole("status")).toBeNull();
    view.rerender(<RichMessage message={{ ...message, content: `${message.content}\n\nעוד טקסט` }} />);
    expect(screen.getAllByRole("table")[1]).toBe(tables[1]);
    expect(within(frame).queryByRole("status")).toBeNull();
  });

  test("copies a standalone RTL HTML table plus tab-separated text, with no toolbar or executable markup", async () => {
    render(<MessageTable style={{ direction: "rtl" }}>
      <thead><tr><th>פריט</th><th style={{ textAlign: "center" }}>תיאור</th></tr></thead>
      <tbody><tr><td><strong>טקסט</strong><br /><img src="https://example.com/p.png" alt="תמונה" /></td><td>{'<script>alert("x")</script>'}</td></tr></tbody>
    </MessageTable>);
    fireEvent.click(screen.getByRole("button", { name: "העתק טבלה" }));
    await waitFor(() => expect(write).toHaveBeenCalledOnce());
    const item = write.mock.calls[0][0][0] as TestClipboardItem;
    const html = await readBlob(item.data["text/html"]);
    const plain = await readBlob(item.data["text/plain"]);
    const copy = new DOMParser().parseFromString(html, "text/html");
    expect(copy.querySelectorAll("table")).toHaveLength(1);
    expect(copy.querySelector("table")?.dir).toBe("rtl");
    expect(copy.querySelectorAll("th")[1].style.textAlign).toBe("center");
    expect(copy.querySelectorAll("td")[0].textContent).toBe("טקסט\nתמונה");
    expect(copy.querySelectorAll("td")[1].textContent).toBe('<script>alert("x")</script>');
    expect(copy.querySelector("button, img, script")).toBeNull();
    expect(plain).toContain("פריט\tתיאור\r\n");
    expect(plain).toContain('"טקסט\nתמונה"');
    expect(writeText).not.toHaveBeenCalled();
  });

  test("falls back to plain text when rich clipboard writing is rejected", async () => {
    write.mockRejectedValue(new Error("HTML clipboard unavailable"));
    render(sampleTable());
    fireEvent.click(screen.getByRole("button", { name: "העתק טבלה" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText.mock.calls[0][0]).toContain("שם\tהערה\tסכום");
  });

  test("exports UTF-8 CSV with Hebrew, quotes, commas, multiline and empty cells, and literal formulas", async () => {
    vi.mocked(invoke).mockResolvedValue("C:\\Exports\\table.csv");
    render(sampleTable());
    fireEvent.click(screen.getByRole("button", { name: "ייצוא CSV" }));
    await waitFor(() => expect(invoke).toHaveBeenCalledOnce());
    expect(invoke).toHaveBeenCalledWith("save_text_file", {
      suggestedName: "smarti_table.csv",
      contents: '\uFEFFשם,הערה,סכום\r\nדנה,"אמר ""שלום"", שוב",-12.5\r\nעוד,"שורה\nשנייה",\'=1+1\r\n,00123,\r\n',
    });
  });

  test("disables repeat actions while the save dialog is open and treats cancellation as cancellation", async () => {
    let finish!: (result: null) => void;
    vi.mocked(invoke).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    render(sampleTable());
    fireEvent.click(screen.getByRole("button", { name: "ייצוא CSV" }));
    expect((screen.getByRole("button", { name: "ייצוא CSV" }) as HTMLButtonElement).disabled).toBe(true);
    const copyButton = screen.getByRole("button", { name: "העתק טבלה" });
    expect((copyButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(copyButton);
    expect(write).not.toHaveBeenCalled();
    finish(null);
    await waitFor(() => expect((screen.getByRole("button", { name: "ייצוא CSV" }) as HTMLButtonElement).disabled).toBe(false));
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test.each(["copy", "export"])("reports a failed %s and allows retry", async (action) => {
    write.mockRejectedValue(new Error("Denied"));
    writeText.mockRejectedValueOnce(new Error("Denied"));
    vi.mocked(invoke).mockRejectedValueOnce(new Error("Disk full"));
    render(sampleTable());
    const name = action === "copy" ? "העתק טבלה" : "ייצוא CSV";
    fireEvent.click(screen.getByRole("button", { name }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("נכשלה"));
    expect((screen.getByRole("button", { name }) as HTMLButtonElement).disabled).toBe(false);
    write.mockResolvedValue(undefined);
    vi.mocked(invoke).mockResolvedValue("C:\\Exports\\table.csv");
    fireEvent.click(screen.getByRole("button", { name }));
    await waitFor(() => expect((screen.getByRole("button", { name }) as HTMLButtonElement).disabled).toBe(false));
    expect(action === "copy" ? write.mock.calls.length : vi.mocked(invoke).mock.calls.length).toBe(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
