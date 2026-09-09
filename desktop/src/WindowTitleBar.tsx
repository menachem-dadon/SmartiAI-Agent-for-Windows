import { useEffect, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";

// Windows caption glyphs, also available in Segoe MDL2 Assets on Windows 10.
// https://learn.microsoft.com/windows/apps/design/iconography/segoe-fluent-icons-font
const captionGlyphs = {
  minimize: "\uE921",
  maximize: "\uE922",
  restore: "\uE923",
  close: "\uE8BB",
} as const;

export function WindowCaptionIcon({ action }: { action: keyof typeof captionGlyphs }) {
  return <span className="window-caption-icon" aria-hidden="true">{captionGlyphs[action]}</span>;
}

export function WindowTitleBar() {
  const [appWindow] = useState(getCurrentWindow);
  const [maximized, setMaximized] = useState(false);
  useEffect(() => {
    let alive = true;
    let request = 0;
    const sync = () => {
      const current = ++request;
      void appWindow.isMaximized().then((value) => {
        if (alive && current === request) setMaximized(value);
      }).catch((reason) => console.error("Failed to read window state", reason));
    };
    const listener = appWindow.onResized(sync);
    void listener.then(() => { if (alive) sync(); })
      .catch((reason) => console.error("Failed to watch window state", reason));
    return () => {
      alive = false;
      void listener.then((dispose) => dispose()).catch(() => {});
    };
  }, [appWindow]);
  return (
    <header className="window-titlebar" dir="ltr">
      {/* Tauri handles dragging and double-click maximize on this region.
          A React double-click handler would toggle a second time. */}
      <div className="window-drag-region" data-tauri-drag-region />
      <button
        type="button"
        aria-label="מזער"
        title="מזער"
        onClick={() => void appWindow.minimize()}
      >
        <WindowCaptionIcon action="minimize" />
      </button>
      <button
        type="button"
        aria-label={maximized ? "שחזר" : "הגדל"}
        title={maximized ? "שחזר" : "הגדל"}
        onClick={() => void appWindow.toggleMaximize()}
      >
        <WindowCaptionIcon action={maximized ? "restore" : "maximize"} />
      </button>
      <button
        type="button"
        className="window-close"
        aria-label="סגירה"
        title="סגירה"
        onClick={() => void appWindow.close()}
      >
        <WindowCaptionIcon action="close" />
      </button>
    </header>
  );
}
