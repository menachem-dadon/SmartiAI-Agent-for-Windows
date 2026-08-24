import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { Point16AVisualFixture } from "./Point16AVisualFixture";
import { VoiceOverlayWindow } from "./VoiceOverlayWindow";
import { Point16BVisualFixture } from "./Point16BVisualFixture";

const voiceOverlay = new URLSearchParams(location.search).get("voice-overlay") === "1";
const voiceFixture =
  import.meta.env.DEV &&
  new URLSearchParams(location.search).get("visual-fixture") === "point16a-voice";
const visualFixture =
  import.meta.env.DEV &&
  new URLSearchParams(location.search).get("visual-fixture") === "point16a";
const point16BFixture = import.meta.env.DEV ? new URLSearchParams(location.search).get("visual-fixture") : "";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    {voiceOverlay || voiceFixture ? <VoiceOverlayWindow fixture={voiceFixture} /> : visualFixture ? <Point16AVisualFixture /> : point16BFixture === "point16b-management" ? <Point16BVisualFixture /> : point16BFixture === "point16b-legal" ? <Point16BVisualFixture page="legal" /> : <App />}
  </React.StrictMode>,
);
