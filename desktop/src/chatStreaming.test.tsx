// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { reduceStream, streamAnswer, type StreamState } from "./chatStreaming";
import type { RunEvent } from "./chatTypes";
import { RichMessage } from "./RichMessage";

const event = (id: number, values: Record<string, unknown>[]): RunEvent => ({ event_id: id, sequence: id, run_id: "r", session_id: "s", event_type: "run_stream", created_at: "", payload: { value: { events: values.map(value => ({ request_id: "request", ...value })) } } });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
describe("live chat contracts", () => {
  test("a queued revision has its own quiet block, and a completed empty segment stays collapsed", () => {
    const message = { role: "assistant" as const, content: "", metadata: { live_schema: 2, live_process: true, live_segment_id: "revision", live_segment_after: null, live_run_status: "queued" } };
    const view = render(<RichMessage message={message} active runStatus="running"/>);
    expect(view.container.querySelector('.agent-process')).not.toBeNull();
    expect(view.container.textContent).toContain("ממתין לעדכון המשימה");
    expect(view.container.querySelector('.is-shimmering')).toBeNull();
    view.rerender(<RichMessage message={{...message,metadata:{...message.metadata,live_segment_after:9,live_run_status:"completed"}}} active runStatus="running"/>);
    expect(view.container.querySelector('details')?.open).toBe(false);
    expect(view.container.querySelector('.is-shimmering')).toBeNull();
  });
  test("streamed activity belongs only to the assistant, including a restored user run ID", () => {
    const stream: StreamState = { stage: "tool", blocks: {
      report: { kind: "text", role: "report", text: "בודק מקורות" },
      call: { kind: "tool", call_id: "call", name: "web_manager" },
    } };
    const html = renderToStaticMarkup(<RichMessage message={{ role: "user", content: "בקשה", metadata: { run_id: "same-run" } }} stream={stream}/>);
    expect(html).not.toContain("agent-process");
    expect(html).not.toContain("בודק מקורות");
    expect(html).not.toContain("לא הושלמה");
  });

  test("reports are typed from the first chunk and retry preparation never becomes execution history", () => {
    let state = reduceStream(undefined, event(1, [{ kind: "request_start" }, { kind: "text_delta", block_id: "request", text: "בודק", role: "report" }, { kind: "tool_preparing", block_id: "request:0", call_id: "request:0", name: "canvas_manager" }]));
    expect(streamAnswer(state)).toBe("");
    state = reduceStream(state, event(2, [{ kind: "request_start", request_id: "retry" }, { kind: "text_delta", request_id: "retry", block_id: "retry", text: "תשובה", role: "answer" }]));
    expect(Object.values(state.blocks).filter(block => block.kind === "tool")).toHaveLength(0);
    expect(state.blocks.request.text).toBe("בודק");
    expect(streamAnswer(state)).toBe("תשובה");
  });

  test("a saved process ignores unexecuted preparations while merging the complete streamed report once", () => {
    const html = renderToStaticMarkup(<RichMessage message={{ role: "assistant", content: "נוצר קנבס", metadata: { run_id: "saved", agent_process: { events: [
      { type: "report", text: "בודק מקורות" },
      { type: "tool_start", tools: [{ action: "web_manager", event_id: "executed" }] },
      { type: "tool_finish", results: [{ action: "web_manager", event_id: "executed", status: "ok", output_text: "SUCCESS" }] },
    ] } } }} runStatus="completed" stream={{ stage: "text", blocks: {
      old: { kind: "tool", call_id: "unexecuted", name: "canvas_manager" },
      report: { kind: "text", role: "report", text: "בודק מקורות עם טקסט חי נוסף" },
    } }}/>);
    expect(html.match(/class="agent-tool-row"/g)).toHaveLength(1);
    expect(html.match(/class="agent-report"/g)).toHaveLength(1);
    expect(html).not.toContain("לא הושלמה");
    expect(html).toContain("טקסט חי נוסף");
  });

  test("tool identity icons survive failure while X and preparation indicators precede the RTL text", () => {
    const view = render(<RichMessage message={{ role: "assistant", content: "", metadata: { run_id: "icons" } }} active stream={{ stage: "tool", blocks: { call: { kind: "tool", call_id: "call", name: "web_manager" } } }}/>);
    const preparation = view.container.querySelector(".agent-tool-row > summary")!;
    expect(preparation.lastElementChild?.getAttribute("data-icon")).toBe("globe");
    expect(preparation.children[1].querySelector(".tool-preparation-ring")).not.toBeNull();
    const events: RunEvent[] = [
      { event_id: 1, sequence: 1, event_type: "tool_started", run_id: "icons", session_id: "s", created_at: "", payload: { call_id: "call", tool: "web_manager" } },
      { event_id: 2, sequence: 2, event_type: "tool_finished", run_id: "icons", session_id: "s", created_at: "", payload: { call_id: "call", tool: "web_manager", status: "error", output: "ERROR: 429" } },
    ];
    view.rerender(<RichMessage message={{ role: "assistant", content: "", metadata: { run_id: "icons" } }} events={events} runStatus="completed"/>);
    const failed = view.container.querySelector(".agent-tool-row > summary")!;
    expect(failed.lastElementChild?.getAttribute("data-icon")).toBe("globe");
    expect(failed.children[1].querySelector('[data-icon="close"]')).not.toBeNull();
    expect(failed.querySelector('[data-icon="check"]')).toBeNull();
    expect(failed.textContent).toContain("שגיאה web_manager");
    expect(view.container.textContent).toContain("ERROR: 429");
  });

  test("append updates preserve existing reveal nodes and their elapsed fade time", () => {
    vi.useFakeTimers();vi.setSystemTime(1000);
    const message = { role: "assistant" as const, content: "תוכן קיים", metadata: { run_id: "fade" } };
    const view = render(<RichMessage message={message} active/>);
    view.rerender(<RichMessage message={{ ...message, content: message.content + " חדש" }} active/>);
    const first = view.container.querySelector<HTMLElement>(".stream-reveal")!;
    expect(first.textContent).toBe(" ");
    const initialDelay = parseFloat(first.style.animationDelay);
    vi.setSystemTime(1200);
    view.rerender(<RichMessage message={{ ...message, content: message.content + " חדש נוסף" }} active/>);
    const spans = view.container.querySelectorAll<HTMLElement>(".stream-reveal");
    expect(spans[0]).toBe(first);
    expect(parseFloat(spans[0].style.animationDelay)).toBeCloseTo(initialDelay);
    expect(parseFloat(spans[spans.length - 1].style.animationDelay)).toBeCloseTo(0);
    expect(view.container.querySelector(".message-content-body")?.textContent).toBe("תוכן קיים חדש נוסף");
  });
  test("letters fade continuously across chunk boundaries, including complete Unicode graphemes", () => {
    vi.useFakeTimers();vi.setSystemTime(1000);
    const message = { role: "assistant" as const, content: "", metadata: { run_id: "letters" } };
    const view = render(<RichMessage message={message} active/>);
    view.rerender(<RichMessage message={{ ...message, content: "אב גד" }} active/>);
    vi.setSystemTime(1120);
    view.rerender(<RichMessage message={{ ...message, content: "אב גד הו זח" }} active/>);
    const starts = [...view.container.querySelectorAll<HTMLElement>(".stream-reveal")].map(node => Number(node.dataset.revealStarted));
    expect(starts.every((started, index) => !index || started > starts[index - 1])).toBe(true);
    expect(starts[starts.length - 1]).toBe(1120);
    vi.setSystemTime(1240);
    view.rerender(<RichMessage message={{ ...message, content: "אב גד הו זח שָ 👩‍💻" }} active/>);
    const letters = [...view.container.querySelectorAll(".stream-reveal")].map(node => node.textContent);
    expect(letters).toContain("שָ");expect(letters).toContain("👩‍💻");
    vi.setSystemTime(2241);
    view.rerender(<RichMessage message={{ ...message, content: "אב גד הו זח שָ 👩‍💻!" }} active/>);
    expect([...view.container.querySelectorAll(".stream-reveal")].map(node => node.textContent)).toEqual(["!"]);
  });
  test("returning to a streamed snapshot reveals only subsequent answer and report chunks", () => {
    const message = { role: "assistant" as const, content: "תוכן שכבר נראה `C:\\qa\\קובץ.txt`", metadata: { run_id: "reveal" } };
    const report = (text: string): StreamState => ({ stage: "text", blocks: { report: { kind: "text", role: "report", text } } });
    const view = render(<RichMessage message={message} active stream={report("דיווח קיים")}/>);
    expect(view.container.querySelector(".stream-reveal")).toBeNull();
    view.rerender(<RichMessage message={{ ...message, content: message.content + " חדש" }} active stream={report("דיווח קיים נוסף")}/>);
    expect([...view.container.querySelectorAll(".stream-reveal")].map(node => node.textContent).join("")).toBe(" נוסף חדש");
    view.unmount();
    const restored = render(<RichMessage message={{ ...message, content: message.content + " חדש" }} active stream={report("דיווח קיים נוסף")}/>);
    expect(restored.container.querySelector(".stream-reveal")).toBeNull();
  });

  test("replay after a snapshot is idempotent and keeps reports separate from the final answer", () => {
    let state = reduceStream(undefined, event(1, [{ kind: "request_start" }, { kind: "text_delta", block_id: "request", text: "בודק" }]));
    state = reduceStream(state, event(2, [{ kind: "text_role", block_id: "request", role: "report" }, { kind: "tool_preparing", block_id: "call", call_id: "call", name: "canvas_manager", arguments_text: "partial" }]));
    expect(streamAnswer(state)).toBe("");
    expect(state.blocks.request.role).toBe("report");
    expect(reduceStream(state, event(1, [{ kind: "text_delta", block_id: "request", text: "duplicate" }]))).toBe(state);
    state = reduceStream(state, event(3, [{ kind: "request_start", request_id: "next" }, { kind: "text_delta", request_id: "next", block_id: "next", text: "סופי" }]));
    expect(streamAnswer(state)).toBe("סופי");
  });

  test("an incomplete response cannot expose copy or speech controls, including after cancellation", () => {
    for (const status of ["running", "cancelled", "failed", "interrupted"]) {
      const html = renderToStaticMarkup(<RichMessage message={{ role: "assistant", content: "partial", metadata: { run_id: "r", run_status: status } }} active={status === "running"} runStatus={status}/>);
      expect(html).not.toContain('aria-label="הקרא בקול"');
      expect(html).not.toContain('aria-label="העתק"');
    }
    const html = renderToStaticMarkup(<RichMessage message={{ role: "assistant", content: "final", metadata: { run_id: "r", run_status: "completed" } }}/>);
    expect(html).toContain('aria-label="הקרא בקול"');
    expect(html).toContain('aria-label="העתק"');
  });

  test("Live reserves user actions through streaming and late transcript completion", () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    const user = { role: "user" as const, content: "תמלול", metadata: { live_session_id: "voice", live_message_id: "utterance", live_partial: true } };
    const answer = { role: "assistant" as const, content: "תשובה", metadata: { live_session_id: "voice", live_message_id: "reply", live_partial: true } };
    const dialogue = (content: string, userPartial: boolean, answerPartial: boolean) => <>
      <RichMessage message={{ ...user, content, metadata: { ...user.metadata, live_partial: userPartial } }} active={userPartial}/>
      <RichMessage message={{ ...answer, metadata: { ...answer.metadata, live_partial: answerPartial } }} active={answerPartial}/>
    </>;
    const view = render(dialogue(user.content, true, true));
    const userFooter = view.container.querySelector(".chat-message-row--user .sds-message-actions");
    expect(userFooter).not.toBeNull();
    expect(userFooter?.querySelector('[aria-hidden="true"]')).not.toBeNull();
    expect(view.queryByRole("button", { name: "העתק" })).toBeNull();
    expect(view.container.querySelector(".chat-message-row--assistant .sds-message-actions")).toBeNull();

    view.rerender(dialogue("תמלול מלא ומאומת", true, false));
    expect(view.container.querySelector(".chat-message-row--user .sds-message-actions")).toBe(userFooter);
    expect(userFooter?.querySelector("button")).toBeNull();

    view.rerender(dialogue("תמלול מלא ומאומת", false, false));
    expect(view.container.querySelector(".chat-message-row--user .sds-message-actions")).toBe(userFooter);
    expect(userFooter?.querySelector('button[aria-label="העתק"]')).not.toBeNull();
    expect(userFooter?.querySelector(".message-actions-placeholder")).toBeNull();

    view.rerender(dialogue("תמלול מלא ומאומת נוסף", true, false));
    expect(view.container.querySelector(".chat-message-row--user .sds-message-actions")).toBe(userFooter);
    expect(userFooter?.querySelector("button")).toBeNull();
  });

  test("empty transcripts and explicitly hidden actions do not reserve a footer", () => {
    for (const content of ["", "  ", "טקסט"]) {
      const html = renderToStaticMarkup(<RichMessage message={{ role: "user", content, metadata: { live_partial: true } }} active hideActions={Boolean(content.trim())}/>);
      expect(html).not.toContain("sds-message-actions");
      expect(html).not.toContain("message-actions-placeholder");
    }
  });

  test("preparation has one existing status line and arguments only in tool details", () => {
    const stream: StreamState = { stage: "tool", blocks: { call: { kind: "tool", call_id: "call", name: "canvas_manager", arguments_text: "very long input" } } };
    const html = renderToStaticMarkup(<RichMessage message={{ role: "assistant", content: "", metadata: { run_id: "prep" } }} active stream={stream}/>);
    expect(html).toContain("מכין כלי canvas_manager");
    expect(html).toContain("tool-preparation-ring");
    expect(html).not.toContain("חושב...");
    expect(html.match(/is-shimmering/g)?.length).toBe(1);
    expect(html).toContain('<pre dir="ltr">very long input</pre>');
  });

  test("local prefill percentage is presented without exposing reasoning text", () => {
    const html = renderToStaticMarkup(<RichMessage message={{ role: "assistant", content: "", metadata: { run_id: "prefill" } }} active stream={{ stage: "prefill", percent: 37, blocks: {} }}/>);
    expect(html).toContain("מעבד הנחיה: 37%");
    expect(html).not.toContain("חושב");
  });

  test("sent attachment rows precede and stay outside the user bubble", () => {
    const html = renderToStaticMarkup(<RichMessage message={{ role: "user", content: "text", attachments: [{ name: "image.png", path: "C:/qa/image.png", kind: "image" }, { name: "file.txt", path: "C:/qa/file.txt" }] }}/>);
    expect(html.indexOf('class="sent-attachments"')).toBeLessThan(html.indexOf('class="sds-user-bubble'));
    expect(html).toContain('aria-label="הגדל תמונה: image.png"');
  });
});
