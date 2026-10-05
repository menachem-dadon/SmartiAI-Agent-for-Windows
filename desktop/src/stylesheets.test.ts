import { readFileSync } from "node:fs";
import { parse } from "postcss";
import { expect, test } from "vitest";

const stylesheet = (file: string) => readFileSync(new URL(file, import.meta.url), "utf8");

test.each(["./App.css", "./chat.css", "./workbench.css", "./design-system/system.css"])(
  "%s has complete CSS blocks before browser error recovery",
  (file) => expect(() => parse(stylesheet(file), { from: file })).not.toThrow(),
);

test("window captions and management navigation are available outside narrow media queries", () => {
  const root = parse(stylesheet("./App.css"));
  for (const selector of [
    ".window-titlebar",
    ".window-titlebar button",
    ".window-caption-icon",
    ".management-layout > nav > section",
    ".management-layout > nav button > span:last-child",
  ]) {
    const globalRules = root.nodes.filter((node) => node.type === "rule" && node.selector === selector);
    expect(globalRules.length, selector).toBeGreaterThan(0);
  }
});
