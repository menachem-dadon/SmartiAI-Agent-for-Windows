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
