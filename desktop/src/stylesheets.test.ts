import { readFileSync } from "node:fs";
import { parse } from "postcss";
import { expect, test } from "vitest";

const stylesheet = (file: string) => readFileSync(new URL(file, import.meta.url), "utf8");

test.each(["./App.css", "./management.css", "./chat.css", "./workbench.css", "./design-system/system.css"])(
  "%s has complete CSS blocks before browser error recovery",
  (file) => expect(() => parse(stylesheet(file), { from: file })).not.toThrow(),
);

test("window captions and management navigation are available outside narrow media queries", () => {
  const root = parse(stylesheet("./App.css"));
  for (const selector of [
    ".window-titlebar",
    ".window-titlebar button",
    ".window-caption-icon",
  ]) {
    const globalRules = root.nodes.filter((node) => node.type === "rule" && node.selector === selector);
    expect(globalRules.length, selector).toBeGreaterThan(0);
  }
});

 test("management labels and sections remain available at normal widths", () => {
  const root = parse(stylesheet("./management.css"));
  for (const selector of [".management-layout>nav>section", ".management-layout>nav .sds-button>span"]) {
    expect(root.nodes.some(node => node.type === "rule" && node.selector === selector), selector).toBe(true);
  }
});
