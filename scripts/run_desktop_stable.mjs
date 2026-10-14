import { spawn } from "node:child_process";
import { cp, mkdtemp, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const desktop = path.join(repository, "desktop");

async function buildInterface() {
  const npm = process.env.npm_execpath || path.join(path.dirname(process.execPath), "node_modules/npm/bin/npm-cli.js");
  await stat(npm);
  await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [npm, "run", "build"], { cwd: desktop, stdio: "inherit", windowsHide: true });
    child.once("error", reject);
    child.once("exit", (code, signal) => code === 0 ? resolve() : reject(new Error(`Interface build failed (${code ?? signal})`)));
  });
}

// A running window owns immutable Web files, with no development WebSocket.
// Rebuilding dist elsewhere cannot invalidate this window's module URLs.
export async function startStableInterface({ port = 1420, host = "localhost", build = true } = {}) {
  if (build) await buildInterface();
  const temporaryRoot = path.resolve(tmpdir());
  const snapshot = await mkdtemp(path.join(temporaryRoot, "smarti-desktop-web-"));
  let server;
  const cleanup = async () => {
    // This directory was created by this invocation, directly under the OS
    // temporary directory. Never remove source, dist or another app's files.
    if (path.dirname(path.resolve(snapshot)) !== temporaryRoot || !path.basename(snapshot).startsWith("smarti-desktop-web-")) throw new Error("Invalid owned Web snapshot path");
    await rm(snapshot, { recursive: true, force: true });
  };
  try {
    await cp(path.join(desktop, "dist"), path.join(snapshot, "web"), { recursive: true });
    const { preview } = await import(pathToFileURL(path.join(desktop, "node_modules/vite/dist/node/index.js")).href);
    server = await preview({ configFile: false, root: snapshot, build: { outDir: "web" }, preview: { port, host, strictPort: true } });
  } catch (error) { await cleanup(); throw error; }
  return {
    url: `http://${host}:${port}/`,
    close: async () => { await new Promise((resolve, reject) => server.httpServer.close(error => error ? reject(error) : resolve())); await cleanup(); },
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const serving = await startStableInterface();
  console.log(`Smarti built interface ready at ${serving.url}`);
  let stopping = false;
  const stop = async () => { if (stopping) return; stopping = true; await serving.close(); process.exit(0); };
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
}
