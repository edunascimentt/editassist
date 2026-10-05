import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import type { LogLine } from "../shared/types";
import { serviceEnv } from "./store";
import { toolPath } from "./paths";

/** Main-process event bus; ipc.ts forwards it to the window. */
export const bus = new EventEmitter();
bus.setMaxListeners(50);

export function log(channel: string, text: string, extra: Partial<LogLine> = {}): void {
  bus.emit("log", { channel, text, ...extra } satisfies LogLine);
}

/** Environment for every child process: full PATH plus the user's service keys. */
export function childEnv(extra: Record<string, string> = {}): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) if (v !== undefined) env[k] = v;
  // keys come from the app's keychain store, not from whatever the parent shell had
  delete env.ANTHROPIC_API_KEY;
  delete env.OPENAI_API_KEY;
  delete env.CODEX_API_KEY;
  delete env.ELECTRON_RUN_AS_NODE;
  return { ...env, PATH: toolPath(), PYTHONIOENCODING: "utf-8", ...serviceEnv(), ...extra };
}

export interface Done {
  code: number | null;
  stdout: string;
  stderr: string;
}

export function run(
  cmd: string,
  args: string[],
  opts: { cwd?: string; env?: Record<string, string>; channel?: string; input?: string; signal?: AbortSignal } = {},
): Promise<Done> {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd: opts.cwd,
      env: opts.env ?? childEnv(),
      signal: opts.signal,
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    const stream = (chunk: Buffer, isErr: boolean) => {
      const s = chunk.toString("utf8");
      if (isErr) stderr += s;
      else stdout += s;
      if (opts.channel) for (const line of s.split(/\r?\n|\r/)) if (line.trim()) log(opts.channel, line);
    };
    child.stdout.on("data", (c) => stream(c, false));
    child.stderr.on("data", (c) => stream(c, true));
    child.on("error", (e) => {
      stderr += String(e);
      resolve({ code: -1, stdout, stderr });
    });
    child.on("close", (code) => resolve({ code, stdout, stderr }));
    if (opts.input !== undefined) child.stdin.end(opts.input);
    else child.stdin.end();
  });
}

/** Last JSON value printed by a command (ea prints one JSON document). */
export function parseJson(stdout: string): unknown {
  const t = stdout.trim();
  if (!t) return null;
  try {
    return JSON.parse(t);
  } catch {
    const i = Math.min(...["{", "["].map((c) => t.indexOf(c)).filter((i) => i >= 0));
    if (Number.isFinite(i)) {
      try {
        return JSON.parse(t.slice(i));
      } catch {
        /* not json */
      }
    }
    return null;
  }
}
