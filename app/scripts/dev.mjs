// Dev loop: Vite serves the renderer with hot reload, the main process is rebuilt once and
// Electron loads the dev server (EA_DEV_URL). Restart this script after editing src/main.
import { spawn } from "node:child_process";
import { createServer } from "vite";

const server = await createServer({ configFile: "vite.config.ts" });
await server.listen();
const url = server.resolvedUrls.local[0];
await new Promise((ok, fail) =>
  spawn(process.execPath, ["scripts/build-main.mjs"], { stdio: "inherit" }).on("exit", (c) => (c ? fail(c) : ok())),
);
const electron = (await import("electron")).default;
const app = spawn(electron, ["."], { stdio: "inherit", env: { ...process.env, EA_DEV_URL: url } });
app.on("exit", async (code) => {
  await server.close();
  process.exit(code ?? 0);
});
