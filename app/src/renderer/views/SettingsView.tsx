import { useEffect, useState } from "react";
import { Icon, Spinner, Switch } from "../components/ui";
import { AiPanel, EditorsPanel, ServicesPanel, ToolsPanel, useSetupState, type PanelProps } from "./panels";

const SECTIONS = [
  ["ai", "Inteligência"],
  ["services", "Serviços e chaves"],
  ["engine", "Motor de edição"],
  ["editors", "Editores"],
  ["general", "Geral"],
] as const;
type Section = (typeof SECTIONS)[number][0];

export function SettingsView({ onRerunSetup }: { onRerunSetup: () => void }) {
  const st = useSetupState();
  const [section, setSection] = useState<Section>("ai");
  const [memDir, setMemDir] = useState<string | null>(null);
  useEffect(() => {
    void window.ea.system.memoryDir().then(setMemDir);
  }, []);
  if (!st.settings)
    return (
      <div className="empty" style={{ flex: 1 }}>
        <Spinner />
      </div>
    );
  const p = st as PanelProps;

  return (
    <>
      <div className="topbar drag">
        <h1>Configurações</h1>
      </div>
      <div className="settings">
        <nav className="settings-nav">
          {SECTIONS.map(([id, label]) => (
            <button key={id} className={`side-item ${section === id ? "active" : ""}`} onClick={() => setSection(id)}>
              {label}
            </button>
          ))}
        </nav>
        <div className="settings-body">
          <div className="inner">
            {section === "ai" && (
              <>
                <h2>Inteligência</h2>
                <p className="hint" style={{ marginTop: 0, marginBottom: 18 }}>
                  O editor que conversa com você e opera o motor de edição.
                </p>
                <AiPanel {...p} />
                <div className="card section">
                  <h3>Permissões</h3>
                  <div className="check-row">
                    <div className="grow">
                      <div>Claude: aprovar comandos e edições sem perguntar</div>
                      <div className="hint">Desligado, o app pergunta antes de cada comando fora da lista segura do motor.</div>
                    </div>
                    <Switch on={p.settings.autoApprove} onChange={(autoApprove) => p.setSettings({ autoApprove })} />
                  </div>
                  <div className="check-row">
                    <div className="grow">
                      <div>Codex: acesso total ao computador</div>
                      <div className="hint">
                        O Codex não pede aprovação no app. Desligado, ele fica numa área restrita (pode falhar ao instalar ou baixar
                        modelos).
                      </div>
                    </div>
                    <Switch
                      on={p.settings.codexSandbox === "danger-full-access"}
                      onChange={(on) => p.setSettings({ codexSandbox: on ? "danger-full-access" : "workspace-write" })}
                    />
                  </div>
                </div>
              </>
            )}
            {section === "services" && (
              <>
                <h2>Serviços e chaves</h2>
                <p className="hint" style={{ marginTop: 0, marginBottom: 18 }}>
                  Guardadas no Keychain, criptografadas. O editor recebe as chaves como variáveis de ambiente e nunca as vê no chat.
                </p>
                <ServicesPanel {...p} />
              </>
            )}
            {section === "engine" && (
              <>
                <h2>Motor de edição</h2>
                <p className="hint" style={{ marginTop: 0, marginBottom: 18 }}>
                  {p.sys?.engineDir}
                </p>
                <div className="row" style={{ marginBottom: 12 }}>
                  <button className="btn" onClick={() => p.refresh(true)}>
                    <Icon name="refresh" /> Verificar de novo
                  </button>
                </div>
                <ToolsPanel {...p} />
              </>
            )}
            {section === "editors" && (
              <>
                <h2>Editores</h2>
                <p className="hint" style={{ marginTop: 0, marginBottom: 18 }}>
                  Onde o projeto termina.
                </p>
                <EditorsPanel {...p} />
              </>
            )}
            {section === "general" && (
              <>
                <h2>Geral</h2>
                <div className="card section">
                  <h3>Pasta dos projetos</h3>
                  <div className="row" style={{ marginTop: 8 }}>
                    <code className="mono grow selectable">{p.settings.projectsDir}</code>
                    <button className="btn" onClick={() => window.ea.system.reveal(p.settings.projectsDir)}>
                      Mostrar
                    </button>
                    {!p.sys?.dev && (
                      <button
                        className="btn"
                        onClick={async () => {
                          const dir = await window.ea.system.pickFolder();
                          if (dir) await p.setSettings({ projectsDir: dir });
                        }}
                      >
                        Trocar
                      </button>
                    )}
                  </div>
                </div>
                <div className="card section">
                  <h3>Seu estilo de edição (memória)</h3>
                  <p className="hint" style={{ margin: "4px 0 8px" }}>
                    Preferências, estilos nomeados e vocabulário que o editor aprende com você. Ficam fora do projeto, só no seu
                    computador.
                  </p>
                  <div className="row">
                    <code className="mono grow selectable">{memDir ?? "—"}</code>
                    {memDir && (
                      <button className="btn" onClick={() => window.ea.system.openPath(memDir)}>
                        Abrir
                      </button>
                    )}
                  </div>
                </div>
                <div className="card section">
                  <h3>Configuração inicial</h3>
                  <div className="row" style={{ marginTop: 8 }}>
                    <span className="hint grow">Refazer o passo a passo do primeiro uso.</span>
                    <button className="btn" onClick={onRerunSetup}>
                      Abrir assistente
                    </button>
                  </div>
                </div>
                <p className="hint">
                  editassist {p.sys?.appVersion} · {p.sys?.platform} {p.sys?.arch}
                  {p.sys?.dev ? " · modo desenvolvimento" : ""}
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
