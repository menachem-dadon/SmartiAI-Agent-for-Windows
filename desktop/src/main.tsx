import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { InterfaceLoading, InterfaceRecovery } from "./InterfaceRecovery";
import { VoiceOverlayWindow } from "./VoiceOverlayWindow";
import "./interfaceRecovery.css";

const App = lazy(() => import("./App"));
const Point16AVisualFixture = import.meta.env.DEV ? lazy(() => import("./Point16AVisualFixture").then(module => ({ default: module.Point16AVisualFixture }))) : null;
const Point16BVisualFixture = import.meta.env.DEV ? lazy(() => import("./Point16BVisualFixture").then(module => ({ default: module.Point16BVisualFixture }))) : null;

const voiceOverlay = new URLSearchParams(location.search).get("voice-overlay") === "1";
const voiceFixture =
  import.meta.env.DEV &&
  new URLSearchParams(location.search).get("visual-fixture") === "point16a-voice";
const visualFixture =
  import.meta.env.DEV &&
  new URLSearchParams(location.search).get("visual-fixture") === "point16a";
const point16BFixture = import.meta.env.DEV ? new URLSearchParams(location.search).get("visual-fixture") : "";
document.documentElement.classList.toggle("voice-overlay-document", voiceOverlay || voiceFixture);

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <InterfaceRecovery>{voiceOverlay || voiceFixture ? <VoiceOverlayWindow fixture={voiceFixture} /> : <Suspense fallback={<InterfaceLoading />}>
    {visualFixture && Point16AVisualFixture ? <Point16AVisualFixture /> : point16BFixture === "point16b-management" && Point16BVisualFixture ? <Point16BVisualFixture /> : point16BFixture === "point16b-legal" && Point16BVisualFixture ? <Point16BVisualFixture page="legal" /> : <App />}
    </Suspense>}</InterfaceRecovery>
  </React.StrictMode>,
);
