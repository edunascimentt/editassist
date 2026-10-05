import { useCallback, useEffect, useState } from "react";
import type { ProjectSummary, Settings } from "../shared/types";
import { Icon, Spinner } from "./components/ui";
import { Home, NewProjectModal } from "./views/Home";
import { Onboarding } from "./views/Onboarding";
import { ProjectView } from "./views/ProjectView";
import { SettingsView } from "./views/SettingsView";

type View = { kind: "home" } | { kind: "project"; name: string } | { kind: "settings" };

export function App() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [view, setView] = useState<View>({ kind: "home" });
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [newOpen, setNewOpen] = useState(false);

  const loadProjects = useCallback(async () => setProjects(await window.ea.projects.list()), []);

  useEffect(() => {
    void window.ea.settings.get().then(setSettings);
    void loadProjects();
    const off1 = window.ea.on.projectChanged(() => loadProjects());
    const off2 = window.ea.on.state((e) =>
      setRunning((r) => {
        const n = new Set(r);
        if (e.state === "running") n.add(e.project);
        else n.delete(e.project);
        return n;
      }),
    );
    return () => {
      off1();
      off2();
    };
  }, [loadProjects]);

  // settings may change in the Settings screen: re-read when navigating
  useEffect(() => {
    void window.ea.settings.get().then(setSettings);
  }, [view]);

  if (!settings)
    return (
      <div className="empty" style={{ height: "100%" }}>
        <Spinner />
      </div>
    );

  if (!settings.onboarded || setupOpen)
    return (
      <Onboarding
        onDone={async () => {
          setSetupOpen(false);
          setSettings(await window.ea.settings.get());
          await loadProjects();
        }}
      />
    );

  const updateSettings = async (p: Partial<Settings>) => setSettings(await window.ea.settings.set(p));
  const current = view.kind === "project" ? view.name : null;

  return (
    <div className={`app platform-${navigator.userAgent.includes("Windows") ? "win" : "mac"}`}>
      <aside className="sidebar">
        <div className="brand drag">
          <span className="dot" /> editassist
        </div>
        <div style={{ padding: "0 8px 6px" }}>
          <button className={`side-item ${view.kind === "home" ? "active" : ""}`} onClick={() => setView({ kind: "home" })}>
            <Icon name="film" /> <span className="name">Projetos</span>
          </button>
        </div>
        <div className="side-section">
          Recentes
          <button className="btn ghost icon sm" title="Novo projeto" onClick={() => setNewOpen(true)}>
            <Icon name="plus" size={14} />
          </button>
        </div>
        <div className="side-list">
          {projects.map((p) => (
            <button
              key={p.name}
              className={`side-item ${current === p.name ? "active" : ""}`}
              onClick={() => setView({ kind: "project", name: p.name })}
            >
              <Icon name="folder" size={14} />
              <span className="name">{p.name}</span>
              {running.has(p.name) && <span className="badge" title="editando" />}
            </button>
          ))}
          {!projects.length && <div className="hint" style={{ padding: "4px 8px" }}>Nenhum projeto ainda.</div>}
        </div>
        <div className="side-foot">
          <button className={`side-item ${view.kind === "settings" ? "active" : ""}`} onClick={() => setView({ kind: "settings" })}>
            <Icon name="settings" /> <span className="name">Configurações</span>
          </button>
        </div>
      </aside>
      <main className="main">
        {view.kind === "home" && <Home projects={projects} onOpen={(name) => setView({ kind: "project", name })} onNew={() => setNewOpen(true)} />}
        {view.kind === "project" && (
          <ProjectView
            key={view.name}
            name={view.name}
            settings={settings}
            onSettings={updateSettings}
            onDeleted={async () => {
              await loadProjects();
              setView({ kind: "home" });
            }}
          />
        )}
        {view.kind === "settings" && <SettingsView onRerunSetup={() => setSetupOpen(true)} />}
      </main>
      {newOpen && (
        <NewProjectModal
          onClose={() => setNewOpen(false)}
          onCreated={async (name) => {
            setNewOpen(false);
            await loadProjects();
            setView({ kind: "project", name });
          }}
        />
      )}
    </div>
  );
}
