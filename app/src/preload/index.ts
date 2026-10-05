import { contextBridge, ipcRenderer, webUtils } from "electron";
import type { EaApi } from "../shared/types";

const invoke = (ch: string, ...args: unknown[]) => ipcRenderer.invoke(ch, ...args);

function subscribe<T>(channel: string, cb: (v: T) => void): () => void {
  const fn = (_e: Electron.IpcRendererEvent, v: T) => cb(v);
  ipcRenderer.on(channel, fn);
  return () => ipcRenderer.removeListener(channel, fn);
}

const api: EaApi = {
  settings: {
    get: () => invoke("settings:get"),
    set: (patch) => invoke("settings:set", patch),
  },
  secrets: {
    status: () => invoke("secrets:status"),
    set: (key, value) => invoke("secrets:set", key, value),
    clear: (key) => invoke("secrets:clear", key),
    validate: (key) => invoke("secrets:validate", key),
  },
  system: {
    status: (refresh) => invoke("system:status", refresh),
    installTools: () => invoke("system:installTools"),
    setupEngine: () => invoke("system:setupEngine"),
    downloadWhisper: () => invoke("system:downloadWhisper"),
    resolveMcpSetup: () => invoke("system:resolveMcpSetup"),
    codexLogin: () => invoke("system:codexLogin"),
    codexLogout: () => invoke("system:codexLogout"),
    openExternal: (url) => invoke("system:openExternal", url),
    reveal: (p) => invoke("system:reveal", p),
    openPath: (p) => invoke("system:openPath", p),
    pickFolder: () => invoke("system:pickFolder"),
    pickMedia: () => invoke("system:pickMedia"),
    memoryDir: () => invoke("system:memoryDir"),
    setupDone: () => invoke("system:setupDone"),
  },
  projects: {
    list: () => invoke("projects:list"),
    create: (p) => invoke("projects:create", p),
    get: (name) => invoke("projects:get", name),
    importMedia: (name, paths) => invoke("projects:importMedia", name, paths),
    trash: (name) => invoke("projects:trash", name),
    run: (name, args) => invoke("projects:run", name, args),
    mediaUrl: (name, rel) => `ea-media://${encodeURIComponent(name)}/${rel.split("/").map(encodeURIComponent).join("/")}`,
  },
  agent: {
    history: (project) => invoke("agent:history", project),
    send: (project, text) => invoke("agent:send", project, text),
    stop: (project) => invoke("agent:stop", project),
    reply: (requestId, reply) => invoke("agent:reply", requestId, reply),
    reset: (project) => invoke("agent:reset", project),
  },
  on: {
    chat: (cb) => subscribe("on:chat", cb),
    state: (cb) => subscribe("on:state", cb),
    log: (cb) => subscribe("on:log", cb),
    projectChanged: (cb) => subscribe("on:projectChanged", cb),
  },
  pathForFile: (file) => webUtils.getPathForFile(file),
};

contextBridge.exposeInMainWorld("ea", api);
