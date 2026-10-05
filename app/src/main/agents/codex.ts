// Codex through the Codex SDK. Auth is whatever OpenAI's own codex CLI has: a ChatGPT account
// (`codex login`, done in OpenAI's page) or the OpenAI API key the user saved in the app.
import type { ThreadEvent, ThreadItem } from "@openai/codex-sdk";
import type { ChatItem } from "../../shared/types";
import { codexExecutable, engineDir } from "../paths";
import { childEnv } from "../proc";
import { getProject } from "../projects";
import { getSecret, getSettings } from "../store";
import { codexPreamble } from "./context";
import { newId, readSessions, setState, upsert, writeSessions } from "./chat";

const short = (s: string, n = 90) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

function toChat(item: ThreadItem, done: boolean): ChatItem | null {
  const ts = Date.now();
  switch (item.type) {
    case "agent_message":
      return { id: item.id, kind: "assistant", text: item.text, ts, streaming: !done };
    case "reasoning":
      return item.text.trim() ? { id: item.id, kind: "thinking", text: item.text, ts } : null;
    case "command_execution": {
      const status = item.status === "failed" || (item.exit_code ?? 0) !== 0 ? "error" : item.status === "completed" ? "done" : "running";
      const cmd = item.command.replace(/^(\/bin\/)?(ba|z)sh -lc /, "").replace(/^['"]|['"]$/g, "");
      return { id: item.id, kind: "tool", ts, name: "Bash", title: short(cmd), detail: cmd, status, output: item.aggregated_output.slice(-4000) };
    }
    case "file_change":
      return {
        id: item.id,
        kind: "tool",
        ts,
        name: "Edit",
        title: `Alterando ${item.changes.length} arquivo(s)`,
        detail: item.changes.map((c) => `${c.kind} ${c.path}`).join("\n"),
        status: item.status === "failed" ? "error" : "done",
      };
    case "mcp_tool_call":
      return {
        id: item.id,
        kind: "tool",
        ts,
        name: `mcp__${item.server}__${item.tool}`,
        title: `${item.server}: ${item.tool}`,
        detail: JSON.stringify(item.arguments ?? {}, null, 1),
        status: item.status === "failed" ? "error" : item.status === "completed" ? "done" : "running",
      };
    case "web_search":
      return { id: item.id, kind: "tool", ts, name: "WebSearch", title: `Pesquisando "${short(item.query, 60)}"`, detail: "", status: "done" };
    case "todo_list":
      return {
        id: item.id,
        kind: "tool",
        ts,
        name: "TodoWrite",
        title: "Plano de trabalho",
        detail: item.items.map((t) => `${t.completed ? "✓" : "○"} ${t.text}`).join("\n"),
        status: "done",
      };
    case "error":
      return { id: item.id, kind: "error", text: item.message, ts };
  }
  return null;
}

export async function runCodex(project: string, text: string): Promise<void> {
  const settings = getSettings();
  const apiKey = settings.codexAuth === "apikey" ? getSecret("OPENAI_API_KEY") : undefined;
  if (settings.codexAuth === "apikey" && !apiKey) throw new Error("Configure a chave da API OpenAI em Configurações para usar o Codex.");
  const { Codex } = await import("@openai/codex-sdk");
  const abort = new AbortController();
  setState(project, "running", abort);
  const started = Date.now();
  const retryId = newId();
  let fatal: string | undefined;
  const sessions = readSessions(project);
  const codex = new Codex({ codexPathOverride: codexExecutable(), apiKey, env: childEnv() });
  const opts = {
    workingDirectory: engineDir(),
    skipGitRepoCheck: true,
    sandboxMode: settings.codexSandbox,
    networkAccessEnabled: true,
    approvalPolicy: "never" as const,
    model: settings.codexModel || undefined,
    additionalDirectories: [getProject(project).dir],
  };
  const thread = sessions.codex ? codex.resumeThread(sessions.codex, opts) : codex.startThread(opts);
  try {
    const { events } = await thread.runStreamed(sessions.codex ? text : codexPreamble(project) + text, { signal: abort.signal });
    for await (const ev of events as AsyncGenerator<ThreadEvent>) {
      if (ev.type === "thread.started") writeSessions(project, { ...readSessions(project), codex: ev.thread_id });
      else if (ev.type === "item.started" || ev.type === "item.updated" || ev.type === "item.completed") {
        const c = toChat(ev.item, ev.type === "item.completed");
        if (c) upsert(project, c);
      } else if (ev.type === "turn.completed") {
        const u = ev.usage;
        upsert(project, {
          id: newId(),
          kind: "result",
          ts: Date.now(),
          agent: "codex",
          durationMs: Date.now() - started,
          tokens: u.input_tokens + u.output_tokens,
        });
      } else if (ev.type === "turn.failed") {
        upsert(project, { id: newId(), kind: "error", text: ev.error.message, ts: Date.now() });
      } else if (ev.type === "error") {
        if (/\b401\b|invalid_api_key|Unauthorized/i.test(ev.message)) {
          // a rejected credential never recovers: stop instead of reconnecting 5 times
          fatal =
            settings.codexAuth === "apikey"
              ? "A OpenAI recusou a chave da API (401). Confira em Configurações › Inteligência."
              : "A sessão da conta ChatGPT expirou ou foi recusada (401). Entre de novo em Configurações › Inteligência.";
          abort.abort();
        } else if (/^Reconnecting/i.test(ev.message)) {
          upsert(project, { id: retryId, kind: "notice", text: `Conexão instável, tentando de novo… ${ev.message.match(/\d+\/\d+/)?.[0] ?? ""}`, ts: Date.now() });
        } else {
          upsert(project, { id: newId(), kind: "error", text: ev.message, ts: Date.now() });
        }
      }
    }
  } catch (e) {
    if (!abort.signal.aborted) throw e;
    upsert(project, { id: newId(), kind: "error", text: fatal ?? "Interrompido.", ts: Date.now() });
  } finally {
    setState(project, "idle");
  }
}
