// The editing engine: the same `ea` CLI, skills and CLAUDE.md the terminal workflow uses.
import { app } from "electron";
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  readlinkSync,
  rmdirSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import type { DoctorCheck, RunResult, SystemStatus } from "../shared/types";
import { bundledEngineDir, codexExecutable, engineDir, isDev, isMac, isWin, which } from "./paths";
import { childEnv, log, parseJson, run } from "./proc";
import { getSecret, getSettings } from "./store";

/** Packaged app: copy the bundled engine to a writable folder (once per app version) and point
 * its projects/ at the user's projects folder, so every `projects/<name>/` path in the skills works. */
export function ensureEngine(): void {
  const dst = engineDir();
  if (!isDev) {
    const marker = path.join(dst, ".app-engine-version");
    const have = existsSync(marker) ? readFileSync(marker, "utf8").trim() : "";
    if (have !== app.getVersion()) {
      mkdirSync(dst, { recursive: true });
      cpSync(bundledEngineDir(), dst, { recursive: true, force: true });
      writeFileSync(marker, app.getVersion());
    }
  }
  linkProjects();
}

export function linkProjects(): void {
  const target = getSettings().projectsDir;
  mkdirSync(target, { recursive: true });
  if (isDev) return; // dev: projects live in the repo already
  const link = path.join(engineDir(), "projects");
  if (existsSync(link) || isBrokenLink(link)) {
    const st = lstatSync(link);
    if (st.isSymbolicLink()) {
      if (path.resolve(readlinkSync(link)) === path.resolve(target)) return;
      unlinkSync(link);
    } else if (st.isDirectory() && readdirSync(link).filter((f) => f !== ".gitkeep").length === 0) {
      for (const f of readdirSync(link)) unlinkSync(path.join(link, f));
      rmdirSync(link);
    } else {
      log("setup", `engine/projects is a real folder with files; left as is (${link})`);
      return;
    }
  }
  symlinkSync(target, link, isWin ? "junction" : "dir");
}

function isBrokenLink(p: string): boolean {
  try {
    return lstatSync(p).isSymbolicLink();
  } catch {
    return false;
  }
}

function uv(): string {
  return which("uv") ?? "uv";
}

/** `uv run ea <args>` in the engine, JSON parsed. */
export async function ea(args: string[], channel?: string, signal?: AbortSignal): Promise<RunResult> {
  const r = await run(uv(), ["run", "--quiet", "ea", ...args], { cwd: engineDir(), channel, signal });
  return { ok: r.code === 0, code: r.code, json: parseJson(r.stdout), stdout: r.stdout, stderr: r.stderr };
}

export function engineReady(): boolean {
  return existsSync(path.join(engineDir(), ".venv"));
}

export async function setupEngine(): Promise<boolean> {
  const ch = "setup";
  const cwd = engineDir();
  if (!which("uv")) {
    log(ch, "uv não encontrado: instale as ferramentas primeiro.", { done: true, ok: false });
    return false;
  }
  log(ch, "Instalando o ambiente Python do motor (uv sync)…");
  let r = await run(uv(), ["sync"], { cwd, channel: ch });
  if (r.code !== 0) {
    log(ch, "uv sync falhou.", { done: true, ok: false });
    return false;
  }
  const npm = which("npm");
  const remotion = path.join(cwd, "remotion");
  if (npm && existsSync(path.join(remotion, "package.json")) && !existsSync(path.join(remotion, "node_modules"))) {
    log(ch, "Instalando os gráficos animados (Remotion)…");
    const lock = existsSync(path.join(remotion, "package-lock.json"));
    r = await run(npm, [lock ? "ci" : "install", "--no-audit", "--no-fund"], { cwd: remotion, channel: ch });
    if (r.code !== 0) log(ch, "Remotion não instalou; gráficos animados ficam desligados (o resto funciona).");
  }
  await ea(["memory", "--init"], ch);
  log(ch, "Motor pronto.", { done: true, ok: true });
  return true;
}

export async function doctor(): Promise<SystemStatus["doctor"]> {
  if (!engineReady()) return null;
  const r = await ea(["doctor", "--json"]);
  const j = r.json as { ready: boolean; checks: DoctorCheck[] } | null;
  return j && Array.isArray(j.checks) ? { ready: j.ready, checks: j.checks } : null;
}

export async function installTools(): Promise<boolean> {
  const ch = "setup";
  const missing = (["uv", "ffmpeg", "node"] as const).filter((t) => !which(t));
  if (!missing.length) {
    log(ch, "Ferramentas já instaladas.", { done: true, ok: true });
    return true;
  }
  if (isMac) {
    const brew = which("brew");
    if (!brew) {
      if (missing.includes("uv")) {
        log(ch, "Instalando uv (instalador oficial da Astral)…");
        await run("/bin/sh", ["-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"], { channel: ch });
      }
      const rest = missing.filter((t) => t !== "uv" && !which(t));
      if (rest.length) {
        log(ch, `Falta ${rest.join(", ")}. Instale o Homebrew (https://brew.sh) e clique de novo, ou instale manualmente.`, {
          done: true,
          ok: false,
        });
        return false;
      }
    } else {
      log(ch, `brew install ${missing.join(" ")}`);
      const r = await run(brew, ["install", ...missing], { channel: ch, env: childEnv({ HOMEBREW_NO_AUTO_UPDATE: "1" }) });
      if (r.code !== 0) {
        log(ch, "O Homebrew não conseguiu instalar tudo (veja o log acima).", { done: true, ok: false });
        return false;
      }
    }
  } else if (isWin) {
    const winget = which("winget");
    if (!winget) {
      log(ch, "winget não encontrado: instale o App Installer da Microsoft Store.", { done: true, ok: false });
      return false;
    }
    const ids: Record<string, string> = { uv: "astral-sh.uv", ffmpeg: "Gyan.FFmpeg", node: "OpenJS.NodeJS.LTS" };
    for (const t of missing) {
      log(ch, `winget install ${ids[t]}`);
      await run(winget, ["install", "--id", ids[t], "-e", "--accept-source-agreements", "--accept-package-agreements"], {
        channel: ch,
      });
    }
  } else {
    log(ch, `Instale ${missing.join(", ")} pelo gerenciador de pacotes do sistema.`, { done: true, ok: false });
    return false;
  }
  const still = missing.filter((t) => !which(t));
  log(ch, still.length ? `Ainda falta: ${still.join(", ")}` : "Ferramentas instaladas.", { done: true, ok: !still.length });
  return !still.length;
}

export async function downloadWhisper(): Promise<boolean> {
  log("setup", "Baixando o modelo de transcrição (~1,6 GB, uma vez só)…");
  const r = await run(
    uv(),
    [
      "run",
      "python",
      "-c",
      "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cpu', compute_type='int8'); print('ok')",
    ],
    { cwd: engineDir(), channel: "setup" },
  );
  log("setup", r.code === 0 ? "Modelo pronto." : "Download falhou.", { done: true, ok: r.code === 0 });
  return r.code === 0;
}

export async function resolveMcpSetup(): Promise<boolean> {
  const r = await ea(["resolve-mcp", "--setup"], "setup");
  log("setup", r.ok ? "Controle do DaVinci Resolve instalado." : "Falhou: veja o log.", { done: true, ok: r.ok });
  return r.ok;
}

export function resolveInstalled(): boolean {
  if (isMac) return existsSync("/Applications/DaVinci Resolve") || existsSync("/Applications/DaVinci Resolve.app");
  if (isWin) return existsSync(path.join(process.env.ProgramFiles ?? "C:\\Program Files", "Blackmagic Design", "DaVinci Resolve"));
  return existsSync("/opt/resolve");
}

export async function memoryDir(): Promise<string | null> {
  if (!engineReady()) return null;
  const r = await ea(["memory"]);
  return (r.json as { dir?: string } | null)?.dir ?? null;
}

// --- Codex account (ChatGPT sign-in handled by OpenAI's own codex CLI) --------------------------

function codexEnv(): Record<string, string> {
  const env = childEnv();
  const key = getSecret("OPENAI_API_KEY");
  if (getSettings().codexAuth === "apikey" && key) env.CODEX_API_KEY = key;
  return env;
}

export async function codexStatus(): Promise<SystemStatus["codex"]> {
  const bin = codexExecutable();
  if (!bin) return { loggedIn: false, detail: "Codex não encontrado no app" };
  const r = await run(bin, ["login", "status"], { env: codexEnv() });
  const text = (r.stdout + r.stderr).trim().split("\n").pop() ?? "";
  if (r.code !== 0) return { loggedIn: false, detail: "não conectado" };
  return { loggedIn: true, detail: /chatgpt/i.test(text) ? "conectado com a conta ChatGPT" : /api key/i.test(text) ? "conectado com chave de API" : text };
}

export async function codexLogin(): Promise<boolean> {
  const bin = codexExecutable();
  if (!bin) return false;
  log("codex", "Abrindo o navegador para entrar com a sua conta ChatGPT…");
  const ac = AbortSignal.timeout(10 * 60 * 1000);
  const r = await run(bin, ["login"], { env: codexEnv(), channel: "codex", signal: ac });
  log("codex", r.code === 0 ? "Conta conectada." : "Login não concluído.", { done: true, ok: r.code === 0 });
  return r.code === 0;
}

export async function codexLogout(): Promise<boolean> {
  const bin = codexExecutable();
  if (!bin) return false;
  const r = await run(bin, ["logout"], { env: codexEnv() });
  return r.code === 0;
}
