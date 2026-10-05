import { useEffect, useRef, useState } from "react";
import type { ComponentPropsWithoutRef } from "react";
import type { ExtraProps } from "react-markdown";
import { invoke } from "@tauri-apps/api/core";
import type { ResolvedTheme } from "./designSystem";
import { IconButton } from "./design-system";

function cellText(cell: HTMLTableCellElement): string {
  const content = cell.cloneNode(true) as HTMLElement;
  content.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
  content.querySelectorAll("img").forEach((img) => img.replaceWith(img.alt));
  return (content.textContent || "").replace(/\r\n?/g, "\n");
}

function spreadsheetText(value: string): string {
  // Export model-provided formulas as literal text, but keep negative numbers numeric.
  const numeric = /^-\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(value.trim());
  return !numeric && /^\s*[=+@-]/u.test(value) ? `'${value}` : value;
}

function delimitedText(rows: string[][], delimiter: string): string {
  return rows.map((row) => row.map((value) => {
    const text = spreadsheetText(value);
    return text.includes(delimiter) || /["\r\n]/u.test(text)
      ? `"${text.replace(/"/g, '""')}"`
      : text;
  }).join(delimiter)).join("\r\n");
}

function clipboardHtml(table: HTMLTableElement, rows: string[][]): string {
  // Build a self-contained table without chat controls, application attributes or remote images.
  const result = table.ownerDocument.createElement("table");
  const direction = getComputedStyle(table).direction === "rtl" ? "rtl" : "ltr";
  result.dir = direction;
  result.style.cssText = "border-collapse:collapse;font-family:Segoe UI,Arial,sans-serif;color:#111;background:#fff";
  for (const [rowIndex, row] of Array.from(table.rows).entries()) {
    const section = row.parentElement?.tagName === "THEAD"
      ? result.tHead || result.createTHead()
      : result.tBodies[0] || result.createTBody();
    const copyRow = section.insertRow();
    for (const [cellIndex, cell] of Array.from(row.cells).entries()) {
      const copyCell = table.ownerDocument.createElement(cell.tagName.toLowerCase());
      copyCell.textContent = rows[rowIndex][cellIndex];
      copyCell.style.cssText = "border:1px solid #9ca3af;padding:8px 12px;vertical-align:top;white-space:pre-wrap";
      copyCell.style.textAlign = cell.style.textAlign || (direction === "rtl" ? "right" : "left");
      if (cell.tagName === "TH") {
        copyCell.setAttribute("scope", "col");
        copyCell.style.backgroundColor = "#eef2f7";
        copyCell.style.fontWeight = "700";
      }
      copyRow.append(copyCell);
    }
  }
  return result.outerHTML;
}

export function MessageTable({
  node: _node,
  theme: _theme = "dark",
  ...props
}: ComponentPropsWithoutRef<"table"> & ExtraProps & { theme?: ResolvedTheme }) {
  const tableRef = useRef<HTMLTableElement>(null);
  const [busy, setBusy] = useState<"copy" | "export" | null>(null);
  const [feedback, setFeedback] = useState<{ text: string; error?: boolean } | null>(null);

  useEffect(() => {
    if (!feedback || feedback.error) return;
    const timer = window.setTimeout(() => setFeedback(null), 3000);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  async function perform(action: "copy" | "export") {
    const table = tableRef.current;
    if (!table || busy) return;
    setBusy(action);
    setFeedback(null);
    try {
      const rows = Array.from(table.rows, (row) => Array.from(row.cells, cellText));
      if (action === "export") {
        const path = await invoke<string | null>("save_text_file", {
          suggestedName: "smarti_table.csv",
          contents: `\uFEFF${delimitedText(rows, ",")}\r\n`,
        });
        if (path) setFeedback({ text: "הקובץ נשמר" });
      } else {
        const plainText = delimitedText(rows, "\t");
        let richCopy = false;
        if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
          try {
            await navigator.clipboard.write([new ClipboardItem({
              "text/html": new Blob([clipboardHtml(table, rows)], { type: "text/html" }),
              "text/plain": new Blob([plainText], { type: "text/plain" }),
            })]);
            richCopy = true;
          } catch {
            // Some WebViews only permit plain-text clipboard writes.
          }
        }
        if (!richCopy) await navigator.clipboard.writeText(plainText);
        setFeedback({ text: richCopy ? "הטבלה הועתקה" : "הטבלה הועתקה כטקסט" });
      }
    } catch {
      setFeedback({
        text: action === "copy" ? "העתקת הטבלה נכשלה. נסה שוב." : "שמירת הקובץ נכשלה. נסה שוב.",
        error: true,
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="message-table-frame">
      <div className="message-table-actions" role="group" aria-label="פעולות טבלה" dir="rtl">
        <IconButton tooltip={false} icon="copy" label="העתק טבלה" variant="ghost" loading={busy === "copy"} disabled={busy !== null} onClick={() => void perform("copy")} />
        <IconButton icon="download" label="ייצוא CSV" variant="ghost" loading={busy === "export"} disabled={busy !== null} onClick={() => void perform("export")} />
      </div>
      <div className="message-table-scroll" role="region" aria-label="טבלה בהודעה" tabIndex={0}>
        <table {...props} ref={tableRef} />
      </div>
      {feedback?.error && (
        <p className="message-table-feedback" role={feedback.error ? "alert" : "status"} dir="rtl">
          {feedback.text}
        </p>
      )}
    </div>
  );
}
