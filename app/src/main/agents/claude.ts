// Claude through the Agent SDK, authenticated ONLY with the user's Anthropic API key: the SDK runs
// with its own config dir, so a claude.ai login on this machine is never picked up (Anthropic's
// terms don't allow third-party apps to offer claude.ai sign-in).
import { app } from "electron";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { ApprovalReply, QuestionReply, Question } from "../../shared/types";
import { engineDir, claudeExecutable, which } from "../paths";
import { childEnv, log } from "../proc";
import { getSecret, getSettings } from "../store";
import { appContext } from "./context";
import {
  describeTool,
  find,
  lastStreaming,
  newId,
  projectImage,
  readSessions,
  setState,
  upsert,
  waitForUser,
  writeSessions,
} from "./chat";

type Block = { type: string; [k: string]: unknown };

const configDir = () => path.join(app.getPath("userData"), "claude");

/** The engine is the app's own code: mark it trusted in the app's private Claude config, so the
 * permission allowlist in .claude/settings.json (uv run ea, ffmpeg…) applies without prompts. */
function trustEngine(): void {
  const file = path.join(configDir(), ".claude.json");
  let cfg: { projects?: Record<string, { hasTrustDialogAccepted?: boolean }> } = {};
  try {
    if (existsSync(file)) cfg = JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return; // being written by a running session: next run will do it
  }
  const dir = engineDir();
  if (cfg.projects?.[dir]?.hasTrustDialogAccepted) return;
  cfg.projects = { ...cfg.projects, [dir]: { ...cfg.projects?.[dir], hasTrustDialogAccepted: true } };
  mkdirSync(configDir(), { recursive: true });
  writeFileSync(file, JSON.stringify(cfg, null, 2), { mode: 0o600 });
}

export async function runClaude(project: string, text: string): Promise<void> {
  const key = getSecret("ANTHROPIC_API_KEY");
  if (!key) throw new Error("Configure a chave da API Anthropic em Configurações para usar o Claude.");
  const settings = getSettings();
  const { query } = await import("@anthropic-ai/claude-agent-sdk");
  trustEngine();
  const abort = new AbortController();
  setState(project, "running", abort);
  const sessions = readSessions(project);
  const started = Date.now();
  let fatal: string | undefined;
  const retryId = newId();

  const q = query({
    prompt: text,
    options: {
      cwd: engineDir(),
      settingSources: ["project"],
      systemPrompt: { type: "preset", preset: "claude_code", append: appContext(project) },
      model: settings.claudeModel || undefined,
      resume: sessions.claude,
      includePartialMessages: true,
      abortController: abort,
      permissionMode: settings.autoApprove ? "acceptEdits" : "default",
      allowedTools: settings.autoApprove ? ["Bash", "WebFetch", "WebSearch"] : undefined,
      pathToClaudeCodeExecutable: claudeExecutable(),
      env: childEnv({
        ANTHROPIC_API_KEY: key,
        CLAUDE_CONFIG_DIR: configDir(),
      }),
      mcpServers: settings.resolveMcp
        ? { "davinci-resolve": { type: "stdio", command: which("uv") ?? "uv", args: ["run", "--quiet", "ea", "resolve-mcp"] } }
        : undefined,
      stderr: (d: string) => log("agent", d.trimEnd()),
      canUseTool: async (toolName, input, { signal, suggestions }) => {
        const requestId = newId();
        if (toolName === "AskUserQuestion") {
          const questions = (input.questions as Question[]) ?? [];
          const id = newId();
          upsert(project, { id, kind: "question", ts: Date.now(), requestId, questions, status: "pending" });
          const r = (await waitForUser(project, requestId, signal)) as QuestionReply | null;
          if (!r) return { behavior: "deny", message: "The user dismissed the question." };
          upsert(project, { id, kind: "question", ts: Date.now(), requestId, questions, status: "answered", answers: r.answers });
          return { behavior: "allow", updatedInput: { questions: input.questions, answers: r.answers } };
        }
        const { title, detail } = describeTool(toolName, input);
        const id = newId();
        const base = { id, kind: "approval" as const, ts: Date.now(), requestId, tool: toolName, title, detail };
        upsert(project, { ...base, canRemember: !!suggestions?.length, status: "pending" });
        const r = (await waitForUser(project, requestId, signal)) as ApprovalReply | null;
        const decision = r?.decision ?? "deny";
        upsert(project, { ...base, canRemember: !!suggestions?.length, status: decision === "deny" ? "denied" : decision === "always" ? "always" : "allowed" });
        if (decision === "deny") return { behavior: "deny", message: r?.message || "The user declined this action." };
        return { behavior: "allow", updatedInput: input, updatedPermissions: decision === "always" ? suggestions : undefined };
      },
    },
  });

  try {
    for await (const msg of q) {
      switch (msg.type) {
        case "system":
          if (msg.subtype === "init") {
            // refuse to run on anything but the API key the user gave the app
            if (msg.apiKeySource !== "ANTHROPIC_API_KEY") {
              fatal = `Credencial inesperada (${msg.apiKeySource}); o app só usa a chave da API.`;
              abort.abort();
              break;
            }
            writeSessions(project, { ...readSessions(project), claude: msg.session_id });
          } else if (msg.subtype === "api_retry") {
            const r = msg as unknown as { attempt: number; max_retries: number; error_status?: number; error?: string };
            if (r.error_status === 401 || r.error_status === 403) {
              // a bad key never recovers: stop now instead of ~10 backoff retries
              fatal = `A Anthropic recusou a chave da API (${r.error_status}). Confira em Configurações › Inteligência.`;
              abort.abort();
            } else {
              upsert(project, {
                id: retryId,
                kind: "notice",
                ts: Date.now(),
                text: `A API respondeu ${r.error_status ?? r.error ?? "erro"}; tentando de novo (${r.attempt}/${r.max_retries})…`,
              });
            }
          }
          break;
        case "stream_event": {
          if (msg.parent_tool_use_id) break; // subagent chatter stays inside its tool row
          const ev = msg.event as { type: string; content_block?: Block; delta?: { type: string; text?: string } };
          if (ev.type === "content_block_start" && ev.content_block?.type === "text") {
            upsert(project, { id: newId(), kind: "assistant", text: "", ts: Date.now(), streaming: true });
          } else if (ev.type === "content_block_delta" && ev.delta?.type === "text_delta") {
            const cur = lastStreaming(project);
            if (cur) upsert(project, { ...cur, text: cur.text + (ev.delta.text ?? "") });
          }
          break;
        }
        case "assistant": {
          if (msg.parent_tool_use_id) break;
          for (const b of msg.message.content as unknown as Block[]) {
            if (b.type === "text") {
              const cur = lastStreaming(project);
              const t = String(b.text ?? "");
              if (cur) upsert(project, { ...cur, text: t, streaming: false });
              else if (t.trim()) upsert(project, { id: newId(), kind: "assistant", text: t, ts: Date.now() });
            } else if (b.type === "tool_use") {
              const input = (b.input ?? {}) as Record<string, unknown>;
              const name = String(b.name);
              if (name === "AskUserQuestion") continue; // shown as a question card
              const { title, detail } = describeTool(name, input);
              upsert(project, {
                id: String(b.id),
                kind: "tool",
                ts: Date.now(),
                name,
                title,
                detail,
                status: "running",
                media: name === "Read" ? projectImage(project, input.file_path) : undefined,
              });
            }
          }
          break;
        }
        case "user": {
          if (msg.parent_tool_use_id) break;
          const content = msg.message.content;
          if (!Array.isArray(content)) break;
          for (const b of content as unknown as Block[]) {
            if (b.type !== "tool_result") continue;
            const tool = find(project, String(b.tool_use_id), "tool");
            if (!tool) continue;
            const out = Array.isArray(b.content)
              ? (b.content as Block[]).filter((c) => c.type === "text").map((c) => String(c.text)).join("\n")
              : String(b.content ?? "");
            upsert(project, { ...tool, status: b.is_error ? "error" : "done", output: out.slice(-4000) });
          }
          break;
        }
        case "result": {
          const r = msg as unknown as {
            is_error?: boolean;
            total_cost_usd?: number;
            duration_ms?: number;
            usage?: { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number };
            result?: string;
            subtype: string;
          };
          const tokens = (r.usage?.input_tokens ?? 0) + (r.usage?.output_tokens ?? 0) + (r.usage?.cache_read_input_tokens ?? 0);
          upsert(project, {
            id: newId(),
            kind: "result",
            ts: Date.now(),
            agent: "claude",
            costUsd: r.total_cost_usd,
            durationMs: r.duration_ms ?? Date.now() - started,
            tokens,
            isError: r.is_error,
            text: r.is_error ? (r.result ?? r.subtype) : undefined,
          });
          break;
        }
      }
    }
    if (fatal) upsert(project, { id: newId(), kind: "error", text: fatal, ts: Date.now() });
  } catch (e) {
    if (!abort.signal.aborted) throw e;
    upsert(project, { id: newId(), kind: "error", text: fatal ?? "Interrompido.", ts: Date.now() });
  } finally {
    const cur = lastStreaming(project);
    if (cur) upsert(project, { ...cur, streaming: false });
    setState(project, "idle");
  }
}
