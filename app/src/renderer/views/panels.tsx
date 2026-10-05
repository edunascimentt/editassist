// Setup panels shared by the first-run wizard and the Settings screen.
import { useEffect, useState } from "react";
import type { SecretStatus, Settings, SystemStatus } from "../../shared/types";
import { KeyField } from "../components/KeyField";
import { Icon, LogView, Segmented, Spinner, Switch, useLog, useToast } from "../components/ui";

export interface PanelProps {
  sys: SystemStatus | null;
  refresh: (doctor?: boolean) => Promise<void>;
  settings: Settings;
  setSettings: (p: Partial<Settings>) => Promise<void>;
  secrets: SecretStatus[];
  setSecrets: (s: SecretStatus[]) => void;
}

const has = (secrets: SecretStatus[], k: string) => secrets.some((s) => s.key === k && s.set);

export function aiReady(p: Pick<PanelProps, "sys" | "settings" | "secrets">): boolean {
  if (p.settings.agent === "claude") return has(p.secrets, "ANTHROPIC_API_KEY");
  return p.settings.codexAuth === "apikey" ? has(p.secrets, "OPENAI_API_KEY") : !!p.sys?.codex.loggedIn;
}

function Check({ ok, label, detail, optional }: { ok: boolean; label: string; detail?: string; optional?: boolean }) {
  return (
    <div className="check-row">
      <span className={ok ? "ok" : optional ? "faint" : "warn"}>
        <Icon name={ok ? "check2" : "x"} size={16} />
      </span>
      <span style={{ fontWeight: 550, minWidth: 130 }}>{label}</span>
      <span className="hint grow" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={detail}>
        {detail}
      </span>
    </div>
  );
}

// --- tools + engine --------------------------------------------------------------------------------

export function ToolsPanel({ sys, refresh }: PanelProps) {
  const log = useLog("setup");
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();
  if (!sys)
    return (
      <div className="row">
        <Spinner /> verificando…
      </div>
    );
  const t = sys.tools;
  const missingTools = !t.uv || !t.ffmpeg || !t.node;

  async function act(name: string, fn: () => Promise<boolean>) {
    setBusy(name);
    log.clear();
    const ok = await fn();
    await refresh(true);
    setBusy(null);
    toast(ok ? "Pronto." : "Não terminou: veja o log.", ok ? "ok" : "err");
  }

  return (
    <>
      <div className="card section">
        <div className="row" style={{ marginBottom: 8 }}>
          <h3 className="grow">Ferramentas do sistema</h3>
          {missingTools && (
            <button className="btn primary" disabled={!!busy} onClick={() => act("tools", window.ea.system.installTools)}>
              {busy === "tools" ? <Spinner /> : <Icon name="sparkle" />} Instalar o que falta
            </button>
          )}
        </div>
        <Check ok={!!t.ffmpeg} label="ffmpeg" detail={t.ffmpeg ?? "corta, junta e renderiza vídeo"} />
        <Check ok={!!t.uv} label="uv (Python)" detail={t.uv ?? "roda o motor de edição"} />
        <Check ok={!!t.node} label="Node.js" detail={t.node ?? "gráficos animados (Remotion)"} optional />
        {sys.platform === "darwin" && !t.brew && missingTools && (
          <p className="hint" style={{ marginBottom: 0 }}>
            Sem Homebrew: o app instala o uv sozinho; para ffmpeg e Node, instale o{" "}
            <a onClick={() => window.ea.system.openExternal("https://brew.sh")}>Homebrew</a> e clique de novo.
          </p>
        )}
      </div>
      <div className="card section">
        <div className="row" style={{ marginBottom: 8 }}>
          <div className="grow">
            <h3>Motor de edição</h3>
            <span className="hint">transcrição, cortes, legendas, render e exportação (o mesmo do terminal)</span>
          </div>
          <button
            className={`btn ${sys.engineReady ? "" : "primary"}`}
            disabled={!!busy || !t.uv}
            onClick={() => act("engine", window.ea.system.setupEngine)}
          >
            {busy === "engine" ? <Spinner /> : <Icon name="refresh" />} {sys.engineReady ? "Reinstalar" : "Preparar motor"}
          </button>
        </div>
        <Check ok={sys.engineReady} label="Ambiente Python" detail={sys.engineReady ? "instalado" : "~2 min na primeira vez"} />
        {sys.doctor?.checks
          .filter((c) => !["ffmpeg", "ffprobe", "node (Remotion)"].includes(c.name) && !c.name.includes("KEY") && !c.name.includes("HF_"))
          .map((c) => (
            <Check key={c.name} ok={c.ok} label={c.name} detail={c.detail} optional={!c.required} />
          ))}
      </div>
      {(busy || log.lines.length > 0) && <LogView lines={log.lines} />}
    </>
  );
}

// --- AI providers ----------------------------------------------------------------------------------

export function AiPanel(p: PanelProps) {
  const { sys, settings, setSettings, secrets, setSecrets, refresh } = p;
  const [busy, setBusy] = useState(false);
  const log = useLog("codex");
  const toast = useToast();

  async function login() {
    setBusy(true);
    const ok = await window.ea.system.codexLogin();
    await refresh();
    setBusy(false);
    toast(ok ? "Conta ChatGPT conectada ao Codex." : "Login não concluído.", ok ? "ok" : "err");
  }

  return (
    <>
      <div className="row" style={{ marginBottom: 14 }}>
        <span className="label grow" style={{ margin: 0 }}>
          Editor padrão
        </span>
        <Segmented
          value={settings.agent}
          options={[
            ["claude", "Claude"],
            ["codex", "Codex"],
          ]}
          onChange={(agent) => setSettings({ agent })}
        />
      </div>

      <div className="provider" style={settings.agent === "claude" ? { borderColor: "var(--accent)" } : undefined}>
        <div className="logo" style={{ background: "#d97757", color: "#fff" }}>
          C
        </div>
        <div className="grow">
          <div className="row" style={{ marginBottom: 4 }}>
            <b className="grow">Claude</b>
            {has(secrets, "ANTHROPIC_API_KEY") && <span className="pill ok">configurado</span>}
          </div>
          <p className="hint" style={{ margin: "0 0 10px" }}>
            Usa uma chave da API Anthropic (cobrança por uso no console). O login com assinatura Claude (Pro/Max) não é
            permitido em apps de terceiros pelos termos da Anthropic.
          </p>
          <KeyField k="ANTHROPIC_API_KEY" status={secrets} onChange={setSecrets} />
          <div className="row">
            <span className="label grow" style={{ margin: 0 }}>
              Modelo
            </span>
            <select className="select" style={{ width: 260 }} value={settings.claudeModel} onChange={(e) => setSettings({ claudeModel: e.target.value })}>
              <option value="claude-sonnet-5-5">Sonnet 5.5 (rápido, econômico)</option>
              <option value="claude-opus-5-5">Opus 5.5 (mais capaz)</option>
              <option value="claude-haiku-4-5-20251001">Haiku 4.5 (mais barato)</option>
            </select>
          </div>
        </div>
      </div>

      <div className="provider" style={settings.agent === "codex" ? { borderColor: "var(--accent)" } : undefined}>
        <div className="logo" style={{ background: "#fff", color: "#000" }}>
          <Icon name="terminal" size={18} />
        </div>
        <div className="grow">
          <div className="row" style={{ marginBottom: 4 }}>
            <b className="grow">Codex (OpenAI)</b>
            {(settings.codexAuth === "account" ? sys?.codex.loggedIn : has(secrets, "OPENAI_API_KEY")) && (
              <span className="pill ok">configurado</span>
            )}
          </div>
          <p className="hint" style={{ margin: "0 0 10px" }}>
            Entre com a conta ChatGPT (Plus, Pro, Business) pelo próprio Codex da OpenAI, ou use uma chave da API OpenAI.
          </p>
          <div style={{ marginBottom: 10 }}>
            <Segmented
              value={settings.codexAuth}
              options={[
                ["account", "Conta ChatGPT"],
                ["apikey", "Chave de API"],
              ]}
              onChange={(codexAuth) => setSettings({ codexAuth })}
            />
          </div>
          {settings.codexAuth === "account" ? (
            <div className="row" style={{ marginBottom: 8 }}>
              <span className={`grow hint ${sys?.codex.loggedIn ? "ok" : ""}`}>{sys?.codex.detail || "não conectado"}</span>
              {sys?.codex.loggedIn ? (
                <button
                  className="btn"
                  onClick={async () => {
                    await window.ea.system.codexLogout();
                    await refresh();
                  }}
                >
                  Sair
                </button>
              ) : (
                <button className="btn primary" disabled={busy} onClick={login}>
                  {busy ? <Spinner /> : null} Entrar com ChatGPT
                </button>
              )}
            </div>
          ) : (
            <KeyField k="OPENAI_API_KEY" status={secrets} onChange={setSecrets} />
          )}
          {busy && <LogView lines={log.lines} height={90} />}
          <div className="row">
            <span className="label grow" style={{ margin: 0 }}>
              Modelo
            </span>
            <input
              className="input"
              style={{ width: 220 }}
              placeholder="padrão do Codex"
              value={settings.codexModel}
              onChange={(e) => setSettings({ codexModel: e.target.value })}
            />
          </div>
        </div>
      </div>
    </>
  );
}

// --- paid / optional services ----------------------------------------------------------------------

export function ServicesPanel({ settings, setSettings, secrets, setSecrets }: PanelProps) {
  return (
    <>
      <div className="card section">
        <h3>ElevenLabs</h3>
        <p className="hint" style={{ marginTop: 0 }}>
          Narração, efeitos sonoros, trilha e dublagem.
        </p>
        <KeyField k="ELEVENLABS_API_KEY" status={secrets} onChange={setSecrets} />
        <KeyField k="ELEVENLABS_VOICE_ID" status={secrets} onChange={setSecrets} />
      </div>
      <div className="card section">
        <h3>Higgsfield</h3>
        <p className="hint" style={{ marginTop: 0 }}>
          B-roll e imagens geradas por IA (Kling, Seedance, Wan…). Cobrado por geração.
        </p>
        <KeyField k="HF_API_KEY_ID" status={secrets} onChange={setSecrets} skipValidate />
        <KeyField k="HF_API_KEY_SECRET" status={secrets} onChange={setSecrets} />
        <div className="row">
          <span className="label grow" style={{ margin: 0 }}>
            Limite por geração sem confirmação (US$)
          </span>
          <input
            className="input"
            type="number"
            min={0}
            step={0.5}
            style={{ width: 100 }}
            value={settings.hfMaxUsd}
            onChange={(e) => setSettings({ hfMaxUsd: Math.max(0, Number(e.target.value) || 0) })}
          />
        </div>
      </div>
      <div className="card section">
        <h3>Pexels</h3>
        <p className="hint" style={{ marginTop: 0 }}>
          Vídeos de banco gratuitos para b-roll.
        </p>
        <KeyField k="PEXELS_API_KEY" status={secrets} onChange={setSecrets} />
      </div>
      <div className="card section">
        <h3>Hugging Face</h3>
        <p className="hint" style={{ marginTop: 0 }}>
          Opcional: detecção automática de quem fala (pyannote). Aceite os termos de pyannote/speaker-diarization-3.1.
        </p>
        <KeyField k="HF_TOKEN" status={secrets} onChange={setSecrets} />
      </div>
    </>
  );
}

// --- NLEs + models -----------------------------------------------------------------------------------

export function EditorsPanel({ sys, refresh, settings, setSettings }: PanelProps) {
  const log = useLog("setup");
  const [busy, setBusy] = useState<string | null>(null);
  const mcp = sys?.doctor?.checks.find((c) => c.name === "Resolve MCP");

  async function act(name: string, fn: () => Promise<boolean>) {
    setBusy(name);
    log.clear();
    await fn();
    await refresh(true);
    setBusy(null);
  }

  return (
    <>
      <div className="card section">
        <div className="row">
          <div className="grow">
            <h3>DaVinci Resolve</h3>
            <span className="hint">
              {sys?.resolveInstalled ? "instalado" : "não encontrado"} · exportação funciona em qualquer versão; controle ao vivo só no
              Resolve Studio (Preferences › System › General › External scripting: Local)
            </span>
          </div>
        </div>
        <div className="check-row" style={{ marginTop: 6 }}>
          <span className="grow">Deixar o editor controlar o Resolve aberto (MCP)</span>
          {!mcp?.ok ? (
            <button className="btn" disabled={!!busy || !sys?.engineReady} onClick={() => act("mcp", window.ea.system.resolveMcpSetup)}>
              {busy === "mcp" ? <Spinner /> : null} Instalar
            </button>
          ) : (
            <Switch on={settings.resolveMcp} onChange={(resolveMcp) => setSettings({ resolveMcp })} />
          )}
        </div>
      </div>
      <div className="card section">
        <h3>Premiere Pro, After Effects, Final Cut</h3>
        <span className="hint">Nada a instalar: o app gera XML, .jsx e FCPXML que esses editores abrem.</span>
      </div>
      <div className="card section">
        <div className="row">
          <div className="grow">
            <h3>Modelo de transcrição</h3>
            <span className="hint">Whisper large-v3-turbo (~1,6 GB). Baixe agora para a primeira edição não esperar.</span>
          </div>
          <button className="btn" disabled={!!busy || !sys?.engineReady} onClick={() => act("whisper", window.ea.system.downloadWhisper)}>
            {busy === "whisper" ? <Spinner /> : <Icon name="down" />} Baixar
          </button>
        </div>
      </div>
      {(busy || log.lines.length > 0) && <LogView lines={log.lines} />}
    </>
  );
}

export function useSetupState() {
  const [sys, setSys] = useState<SystemStatus | null>(null);
  const [settings, setS] = useState<Settings | null>(null);
  const [secrets, setSecrets] = useState<SecretStatus[]>([]);
  const refresh = async (doctor = false) => setSys(await window.ea.system.status(doctor));
  useEffect(() => {
    void refresh();
    void window.ea.settings.get().then(setS);
    void window.ea.secrets.status().then(setSecrets);
  }, []);
  const setSettings = async (p: Partial<Settings>) => setS(await window.ea.settings.set(p));
  return { sys, refresh, settings, setSettings, secrets, setSecrets };
}
