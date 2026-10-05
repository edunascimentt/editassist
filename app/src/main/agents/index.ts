import { getSettings } from "../store";
import { history, isRunning, newId, reply, reset, setState, stop, upsert } from "./chat";
import { runClaude } from "./claude";
import { runCodex } from "./codex";

export { history, reply, reset, stop };

export async function send(project: string, text: string): Promise<void> {
  if (isRunning(project)) throw new Error("O editor ainda está trabalhando neste projeto. Espere ou pare antes.");
  upsert(project, { id: newId(), kind: "user", text, ts: Date.now() });
  const agent = getSettings().agent;
  // run in the background: progress arrives through chat events
  (agent === "codex" ? runCodex(project, text) : runClaude(project, text)).catch((e: Error) => {
    upsert(project, { id: newId(), kind: "error", text: e.message || String(e), ts: Date.now() });
    setState(project, "idle");
  });
}
