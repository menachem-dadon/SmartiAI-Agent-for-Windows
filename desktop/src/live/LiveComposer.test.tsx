// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { Composer } from "../Composer";
import { RichMessage } from "../RichMessage";
import type { LiveController } from "./useLiveConversation";
vi.mock("../coreApi", () => ({ coreApi: vi.fn(async () => ({ available:false })), encodePath: encodeURIComponent }));
afterEach(cleanup);
const controller = (active = false) => ({ available:true, active, ready:active, phase:active ? "ready" : "closed", micMuted:false, outputMuted:false,
  orbState:"listening", level:{current:0}, tasks:[], start:vi.fn(), stop:vi.fn(), toggleMic:vi.fn(), toggleOutput:vi.fn(), send:vi.fn(), control:vi.fn() }) as unknown as LiveController;
test("the Live action becomes send and stop while the dictation microphone keeps its purpose", async () => {
  const live = controller(), onSend=vi.fn(async()=>{}), onCancel=vi.fn();
  const props = {attachments:[],onAttachments:vi.fn(),onSend,onCancel,live,draft:"",running:false};
  const view=render(<Composer {...props}/>);
  expect(screen.getByRole("button",{name:"פתיחת לייב"})).toBeTruthy();
  view.rerender(<Composer {...props} draft="בקשה"/>);
  expect(screen.getByRole("button",{name:"שליחה"}).classList.contains("live-toggle")).toBe(true);
  expect(screen.getByRole("button",{name:"הכתבה קולית"}).querySelector('[data-icon="mic"]')).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"שליחה"}));
  await waitFor(()=>expect(onSend).toHaveBeenCalledWith("בקשה"));
  const active=controller(true);
  view.rerender(<Composer {...props} live={active} running/>);
  fireEvent.click(screen.getByRole("button",{name:"סגירת לייב"}));
  expect(active.stop).toHaveBeenCalledOnce(); expect(onCancel).not.toHaveBeenCalled();
  view.rerender(<Composer {...props} running/>);
  const stop=screen.getByRole("button",{name:"עצירה"});
  expect(stop.classList.contains("live-toggle")).toBe(true);
  fireEvent.click(stop); expect(onCancel).toHaveBeenCalledOnce();
});
test("the final Live copy excludes the introduction and retains code, table and links", async () => {
  const writeText=vi.fn(async()=>{});
  Object.defineProperty(navigator,"clipboard",{configurable:true,value:{writeText}});
  const final="התוצאה\n\n```py\nprint(42)\n```\n\n| ערך | תוצאה |\n|---|---|\n| א | 42 |\n\n[קובץ](https://example.test/result)";
  const {container}=render(<RichMessage message={{role:"assistant",content:final,metadata:{live_session_id:"live",live_final:true,live_answer_id:"answer",live_prefix:[{role:"assistant",content:"אני מתחיל לעבוד",metadata:{live_session_id:"live"}}]}}}/>);
  expect(screen.getByText("אני מתחיל לעבוד")).toBeTruthy();
  const actions=container.querySelectorAll<HTMLElement>(".sds-message-actions");
  expect(actions).toHaveLength(1);
  fireEvent.click(within(actions[0]).getByRole("button",{name:"העתק"}));
  await waitFor(()=>expect(writeText).toHaveBeenCalledWith(final));
  expect(screen.queryByRole("button",{name:"השהה משימה"})).toBeNull();
});
