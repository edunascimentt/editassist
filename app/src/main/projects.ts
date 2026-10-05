import { shell } from "electron";
import { constants, existsSync, readdirSync, readFileSync, statSync, watch, type FSWatcher } from "node:fs";
import { copyFile } from "node:fs/promises";
import path from "node:path";
import type {
  MediaItem,
  NewProject,
  OutputFile,
  ProjectDetail,
  ProjectSettings,
  ProjectSummary,
  Timeline,
} from "../shared/types";
import { ea } from "./engine";
import { bus } from "./proc";
import { getSettings } from "./store";

export const projectsDir = () => getSettings().projectsDir;
export const projectDir = (name: string) => {
  const dir = path.join(projectsDir(), name);
  if (path.dirname(dir) !== path.resolve(projectsDir())) throw new Error(`invalid project name: ${name}`);
  return dir;
};

function readJson<T>(file: string): T | null {
  try {
    return JSON.parse(readFileSync(file, "utf8")) as T;
  } catch {
    return null;
  }
}

const VIDEO = new Set([".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mxf"]);
const AUDIO = new Set([".wav", ".mp3", ".m4a", ".aac", ".flac", ".aif", ".aiff", ".ogg"]);
const IMAGE = new Set([".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"]);
const NLE = new Set([".otio", ".xml", ".fcpxml", ".jsx", ".drp", ".prproj", ".aep"]);
const SUBS = new Set([".srt", ".ass", ".vtt"]);

function kindOf(file: string): OutputFile["kind"] {
  const e = path.extname(file).toLowerCase();
  if (VIDEO.has(e)) return "video";
  if (AUDIO.has(e)) return "audio";
  if (IMAGE.has(e)) return "image";
  if (NLE.has(e)) return "nle";
  if (SUBS.has(e)) return "subtitle";
  return "other";
}

function files(dir: string, rel: string): OutputFile[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true })
    .filter((d) => d.isFile() && !d.name.startsWith("."))
    .map((d) => {
      const st = statSync(path.join(dir, d.name));
      return { name: d.name, path: `${rel}/${d.name}`, size: st.size, mtime: st.mtimeMs, kind: kindOf(d.name) };
    })
    .sort((a, b) => b.mtime - a.mtime);
}

export function timelineLength(tl: Timeline | null): number {
  if (!tl) return 0;
  let end = 0;
  for (const t of tl.tracks) for (const c of t.clips) end = Math.max(end, c.start + (c.out - c.in) / ((c.speed as number) || 1));
  return end;
}

function summary(name: string): ProjectSummary | null {
  const dir = projectDir(name);
  const settings = readJson<ProjectSettings>(path.join(dir, "project.json"));
  if (!settings) return null;
  const tl = readJson<Timeline>(path.join(dir, "timeline.json"));
  const inputs = files(path.join(dir, "input"), "input");
  const outputs = files(path.join(dir, "output"), "output");
  const mtimes = [path.join(dir, "project.json"), path.join(dir, "timeline.json")]
    .filter(existsSync)
    .map((f) => statSync(f).mtimeMs)
    .concat(outputs.map((o) => o.mtime), inputs.map((i) => i.mtime));
  const poster = outputs.find((o) => o.kind === "video") ?? inputs.find((i) => i.kind === "video") ?? null;
  return {
    name,
    dir,
    settings,
    inputs: inputs.length,
    hasTimeline: !!tl,
    length: timelineLength(tl),
    updated: Math.max(0, ...mtimes),
    poster: poster?.path ?? null,
  };
}

export function listProjects(): ProjectSummary[] {
  const root = projectsDir();
  if (!existsSync(root)) return [];
  return readdirSync(root, { withFileTypes: true })
    .filter((d) => (d.isDirectory() || d.isSymbolicLink()) && !d.name.startsWith("."))
    .map((d) => summary(d.name))
    .filter((p): p is ProjectSummary => !!p)
    .sort((a, b) => b.updated - a.updated);
}

export function getProject(name: string): ProjectDetail {
  const s = summary(name);
  if (!s) throw new Error(`projeto não encontrado: ${name}`);
  const dir = s.dir;
  const catalog = readJson<Record<string, MediaItem>>(path.join(dir, "work", "media.json")) ?? {};
  return {
    ...s,
    inputFiles: files(path.join(dir, "input"), "input"),
    media: Object.values(catalog).filter((m) => !m.derived),
    timeline: readJson<Timeline>(path.join(dir, "timeline.json")),
    outputs: files(path.join(dir, "output"), "output"),
  };
}

const PRESETS: Record<NewProject["preset"], { width: number; height: number; platform: string }> = {
  youtube: { width: 1920, height: 1080, platform: "youtube" },
  shorts: { width: 1080, height: 1920, platform: "tiktok" },
  square: { width: 1080, height: 1080, platform: "instagram" },
  podcast: { width: 1920, height: 1080, platform: "podcast" },
};

export function slug(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

export async function createProject(p: NewProject): Promise<ProjectSummary> {
  const name = slug(p.name);
  if (!name) throw new Error("Dê um nome ao projeto.");
  if (existsSync(projectDir(name))) throw new Error(`Já existe um projeto "${name}".`);
  const pr = PRESETS[p.preset];
  const args = ["new", name, "--fps", "30", "--width", String(pr.width), "--height", String(pr.height)];
  args.push("--platform", pr.platform, "--language", p.language || "pt");
  const r = await ea(args);
  if (!r.ok) throw new Error(r.stderr.trim().split("\n").pop() || "ea new falhou");
  return summary(name)!;
}

export async function importMedia(name: string, paths: string[]): Promise<ProjectDetail> {
  const input = path.join(projectDir(name), "input");
  const ch = `ingest:${name}`;
  for (const src of paths) {
    let dst = path.join(input, path.basename(src));
    for (let i = 2; existsSync(dst); i++) {
      const e = path.extname(src);
      dst = path.join(input, `${path.basename(src, e)}_${i}${e}`);
    }
    bus.emit("log", { channel: ch, text: `Copiando ${path.basename(src)}…` });
    await copyFile(src, dst, constants.COPYFILE_FICLONE); // APFS clone: instant, no extra space
  }
  bus.emit("log", { channel: ch, text: "Catalogando a mídia (ea ingest)…" });
  const r = await ea(["ingest", name], ch);
  bus.emit("log", { channel: ch, text: r.ok ? "Mídia pronta." : "ingest falhou", done: true, ok: r.ok });
  return getProject(name);
}

export async function trashProject(name: string): Promise<void> {
  await shell.trashItem(projectDir(name));
}

// --- change notifications ------------------------------------------------------------------------

let watcher: FSWatcher | null = null;
const pending = new Map<string, NodeJS.Timeout>();

export function watchProjects(): void {
  watcher?.close();
  const root = projectsDir();
  if (!existsSync(root)) return;
  try {
    watcher = watch(root, { recursive: true }, (_e, file) => {
      if (!file) return;
      const parts = String(file).split(/[\\/]/);
      const name = parts[0];
      if (!name || name.startsWith(".") || parts[1] === ".app") return;
      // ignore churn inside work/ except the catalog
      if (parts[1] === "work" && parts[2] !== "media.json") return;
      clearTimeout(pending.get(name));
      pending.set(
        name,
        setTimeout(() => bus.emit("projectChanged", name), 400),
      );
    });
  } catch {
    /* recursive watch unsupported: the UI refreshes on agent results instead */
  }
}
