/// <reference types="vite/client" />

declare module "node:fs" {
  export function readFileSync(path: URL | string, encoding: "utf8"): string;
}
/// <reference types="vitest" />
