import { expect, test } from "vitest";
import { LiveActivity } from "./liveActivity";

test("quiet real speech animates noticeably while ambient noise stays listening", () => {
  const activity = new LiveActivity();
  expect(activity.sample(.002, 0, 100, false).state).toBe("listening");
  let sample = activity.sample(.018, 0, 120, false);
  for (let now = 140; now < 500; now += 20) sample = activity.sample(.018, 0, now, false);
  expect(sample.state).toBe("userSpeaking");
  expect(sample.level).toBeGreaterThan(.4);
  expect(sample.level).toBeLessThan(1);
});
test("syllable and playback gaps keep speech state, then release to the task state", () => {
  const activity = new LiveActivity();
  expect(activity.sample(.02, 0, 100, false).state).toBe("userSpeaking");
  expect(activity.sample(.005, 0, 230, false).state).toBe("userSpeaking");
  expect(activity.sample(.005, 0, 340, true).state).toBe("thinking");
  expect(activity.sample(0, .06, 400, true).state).toBe("smartySpeaking");
  expect(activity.sample(0, 0, 500, true).state).toBe("smartySpeaking");
  expect(activity.sample(0, 0, 580, false).state).toBe("listening");
});
test("audio envelope changes continuously and task state updates even with a muted microphone", () => {
  const activity = new LiveActivity();
  const first = activity.sample(0, .15, 100, true);
  const second = activity.sample(0, .15, 116, true);
  expect(second.level).toBeGreaterThan(first.level);
  expect(second.level - first.level).toBeLessThan(.25);
  const falling = activity.sample(0, 0, 132, true);
  expect(falling.level).toBeGreaterThan(second.level * .8);
  expect(activity.sample(0, 0, 500, true).state).toBe("thinking");
  expect(activity.sample(0, 0, 520, false).state).toBe("listening");
});
