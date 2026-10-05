import { app, BrowserWindow, protocol, shell } from "electron";
import { createReadStream, statSync } from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { ensureEngine } from "./engine";
import { mediaPath, registerIpc } from "./ipc";
import { isMac } from "./paths";
import { log } from "./proc";
import { watchProjects } from "./projects";

protocol.registerSchemesAsPrivileged([
  { scheme: "ea-media", privileges: { standard: true, secure: true, stream: true, supportFetchAPI: true } },
]);

let win: BrowserWindow | null = null;

const MIME: Record<string, string> = {
  ".mp4": "video/mp4",
  ".m4v": "video/mp4",
  ".mov": "video/quicktime",
  ".webm": "video/webm",
  ".mkv": "video/x-matroska",
  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
  ".m4a": "audio/mp4",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
};

/** Serves project files with HTTP range support, so the video player can seek. */
function serveMedia(req: Request): Response {
  const file = mediaPath(req.url);
  if (!file) return new Response("not found", { status: 404 });
  const size = statSync(file).size;
  const type = MIME[path.extname(file).toLowerCase()] ?? "application/octet-stream";
  const range = /bytes=(\d*)-(\d*)/.exec(req.headers.get("range") ?? "");
  if (range && size > 0) {
    const start = range[1] ? Number(range[1]) : Math.max(0, size - Number(range[2]));
    const end = range[1] && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
    if (start >= size || start > end) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
    const body = Readable.toWeb(createReadStream(file, { start, end })) as ReadableStream;
    return new Response(body, {
      status: 206,
      headers: {
        "Content-Type": type,
        "Content-Length": String(end - start + 1),
        "Content-Range": `bytes ${start}-${end}/${size}`,
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
      },
    });
  }
  const body = Readable.toWeb(createReadStream(file)) as ReadableStream;
  return new Response(body, {
    headers: { "Content-Type": type, "Content-Length": String(size), "Accept-Ranges": "bytes", "Cache-Control": "no-cache" },
  });
}

function createWindow(): void {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1080,
    minHeight: 680,
    title: "editassist",
    backgroundColor: "#0e0f12",
    titleBarStyle: isMac ? "hiddenInset" : "default",
    trafficLightPosition: { x: 16, y: 16 },
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "index.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  win.once("ready-to-show", () => win?.show());
  // links open in the browser; the app window never navigates away
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https:\/\//.test(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith(process.env.EA_DEV_URL ?? "file://")) e.preventDefault();
  });
  if (process.env.EA_DEV_URL) void win.loadURL(process.env.EA_DEV_URL);
  else void win.loadFile(path.join(__dirname, "..", "renderer", "index.html"));
  win.on("closed", () => (win = null));
}

app.whenReady().then(() => {
  protocol.handle("ea-media", serveMedia);
  try {
    ensureEngine();
  } catch (e) {
    log("setup", `engine: ${(e as Error).message}`);
  }
  registerIpc(() => win);
  watchProjects();
  createWindow();
  app.on("activate", () => {
    if (!BrowserWindow.getAllWindows().length) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (!isMac) app.quit();
});
