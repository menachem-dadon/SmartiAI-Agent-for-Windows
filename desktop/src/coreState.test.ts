import { describe, expect, it } from "vitest";
import { copyForState, type CoreState } from "./coreState";

describe("Core shell state copy", () => {
  it.each<CoreState>(["starting", "connecting", "ready", "crashed", "fatal", "repair", "stopped"])(
    "provides polished Hebrew copy for %s",
    (state) => {
      const value = copyForState(state, null);
      expect(value.title.length).toBeGreaterThan(3);
      expect(value.description.length).toBeGreaterThan(12);
      expect(value.status.length).toBeGreaterThan(2);
    },
  );

  it("adds actionable diagnostics only to non-ready states", () => {
    expect(copyForState("crashed", "exit 1").description).toContain("exit 1");
    expect(copyForState("ready", "ignored").description).not.toContain("ignored");
  });
});
