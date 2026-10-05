import { useState } from "react";
import type { NewProject, ProjectSummary } from "../../shared/types";
import { Icon, Modal, Spinner, fmtAgo, fmtTime, useToast } from "../components/ui";

const PRESETS: [NewProject["preset"], string, number, number][] = [
  ["youtube", "YouTube 16:9", 32, 18],
  ["shorts", "Shorts / Reels 9:16", 14, 25],
  ["square", "Quadrado 1:1", 22, 22],
  ["podcast", "Podcast 16:9", 32, 18],
];

export function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: (name: string) => void }) {
  const [name, setName] = useState("");
  const [preset, setPreset] = useState<NewProject["preset"]>("youtube");
  const [language, setLanguage] = useState("pt");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function create() {
    setBusy(true);
    try {
      const p = await window.ea.projects.create({ name, preset, language });
      onCreated(p.name);
    } catch (e) {
      toast((e as Error).message.replace(/^Error invoking remote method '[^']+': (Error: )?/, ""), "err");
      setBusy(false);
    }
  }

  return (
    <Modal onClose={onClose}>
      <h2>Novo projeto</h2>
      <p className="hint" style={{ marginTop: 0 }}>
        Formato e idioma são só o ponto de partida; o editor ajusta se você pedir.
      </p>
      <label className="label" style={{ marginTop: 16 }}>
        Nome
      </label>
      <input
        className="input"
        autoFocus
        placeholder="ex.: entrevista-ana"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && name.trim() && create()}
      />
      <label className="label" style={{ marginTop: 16 }}>
        Formato
      </label>
      <div className="preset-grid">
        {PRESETS.map(([id, label, w, h]) => (
          <button key={id} className={`preset ${preset === id ? "on" : ""}`} onClick={() => setPreset(id)}>
            <span className="shape" style={{ width: w, height: h }} />
            {label}
          </button>
        ))}
      </div>
      <label className="label" style={{ marginTop: 16 }}>
        Idioma falado no vídeo
      </label>
      <select className="select" value={language} onChange={(e) => setLanguage(e.target.value)}>
        <option value="pt">Português</option>
        <option value="en">Inglês</option>
        <option value="es">Espanhol</option>
        <option value="fr">Francês</option>
        <option value="de">Alemão</option>
        <option value="it">Italiano</option>
      </select>
      <div className="actions">
        <button className="btn ghost" onClick={onClose}>
          Cancelar
        </button>
        <button className="btn primary" disabled={!name.trim() || busy} onClick={create}>
          {busy && <Spinner />} Criar projeto
        </button>
      </div>
    </Modal>
  );
}

export function Home({ projects, onOpen, onNew }: { projects: ProjectSummary[]; onOpen: (n: string) => void; onNew: () => void }) {
  return (
    <>
      <div className="topbar drag">
        <h1>Projetos</h1>
        <span className="spacer" />
        <button className="btn primary no-drag" onClick={onNew}>
          <Icon name="plus" /> Novo projeto
        </button>
      </div>
      <div className="home">
        <h2>Bom te ver.</h2>
        <p className="muted" style={{ margin: 0 }}>
          Crie um projeto, arraste os vídeos e descreva o que você quer. O editor faz o resto e te mostra o preview.
        </p>
        <div className="grid">
          <button className="card new-card" onClick={onNew}>
            <Icon name="plus" size={26} />
            Novo projeto
          </button>
          {projects.map((p) => (
            <div key={p.name} className="card proj-card" onClick={() => onOpen(p.name)}>
              <div className="thumb">
                {p.poster ? (
                  <video src={`${window.ea.projects.mediaUrl(p.name, p.poster)}#t=1`} preload="metadata" muted />
                ) : (
                  <Icon name="film" size={28} />
                )}
              </div>
              <div className="info">
                <div className="title">{p.name}</div>
                <div className="hint">
                  {p.settings.width}×{p.settings.height} · {p.inputs} arquivo(s){p.length ? ` · ${fmtTime(p.length)}` : ""} ·{" "}
                  {fmtAgo(p.updated)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
