// Chat state per project: the transcript the UI shows, the agent sessions to resume, and the
// approval / question requests waiting on the user.
import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { AgentKind, AgentState, ApprovalReply, ChatHistory, ChatItem, QuestionReply } from "../../shared/types";
import { bus } from "../proc";
import { projectDir } from "../projects";
import { getSettings } from "../store";

interface ChatState {
  items: ChatItem[];
  state: AgentState;
  abort?: AbortController;
}

const chats = new Map<string, ChatState>();
const saveTimers = new Map<string, NodeJS.Timeout>();

const appDir = (project: string) => path.join(projectDir(project), ".app");

function load(project: string): ChatState {
  let c = chats.get(project);
  if (!c) {
    let items: ChatItem[] = [];
    try {
      items = JSON.parse(readFileSync(path.join(appDir(project), "chat.json"), "utf8"));
    } catch {
      /* new chat */
    }
    // anything left pending from a previous run can't be answered any more
    items = items.map((i) =>
      (i.kind === "approval" || i.kind === "question") && i.status === "pending"
        ? ({ ...i, status: i.kind === "approval" ? "denied" : "answered" } as ChatItem)
        : i.kind === "tool" && i.status === "running"
          ? { ...i, status: "error" }
          : i.kind === "assistant" && i.streaming
            ? { ...i, streaming: false }
            : i,
    );
    c = { items, state: "idle" };
    chats.set(project, c);
  }
  return c;
}

function scheduleSave(project: string): void {
  clearTimeout(saveTimers.get(project));
  saveTimers.set(
    project,
    setTimeout(() => {
      const c = chats.get(project);
      if (!c) return;
      mkdirSync(appDir(project), { recursive: true });
      writeFileSync(path.join(appDir(project), "chat.json"), JSON.stringify(c.items.slice(-500)));
    }, 500),
  );
}

export function history(project: string): ChatHistory {
  const c = load(project);
  return { agent: getSettings().agent, items: c.items, state: c.state };
}

export function upsert(project: string, item: ChatItem): void {
  const c = load(project);
  const i = c.items.findIndex((x) => x.id === item.id);
  if (i >= 0) c.items[i] = item;
  else c.items.push(item);
  bus.emit("chat", { project, item });
  scheduleSave(project);
}

export function find<K extends ChatItem["kind"]>(project: string, id: string, kind: K) {
  return load(project).items.find((x) => x.id === id && x.kind === kind) as Extract<ChatItem, { kind: K }> | undefined;
}

export function lastStreaming(project: string) {
  const items = load(project).items;
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i];
    if (it.kind === "assistant" && it.streaming) return it;
    if (it.kind === "user") return undefined;
  }
  return undefined;
}

export function setState(project: string, state: AgentState, abort?: AbortController): void {
  const c = load(project);
  c.state = state;
  c.abort = state === "running" ? abort : undefined;
  bus.emit("state", { project, state });
}

export function isRunning(project: string): boolean {
  return load(project).state === "running";
}

export function stop(project: string): void {
  const c = load(project);
  c.abort?.abort();
  for (const [id, p] of pending) if (p.project === project) p.resolve(null), pending.delete(id);
}

export function reset(project: string): void {
  stop(project);
  const c = load(project);
  c.items = [];
  writeSessions(project, {});
  scheduleSave(project);
  bus.emit("state", { project, state: c.state });
}

export const newId = () => randomUUID();

// --- agent sessions (resume across app restarts) -------------------------------------------------

type Sessions = Partial<Record<AgentKind, string>>;

export function readSessions(project: string): Sessions {
  const f = path.join(appDir(project), "session.json");
  if (!existsSync(f)) return {};
  try {
    return JSON.parse(readFileSync(f, "utf8"));
  } catch {
    return {};
  }
}

export function writeSessions(project: string, s: Sessions): void {
  mkdirSync(appDir(project), { recursive: true });
  writeFileSync(path.join(appDir(project), "session.json"), JSON.stringify(s));
}

// --- requests waiting on the user -----------------------------------------------------------------

type Reply = ApprovalReply | QuestionReply | null;
const pending = new Map<string, { project: string; resolve: (r: Reply) => void }>();

export function waitForUser(project: string, requestId: string, signal: AbortSignal): Promise<Reply> {
  return new Promise((resolve) => {
    pending.set(requestId, { project, resolve });
    signal.addEventListener("abort", () => {
      pending.delete(requestId);
      resolve(null);
    });
  });
}

export function reply(requestId: string, r: ApprovalReply | QuestionReply): void {
  const p = pending.get(requestId);
  if (!p) return;
  pending.delete(requestId);
  p.resolve(r);
}

// --- what the UI shows for a tool call -------------------------------------------------------------

const short = (s: string, n = 90) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const base = (p: unknown) => (typeof p === "string" ? path.basename(p) : "");

export function describeTool(name: string, input: Record<string, unknown>): { title: string; detail: string } {
  const s = (k: string) => (typeof input[k] === "string" ? (input[k] as string) : "");
  switch (name) {
    case "Bash":
      return { title: short(s("description") || s("command")), detail: s("command") };
    case "Read":
      return { title: `Lendo ${base(input.file_path)}`, detail: s("file_path") };
    case "Write":
      return { title: `Escrevendo ${base(input.file_path)}`, detail: s("file_path") };
    case "Edit":
    case "MultiEdit":
      return { title: `Editando ${base(input.file_path)}`, detail: s("file_path") };
    case "Glob":
    case "Grep":
      return { title: `Procurando ${short(s("pattern"), 60)}`, detail: s("path") || s("pattern") };
    case "Skill":
      return { title: `Receita: ${s("skill") || s("command")}`, detail: s("args") };
    case "WebFetch":
      return { title: `Abrindo ${short(s("url"), 70)}`, detail: s("prompt") };
    case "WebSearch":
      return { title: `Pesquisando "${short(s("query"), 60)}"`, detail: "" };
    case "TodoWrite": {
      const todos = (input.todos as { content: string; status: string }[] | undefined) ?? [];
      const mark = (st: string) => (st === "completed" ? "✓" : st === "in_progress" ? "▸" : "○");
      return { title: "Plano de trabalho", detail: todos.map((t) => `${mark(t.status)} ${t.content}`).join("\n") };
    }
    case "Task":
    case "Agent":
      return { title: `Subtarefa: ${short(s("description"), 70)}`, detail: s("prompt") };
    default:
      if (name.startsWith("mcp__davinci-resolve__")) {
        return { title: `DaVinci Resolve: ${name.slice(22)}${s("action") ? ` · ${s("action")}` : ""}`, detail: JSON.stringify(input, null, 1) };
      }
      return { title: name, detail: short(JSON.stringify(input), 400) };
  }
}

/** Project-relative path when the agent reads an image of this project (to show it in the chat). */
export function projectImage(project: string, file: unknown): string | undefined {
  if (typeof file !== "string" || !/\.(png|jpe?g|webp)$/i.test(file)) return undefined;
  const norm = file.replace(/\\/g, "/");
  const dir = `${projectDir(project).replace(/\\/g, "/")}/`;
  if (norm.startsWith(dir)) return norm.slice(dir.length);
  const marker = `projects/${project}/`; // engine-relative, or through the engine's projects link
  const at = norm.lastIndexOf(marker);
  return at >= 0 && (at === 0 || norm[at - 1] === "/") ? norm.slice(at + marker.length) : undefined;
}
