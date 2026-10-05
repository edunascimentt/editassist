// Free validation calls for every key (same endpoints as `ea keys --check`), so keys can be checked
// during onboarding before the engine is installed. Values never leave the main process.
import { randomUUID } from "node:crypto";
import type { SecretKey, Validation } from "../shared/types";
import { getSecret } from "./store";

async function get(url: string, headers: Record<string, string>): Promise<Response> {
  return fetch(url, { headers, signal: AbortSignal.timeout(20_000) });
}

const fail = (r: Response, body = "") => ({ ok: false, detail: `HTTP ${r.status}${body ? `: ${body.slice(0, 140)}` : ""}` });

export async function validate(key: SecretKey): Promise<Validation> {
  const v = getSecret(key);
  if (!v) return { ok: false, detail: "não configurada" };
  try {
    switch (key) {
      case "ANTHROPIC_API_KEY": {
        const r = await get("https://api.anthropic.com/v1/models?limit=1", { "x-api-key": v, "anthropic-version": "2023-06-01" });
        if (r.ok) return { ok: true, detail: "chave aceita" };
        return r.status === 401 ? { ok: false, detail: "chave inválida ou revogada (401)" } : fail(r, await r.text());
      }
      case "OPENAI_API_KEY": {
        const r = await get("https://api.openai.com/v1/models", { Authorization: `Bearer ${v}` });
        if (r.ok) return { ok: true, detail: "chave aceita" };
        return r.status === 401 ? { ok: false, detail: "chave inválida ou revogada (401)" } : fail(r, await r.text());
      }
      case "ELEVENLABS_API_KEY": {
        const r = await get("https://api.elevenlabs.io/v1/user/subscription", { "xi-api-key": v });
        if (r.ok) {
          const d = (await r.json()) as { tier?: string; character_limit?: number; character_count?: number };
          const left = (d.character_limit ?? 0) - (d.character_count ?? 0);
          return { ok: true, detail: `plano ${d.tier ?? "?"}, ~${left.toLocaleString("pt-BR")} créditos neste período` };
        }
        const r2 = await get("https://api.elevenlabs.io/v1/voices", { "xi-api-key": v });
        if (r2.ok) return { ok: true, detail: "válida (chave restrita: vozes OK)" };
        return fail(r);
      }
      case "ELEVENLABS_VOICE_ID": {
        const k = getSecret("ELEVENLABS_API_KEY");
        if (!k) return { ok: false, detail: "precisa da chave ElevenLabs para conferir" };
        const r = await get(`https://api.elevenlabs.io/v1/voices/${encodeURIComponent(v)}`, { "xi-api-key": k });
        return r.ok ? { ok: true, detail: `voz "${((await r.json()) as { name?: string }).name ?? v}"` } : fail(r);
      }
      case "HF_API_KEY_ID":
      case "HF_API_KEY_SECRET": {
        const id = getSecret("HF_API_KEY_ID");
        const secret = getSecret("HF_API_KEY_SECRET");
        if (!id || !secret) return { ok: false, detail: "precisa do ID e do Secret" };
        // a request id that can't exist: 404 = credentials accepted, 401 = rejected. Free.
        const r = await get(`https://api.higgsfield.ai/requests/${randomUUID()}/status`, { Authorization: `Key ${id}:${secret}` });
        return r.status === 404 ? { ok: true, detail: "credenciais aceitas" } : fail(r, await r.text());
      }
      case "PEXELS_API_KEY": {
        const r = await get("https://api.pexels.com/videos/search?query=city&per_page=1", { Authorization: v });
        return r.ok ? { ok: true, detail: "busca OK" } : fail(r);
      }
      case "HF_TOKEN": {
        const r = await get("https://huggingface.co/api/whoami-v2", { Authorization: `Bearer ${v}` });
        return r.ok ? { ok: true, detail: `usuário ${((await r.json()) as { name?: string }).name}` } : fail(r);
      }
    }
  } catch (e) {
    return { ok: false, detail: `sem conexão (${(e as Error).name})` };
  }
}
