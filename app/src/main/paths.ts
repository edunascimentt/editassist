import { app } from "electron";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

export const isDev = !app.isPackaged;
export const isMac = process.platform === "darwin";
export const isWin = process.platform === "win32";

/** The editassist repo when running from source (app/dist/main -> repo). */
export const repoRoot = path.resolve(__dirname, "..", "..", "..");

/** Where the engine (ea CLI, skills, CLAUDE.md) runs from: the repo in dev, a writable copy when packaged. */
export function engineDir(): string {
  return isDev ? repoRoot : path.join(app.getPath("userData"), "engine");
}

/** The engine shipped inside the app bundle (read-only), copied to engineDir() on first launch. */
export function bundledEngineDir(): string {
  return path.join(process.resourcesPath, "engine");
}

export function defaultProjectsDir(): string {
  if (isDev) return path.join(repoRoot, "projects");
  return path.join(app.getPath("videos"), "editassist");
}

/** Files inside node_modules that native code must reach live outside app.asar. */
export function unpacked(p: string): string {
  return p.replace(`app.asar${path.sep}`, `app.asar.unpacked${path.sep}`);
}

/** GUI apps on macOS don't get the shell's PATH: add the usual install locations. */
export function toolPath(): string {
  const home = homedir();
  const extra = isWin
    ? [
        path.join(home, ".local", "bin"),
        path.join(home, ".cargo", "bin"),
        path.join(process.env.LOCALAPPDATA ?? "", "Microsoft", "WinGet", "Links"),
        "C:\\Program Files\\nodejs",
        "C:\\Program Files\\Git\\cmd",
      ]
    : [
        path.join(home, ".local", "bin"),
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        path.join(home, ".cargo", "bin"),
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
      ];
  const current = (process.env.PATH ?? "").split(path.delimiter).filter(Boolean);
  return [...new Set([...extra, ...current])].join(path.delimiter);
}

export function which(bin: string): string | null {
  const exts = isWin ? [".exe", ".cmd", ".bat", ""] : [""];
  for (const dir of toolPath().split(path.delimiter)) {
    for (const ext of exts) {
      const p = path.join(dir, bin + ext);
      if (existsSync(p)) return p;
    }
  }
  return null;
}

export function claudeExecutable(): string | undefined {
  const pkg = `@anthropic-ai/claude-agent-sdk-${process.platform}-${process.arch}`;
  try {
    const dir = path.dirname(require.resolve(`${pkg}/package.json`));
    const bin = path.join(unpacked(dir), isWin ? "claude.exe" : "claude");
    return existsSync(bin) ? bin : undefined;
  } catch {
    return undefined; // let the SDK find it
  }
}

export function codexExecutable(): string | undefined {
  const triple: Record<string, string> = {
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-x64": "x86_64-apple-darwin",
    "win32-x64": "x86_64-pc-windows-msvc",
    "win32-arm64": "aarch64-pc-windows-msvc",
    "linux-x64": "x86_64-unknown-linux-musl",
    "linux-arm64": "aarch64-unknown-linux-musl",
  };
  const t = triple[`${process.platform}-${process.arch}`];
  if (!t) return undefined;
  try {
    const dir = path.dirname(require.resolve(`@openai/codex-${process.platform}-${process.arch}/package.json`));
    const bin = path.join(unpacked(dir), "vendor", t, "bin", isWin ? "codex.exe" : "codex");
    return existsSync(bin) ? bin : undefined;
  } catch {
    return undefined;
  }
}
