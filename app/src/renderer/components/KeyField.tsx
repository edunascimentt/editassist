import { useState } from "react";
import type { SecretKey, SecretStatus, Validation } from "../../shared/types";
import { Icon, Spinner, useToast } from "./ui";

export const KEY_INFO: Record<SecretKey, { label: string; url?: string; placeholder: string; secret: boolean }> = {
  ANTHROPIC_API_KEY: {
    label: "Chave da API Anthropic",
    url: "https://console.anthropic.com/settings/keys",
    placeholder: "sk-ant-…",
    secret: true,
  },
  OPENAI_API_KEY: { label: "Chave da API OpenAI", url: "https://platform.openai.com/api-keys", placeholder: "sk-…", secret: true },
  ELEVENLABS_API_KEY: {
    label: "ElevenLabs",
    url: "https://elevenlabs.io/app/settings/api-keys",
    placeholder: "chave da ElevenLabs",
    secret: true,
  },
  ELEVENLABS_VOICE_ID: { label: "Voz padrão (ID)", placeholder: "opcional: ID da voz", secret: false },
  PEXELS_API_KEY: { label: "Pexels", url: "https://www.pexels.com/api/", placeholder: "chave da Pexels", secret: true },
  HF_API_KEY_ID: { label: "Higgsfield: Key ID", url: "https://console.higgsfield.ai", placeholder: "Key ID", secret: true },
  HF_API_KEY_SECRET: { label: "Higgsfield: Key Secret", placeholder: "Key Secret", secret: true },
  HF_TOKEN: {
    label: "Hugging Face (detecção de falantes)",
    url: "https://huggingface.co/settings/tokens",
    placeholder: "hf_…",
    secret: true,
  },
};

export function KeyField({
  k,
  status,
  onChange,
  skipValidate,
}: {
  k: SecretKey;
  status: SecretStatus[];
  onChange: (s: SecretStatus[]) => void;
  skipValidate?: boolean;
}) {
  const info = KEY_INFO[k];
  const st = status.find((s) => s.key === k);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [check, setCheck] = useState<Validation | null>(null);
  const toast = useToast();

  async function save() {
    if (!value.trim()) return;
    setBusy(true);
    try {
      onChange(await window.ea.secrets.set(k, value));
      setValue("");
      if (!skipValidate) setCheck(await window.ea.secrets.validate(k));
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(false);
    }
  }

  async function validate() {
    setBusy(true);
    setCheck(await window.ea.secrets.validate(k));
    setBusy(false);
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <div className="row" style={{ marginBottom: 6 }}>
        <span className="label" style={{ margin: 0 }}>
          {info.label}
        </span>
        {info.url && (
          <a className="hint" onClick={() => window.ea.system.openExternal(info.url!)}>
            obter <Icon name="external" size={11} />
          </a>
        )}
        <span className="spacer" />
        {busy ? (
          <Spinner />
        ) : check ? (
          <span className={`pill ${check.ok ? "ok" : "err"}`} title={check.detail}>
            {check.ok ? "✓ " : "✕ "}
            {check.detail.slice(0, 48)}
          </span>
        ) : st?.set ? (
          <span className="pill">salva {st.hint}</span>
        ) : null}
      </div>
      <div className="row">
        <input
          className="input mono"
          type={info.secret ? "password" : "text"}
          placeholder={st?.set ? `${st.hint} (cole para trocar)` : info.placeholder}
          value={value}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
        />
        <button className="btn" disabled={!value.trim() || busy} onClick={save}>
          Salvar
        </button>
        {st?.set && !skipValidate && (
          <button className="btn ghost icon" title="Testar" disabled={busy} onClick={validate}>
            <Icon name="refresh" size={14} />
          </button>
        )}
        {st?.set && (
          <button
            className="btn ghost icon"
            title="Remover"
            disabled={busy}
            onClick={async () => {
              onChange(await window.ea.secrets.clear(k));
              setCheck(null);
            }}
          >
            <Icon name="trash" size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
