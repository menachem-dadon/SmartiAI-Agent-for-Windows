import { describe, expect, test } from "vitest";
import { quotaResetLabel } from "./quotaPresentation";

describe("compact quota reset labels", () => {
  const now = new Date(2026, 9, 15, 12).getTime();
  test("shows the clock time for the five-hour window and weekly resets within 24 hours", () => {
    const later = new Date(2026, 9, 15, 17, 23).getTime() / 1000;
    expect(quotaResetLabel(later, "five_hour", now)).toBe("17:23");
    expect(quotaResetLabel(later, "weekly", now)).toBe("17:23");
    expect(quotaResetLabel(new Date(2026, 9, 16, 9, 7).getTime() / 1000, "weekly", now)).toBe("09:07");
  });
  test("uses a short Hebrew date for later weekly resets, without relative text", () => {
    const reset = new Date(2026, 9, 20, 12).getTime() / 1000;
    expect(quotaResetLabel(reset, "weekly", now)).toMatch(/^20 .*אוק/);
    expect(quotaResetLabel(reset, "weekly", now)).not.toContain("בעוד");
  });
  test("leaves missing or invalid data unknown", () => {
    for (const value of [undefined, 0, NaN, Infinity, 1e20]) expect(quotaResetLabel(value, "weekly", now)).toBe("");
  });
});
