// Render picture frames as JPEG stills in one bundle (the agent's eyes).
// node scripts/stills.mjs --comp Film --out work/stills/run1 [--every 6] [--frames 0,30,61] [--range 0-300] [--scale 0.5] [--props '{"width":1080,"height":1920}']
import path from "node:path";
import fs from "node:fs";
import { bundle } from "@remotion/bundler";
import { openBrowser, renderFrames, renderStill, selectComposition } from "@remotion/renderer";

const arg = (k, d) => {
  const i = process.argv.indexOf(`--${k}`);
  return i > -1 ? process.argv[i + 1] : d;
};
const comp = arg("comp", "Film");
const out = path.resolve(arg("out", "stills"));
const every = Number(arg("every", "0"));
const list = arg("frames", "");
const range = arg("range", "");
const scale = Number(arg("scale", "0.5"));
const inputProps = JSON.parse(arg("props", "{}"));
fs.mkdirSync(out, { recursive: true });

const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts"), publicDir: path.resolve("public") });
const composition = await selectComposition({ serveUrl, id: comp, inputProps });
const last = composition.durationInFrames - 1;
const written = [];

if (list) {
  const browser = await openBrowser("chrome");
  for (const f of list.split(",").map(Number).filter((n) => n >= 0 && n <= last)) {
    const file = path.join(out, `f${String(f).padStart(5, "0")}.jpeg`);
    await renderStill({ composition, serveUrl, frame: f, output: file, imageFormat: "jpeg", jpegQuality: 80, scale, inputProps, puppeteerInstance: browser });
    written.push({ frame: f, file });
  }
  await browser.close({ silent: true });
} else {
  const [a, b] = range ? range.split("-").map(Number) : [0, last];
  const n = Math.max(1, every || 1);
  const frames = [];
  for (let f = a; f <= Math.min(b, last); f += n) frames.push(f);
  const browser = await openBrowser("chrome");
  for (const f of frames) {
    const file = path.join(out, `f${String(f).padStart(5, "0")}.jpeg`);
    await renderStill({ composition, serveUrl, frame: f, output: file, imageFormat: "jpeg", jpegQuality: 80, scale, inputProps, puppeteerInstance: browser });
    written.push({ frame: f, file });
  }
  await browser.close({ silent: true });
}
void renderFrames; // (kept for large ranges if renderStill per frame gets slow)
fs.writeFileSync(path.join(out, "index.json"), JSON.stringify({ comp, fps: composition.fps, durationInFrames: composition.durationInFrames,
  width: composition.width, height: composition.height, frames: written.map((w) => ({ frame: w.frame, file: path.basename(w.file) })) }, null, 1));
console.log(JSON.stringify({ out, count: written.length }));
