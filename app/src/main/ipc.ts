import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import { existsSync } from "node:fs";
import path from "node:path";
import type { ApprovalReply, NewProject, QuestionReply, SecretKey, Settings, SystemStatus } from "../shared/types";
import * as agents from "./agents";
import {
  codexLogin,
  codexLogout,
  codexStatus,
  doctor,
  downloadWhisper,
  ea,
  engineReady,
  installTools,
  linkProjects,
  memoryDir,
  resolveInstalled,
  resolveMcpSetup,
  setupEngine,
} from "./engine";
import { engineDir, isDev, which } from "./paths";
import { bus } from "./proc";
import { createProject, getProject, importMedia, listProjects, projectDir, trashProject, watchProjects } from "./projects";
import { getSettings, secretStatus, setSecret, setSettings } from "./store";
import { validate } from "./validate";

let lastDoctor: SystemStatus["doctor"] = null;

async function status(refreshDoctor = false): Promise<SystemStatus> {
  if (refreshDoctor || !lastDoctor) lastDoctor = await doctor();
  return {
    platform: process.platform,
    arch: process.arch,
    appVersion: app.getVersion(),
    dev: isDev,
    engineDir: engineDir(),
    engineReady: engineReady(),
    tools: { uv: which("uv"), ffmpeg: which("ffmpeg"), node: which("node"), brew: which("brew"), git: which("git") },
    doctor: lastDoctor,
    codex: await codexStatus(),
    resolveInstalled: resolveInstalled(),
  };
}

const MEDIA_FILTER = {
  name: "Mídia",
  extensions: ["mp4", "mov", "m4v", "mkv", "webm", "avi", "mxf", "wav", "mp3", "m4a", "aac", "flac", "aif", "aiff", "png", "jpg", "jpeg", "srt"],
};

export function registerIpc(getWindow: () => BrowserWindow | null): void {
  const h = ipcMain.handle.bind(ipcMain);

  h("settings:get", () => getSettings());
  h("settings:set", (_e, patch: Partial<Settings>) => {
    const before = getSettings().projectsDir;
    const s = setSettings(patch);
    if (s.projectsDir !== before) {
      linkProjects();
      watchProjects();
    }
    return s;
  });

  h("secrets:status", () => secretStatus());
  h("secrets:set", (_e, key: SecretKey, value: string) => (setSecret(key, value), secretStatus()));
  h("secrets:clear", (_e, key: SecretKey) => (setSecret(key, ""), secretStatus()));
  h("secrets:validate", (_e, key: SecretKey) => validate(key));

  h("system:status", (_e, refresh?: boolean) => status(refresh));
  h("system:installTools", () => installTools());
  h("system:setupEngine", async () => {
    const ok = await setupEngine();
    lastDoctor = await doctor();
    return ok;
  });
  h("system:downloadWhisper", () => downloadWhisper());
  h("system:resolveMcpSetup", () => resolveMcpSetup());
  h("system:codexLogin", () => codexLogin());
  h("system:codexLogout", () => codexLogout());
  h("system:openExternal", (_e, url: string) => {
    if (/^https:\/\//.test(url)) return shell.openExternal(url);
  });
  h("system:reveal", (_e, p: string) => shell.showItemInFolder(p));
  h("system:openPath", (_e, p: string) => shell.openPath(p));
  h("system:pickFolder", async () => {
    const win = getWindow();
    const r = await dialog.showOpenDialog(win!, { properties: ["openDirectory", "createDirectory"] });
    return r.canceled ? null : r.filePaths[0];
  });
  h("system:pickMedia", async () => {
    const r = await dialog.showOpenDialog(getWindow()!, { properties: ["openFile", "multiSelections"], filters: [MEDIA_FILTER] });
    return r.canceled ? [] : r.filePaths;
  });
  h("system:memoryDir", () => memoryDir());
  h("system:setupDone", () => ea(["setup-done"]));

  h("projects:list", () => listProjects());
  h("projects:create", (_e, p: NewProject) => createProject(p));
  h("projects:get", (_e, name: string) => getProject(name));
  h("projects:importMedia", (_e, name: string, paths: string[]) => importMedia(name, paths.filter((p) => existsSync(p))));
  h("projects:trash", (_e, name: string) => trashProject(name));
  h("projects:run", (_e, name: string, args: string[]) => {
    projectDir(name); // validates the name
    return ea(args, `run:${name}`);
  });

  h("agent:history", (_e, project: string) => agents.history(project));
  h("agent:send", (_e, project: string, text: string) => agents.send(project, text));
  h("agent:stop", (_e, project: string) => agents.stop(project));
  h("agent:reply", (_e, requestId: string, reply: ApprovalReply | QuestionReply) => agents.reply(requestId, reply));
  h("agent:reset", (_e, project: string) => agents.reset(project));

  for (const ev of ["chat", "state", "log", "projectChanged"]) {
    bus.on(ev, (payload) => getWindow()?.webContents.send(`on:${ev}`, payload));
  }
}

/** ea-media://<project>/<relative path> -> a file inside that project, nothing else. */
export function mediaPath(url: string): string | null {
  const u = new URL(url);
  const project = decodeURIComponent(u.hostname);
  const rel = decodeURIComponent(u.pathname).replace(/^\/+/, "");
  try {
    const dir = projectDir(project);
    const abs = path.resolve(dir, rel);
    return abs.startsWith(dir + path.sep) && existsSync(abs) ? abs : null;
  } catch {
    return null;
  }
}
