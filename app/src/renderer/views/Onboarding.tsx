import { useState } from "react";
import { Icon, Spinner } from "../components/ui";
import { AiPanel, EditorsPanel, ServicesPanel, ToolsPanel, aiReady, useSetupState, type PanelProps } from "./panels";

const STEPS = ["Boas-vindas", "Motor de edição", "Inteligência", "Serviços", "Editores", "Pronto"];

export function Onboarding({ onDone }: { onDone: () => void }) {
  const st = useSetupState();
  const [step, setStep] = useState(0);
  const [finishing, setFinishing] = useState(false);
  if (!st.settings)
    return (
      <div className="empty" style={{ height: "100%" }}>
        <Spinner />
      </div>
    );
  const p = st as PanelProps;
  const engineOk = !!st.sys?.engineReady && !!st.sys.tools.ffmpeg && !!st.sys.tools.uv;
  const canNext = [true, engineOk, aiReady(p), true, true, true][step];

  async function finish() {
    setFinishing(true);
    await window.ea.system.setupDone();
    await p.setSettings({ onboarded: true });
    onDone();
  }

  return (
    <div className="onboarding">
      <aside className="ob-side drag">
        <div className="row" style={{ fontWeight: 700, fontSize: 15, marginBottom: 22, paddingLeft: 10 }}>
          <span className="logo-dot" />
          editassist
        </div>
        {STEPS.map((s, i) => (
          <div key={s} className={`ob-step ${i === step ? "on" : i < step ? "done" : ""}`}>
            <span className="n">{i < step ? <Icon name="check" size={12} /> : i + 1}</span>
            {s}
          </div>
        ))}
      </aside>
      <main className="ob-main">
        <div className="inner">
          {step === 0 && (
            <>
              <h1>Seu editor de vídeo com IA</h1>
              <p className="lead">
                Você descreve o vídeo; o editor transcreve, corta silêncios, escolhe as melhores falas, põe legendas, zooms, b-roll,
                trilha e cor, e entrega o arquivo final ou o projeto aberto no DaVinci Resolve, Premiere ou After Effects.
              </p>
              <div className="card section">
                <h3>Nesta configuração</h3>
                <ul className="muted" style={{ margin: "8px 0 0", paddingLeft: 18, lineHeight: 1.9 }}>
                  <li>instalamos as ferramentas e o motor de edição (alguns minutos)</li>
                  <li>conectamos o Claude (chave de API) ou o Codex (conta ChatGPT ou chave de API)</li>
                  <li>adicionamos as chaves opcionais: ElevenLabs, Higgsfield, Pexels</li>
                  <li>ligamos o DaVinci Resolve, se você usa</li>
                </ul>
              </div>
              <p className="hint">
                <Icon name="shield" size={12} /> As chaves ficam no Keychain do macOS, criptografadas, e nunca aparecem na tela nem na
                conversa com a IA.
              </p>
            </>
          )}
          {step === 1 && (
            <>
              <h1>Motor de edição</h1>
              <p className="lead">ffmpeg, Python e o motor do editassist. O app instala o que faltar.</p>
              <ToolsPanel {...p} />
            </>
          )}
          {step === 2 && (
            <>
              <h1>Inteligência</h1>
              <p className="lead">Quem edita: Claude ou Codex. Configure um ou os dois; você troca quando quiser.</p>
              <AiPanel {...p} />
            </>
          )}
          {step === 3 && (
            <>
              <h1>Serviços</h1>
              <p className="lead">Todos opcionais. Cada chave é testada na hora, sem custo.</p>
              <ServicesPanel {...p} />
            </>
          )}
          {step === 4 && (
            <>
              <h1>Editores e modelos</h1>
              <p className="lead">Onde você termina a edição.</p>
              <EditorsPanel {...p} />
            </>
          )}
          {step === 5 && (
            <>
              <h1>Tudo pronto</h1>
              <p className="lead">Crie um projeto, arraste os vídeos e peça o que quiser.</p>
              <div className="card section">
                <h3>Pasta dos projetos</h3>
                <div className="row" style={{ marginTop: 8 }}>
                  <code className="grow mono selectable">{p.settings.projectsDir}</code>
                  {!st.sys?.dev && (
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
                <h3>Seu estilo</h3>
                <p className="hint" style={{ margin: "4px 0 0" }}>
                  No primeiro projeto, peça "me faz o questionário de preferências": em 3 a 5 minutos o editor aprende seu ritmo de
                  corte, legendas, trilha e cor, e usa isso em todos os vídeos.
                </p>
              </div>
            </>
          )}
          <div className="row" style={{ marginTop: 26 }}>
            {step > 0 && (
              <button className="btn ghost" onClick={() => setStep(step - 1)}>
                Voltar
              </button>
            )}
            <span className="spacer" />
            {step === 3 || step === 4 ? (
              <button className="btn ghost" onClick={() => setStep(step + 1)}>
                Pular
              </button>
            ) : null}
            {step < STEPS.length - 1 ? (
              <button className="btn primary lg" disabled={!canNext} onClick={() => setStep(step + 1)}>
                Continuar <Icon name="chevron" />
              </button>
            ) : (
              <button className="btn primary lg" disabled={finishing} onClick={finish}>
                {finishing ? <Spinner /> : null} Começar a editar
              </button>
            )}
          </div>
          {step === 1 && !engineOk && <p className="hint" style={{ textAlign: "right" }}>Prepare o motor para continuar.</p>}
          {step === 2 && !canNext && <p className="hint" style={{ textAlign: "right" }}>Configure o editor padrão para continuar.</p>}
        </div>
      </main>
    </div>
  );
}
