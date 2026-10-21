import { expect, test } from "vitest";
import type { ChatMessage } from "../chatTypes";
import { LiveCaptions } from "./liveCaptions";
const message:ChatMessage={role:"assistant",content:"שלום לך עולם\n\n```py\nprint(42)\n```",metadata:{live_message_id:"one",live_audio_start_ms:0,live_audio_end_ms:3000,live_spoken_length:12,live_partial:false,live_audio_cues:[{text_end:5,audio_end_ms:1000},{text_end:12,audio_end_ms:3000}]}};
test("caption words follow the playback clock, then rich content and copy become available",()=>{
  const captions=new LiveCaptions();captions.update(message);
  expect(captions.present(message).content).toBe("");
  captions.tick(1000);expect(captions.present(message).content).toBe("שלום ");
  expect(captions.present(message).metadata?.live_partial).toBe(true);
  captions.tick(3000);expect(captions.present(message).content).toBe(message.content);
  expect(captions.present(message).metadata?.live_partial).toBe(false);
  const user:ChatMessage={role:"user",content:"שלום"};expect(captions.present(user)).toBe(user);
});
test("mute displays text immediately, interruptions freeze at the heard words and history is intact",()=>{
  const captions=new LiveCaptions();captions.update(message);captions.tick(1000);captions.interrupt(1000);
  captions.tick(3000);captions.update({...message,content:message.content+"extra"});
  expect(captions.present(message).content).toBe("שלום ");
  expect(captions.present(message).metadata?.live_partial).toBe(false);
  const next={...message,metadata:{...message.metadata,live_message_id:"two"}};captions.update(next);captions.tick(0,true);
  expect(captions.present(next).content).toBe(message.content);
  expect(message.content).toContain("print(42)");
});
test("sub-sample clock differences cannot keep final content and actions pending",()=>{
  const captions=new LiveCaptions();
  const final={...message,metadata:{...message.metadata,live_audio_end_ms:3000.041666666667}};
  captions.update(final);captions.tick(3000.041666666666);
  expect(captions.present(final).content).toBe(message.content);
  expect(captions.present(final).metadata?.live_partial).toBe(false);
});

test("rich content between prose does not leak into spoken captions and fallback replaces a frozen row",()=>{
  const captions=new LiveCaptions();
  const rich={...message,content:"שלום\n```py\nprint(42)\n```\nלך עולם",metadata:{...message.metadata,live_spoken_text:"שלום לך עולם"}};
  captions.update(rich);captions.tick(1000);
  expect(captions.present(rich).content).toBe("שלום ");
  expect(captions.present(rich).content).not.toContain("```py");
  captions.interrupt(1000);
  const fallback={...rich,content:"Complete executor answer",metadata:{...rich.metadata,live_delivery:"fallback",live_audio_end_ms:0,live_partial:false}};
  captions.update(fallback);
  expect(captions.present(fallback).content).toBe("Complete executor answer");
  expect(captions.present(fallback).metadata?.live_partial).toBe(false);
});
