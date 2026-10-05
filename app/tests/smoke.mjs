// Launches the built app with a throwaway profile and screenshots each screen.
// usage: node tests/smoke.mjs <out-dir> [userDataDir]   (STEPS=<module> adds steps, EXE=<binary> tests a package)
import { _electron as electron } from "playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";

const out = process.argv[2] ?? "test-results";
const userData = process.argv[3] ?? path.join(out, "profile");
mkdirSync(out, { recursive: true });
// EXE=<path to the packaged binary> tests the built .app instead of the sources
const app = process.env.EXE
  ? await electron.launch({ executablePath: process.env.EXE, args: [`--user-data-dir=${userData}`] })
  : await electron.launch({ args: [".", `--user-data-dir=${userData}`], cwd: process.cwd() });
const win = await app.firstWindow();
const errors = [];
win.on("pageerror", (e) => errors.push(String(e)));
win.on("console", (m) => m.type() === "error" && errors.push(m.text()));
await win.setViewportSize({ width: 1440, height: 900 });
await win.waitForSelector("#root > *", { timeout: 20000 });
await win.waitForTimeout(1500);
await win.screenshot({ path: path.join(out, "01-start.png") });
globalThis.app = app;
globalThis.win = win;
const steps = process.env.STEPS ? (await import(path.resolve(process.env.STEPS))).default : null;
if (steps) await steps({ app, win, out });
console.log(JSON.stringify({ errors }, null, 1));
await app.close();
