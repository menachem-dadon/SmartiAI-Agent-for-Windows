import { describe, expect, it } from "vitest";
import { canvasSecurityPolicy, securedCanvasDocument } from "./CanvasPanel";

describe("sandboxed Canvas document", () => {
  it("injects restrictive policy and a scoped bridge into hostile HTML", () => {
    const value = securedCanvasDocument("<html><head></head><body><script>window.top.location='file:///C:/secret'</script></body></html>", "canvas-1", false);
    expect(value).toContain("default-src 'none'");
    expect(value).toContain("connect-src 'none'");
    expect(value).toContain("frame-src 'none'");
    expect(value).not.toContain("img-src data: blob: https:");
    expect(value).toContain('canvasId="canvas-1"');
    expect(canvasSecurityPolicy.sandbox).toBe("allow-scripts");
  });

  it("allows HTTPS images only after explicit opt-in", () => {
    expect(securedCanvasDocument("<main />", "canvas-2", true)).toContain("img-src data: blob: https:");
  });
});
