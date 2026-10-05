import { useCallback, useEffect, useRef, useState } from "react";
import type { OutputFile, ProjectDetail, Settings } from "../../shared/types";
import { TimelineView } from "../components/TimelineView";
import { Icon, LogView, Modal, Spinner, fmtAgo, fmtSize, fmtTime, useLog, useToast } from "../components/ui";
import { ChatPanel } from "./ChatPanel";

type Tab = "preview" | "media" | "outputs";

const EXPORTS: [string, string][] = [
  ["DaVinci Resolve (abrir)", "Exporte para o DaVinci Resolve e abra o projeto lá."],
  ["Premiere Pro", "Exporte o projeto para o Premiere Pro."],
  ["After Effects", "Exporte o projeto para o After Effects."],
  ["Final Cut Pro", "Exporte o projeto para o Final Cut Pro (FCPXML)."],
  ["MP4 final: YouTube", "Renderize a versão final em MP4 para YouTube, com QA antes."],
  ["MP4 final: Reels / TikTok", "Renderize a versão final vertical para Reels e TikTok, com QA antes."],
  ["Thumbnail + título", "Faça a thumbnail e escreva título, descrição e capítulos."],
];

function FileCard({
  project,
  dir,
  f,
  on,
  onClick,
  meta,
}: {
  project: string;
  dir: string;
  f: OutputFile;
  on: boolean;
  onClick: () => void;
  meta?: string;
}) {
  const url = window.ea.projects.mediaUrl(project, f.path);
  return (
    <div className={`file ${on ? "on" : ""}`} onClick={onClick} onDoubleClick={() => window.ea.system.openPath(`${dir}/${f.path}`)}>
      <div className="thumb">
        {f.kind === "video" ? (
          <video src={`${url}#t=0.5`} preload="metadata" muted />
        ) : f.kind === "image" ? (
          <img src={url} alt="" />
        ) : (
          <Icon name={f.kind === "audio" ? "wave" : f.kind === "nle" ? "film" : "folder"} size={26} />
        )}
      </div>
      <div className="info">
        <div className="fname" title={f.name}>
          {f.name}
        </div>
        <div className="fmeta">{meta ?? `${fmtSize(f.size)} · ${fmtAgo(f.mtime)}`}</div>
      </div>
    </div>
  );
}

export function ProjectView({
  name,
  settings,
  onSettings,
  onDeleted,
}: {
  name: string;
  settings: Settings;
  onSettings: (p: Partial<Settings>) => void;
  onDeleted: () => void;
}) {
  const [d, setD] = useState<ProjectDetail | null>(null);
  const [tab, setTab] = useState<Tab>("preview");
  const [selected, setSelected] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState<number | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const loaded = useRef(false);
  const knownOutputs = useRef<Set<string>>(new Set());
  const log = useLog(useCallback((c: string) => c === `run:${name}` || c === `ingest:${name}`, [name]));
  const toast = useToast();

  const load = useCallback(async () => {
    try {
      const p = await window.ea.projects.get(name);
      setD(p);
      const videos = p.outputs.filter((o) => o.kind === "video"); // newest first
      const key = (v: OutputFile) => `${v.path}@${v.mtime}`;
      // a file still being written (render in progress) isn't shown yet: look again shortly
      const settled = (v: OutputFile) => v.size > 0 && Date.now() - v.mtime > 2000;
      if (videos.some((v) => !settled(v))) setTimeout(() => void loadRef.current?.(), 2500);
      const fresh = videos.filter((v) => settled(v) && !knownOutputs.current.has(key(v)));
      videos.filter(settled).forEach((v) => knownOutputs.current.add(key(v)));
      if (!loaded.current) {
        loaded.current = true;
        setSelected(videos[0]?.path ?? p.inputFiles.find((i) => i.kind === "video")?.path ?? null);
        if (!p.inputFiles.length) setTab("media");
      } else if (fresh.length) {
        // a new render appeared: show it
        setSelected(fresh[0].path);
        setTab("preview");
      }
    } catch (e) {
      toast((e as Error).message, "err");
    }
  }, [name, toast]);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    knownOutputs.current = new Set();
    loaded.current = false;
    setSelected(null);
    setD(null);
    setPlayhead(null);
    void load();
    const off1 = window.ea.on.projectChanged((p) => p === name && load());
    const off2 = window.ea.on.state((e) => e.project === name && e.state === "idle" && load());
    return () => {
      off1();
      off2();
    };
  }, [name, load]);

  async function importPaths(paths: string[]) {
    if (!paths.length) return;
    setBusy("import");
    log.clear();
    try {
      setD(await window.ea.projects.importMedia(name, paths));
      toast(`${paths.length} arquivo(s) importado(s).`, "ok");
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(null);
    }
  }

  async function renderPreview() {
    setBusy("render");
    log.clear();
    const r = await window.ea.projects.run(name, ["render", name, "--preset", "preview"]);
    setBusy(null);
    if (!r.ok) toast(`Render falhou: ${r.stderr.trim().split("\n").pop()}`, "err");
    await load();
  }

  async function sendToAgent(prompt: string) {
    setExportOpen(false);
    try {
      await window.ea.agent.send(name, prompt);
    } catch (e) {
      toast((e as Error).message.replace(/^Error invoking remote method '[^']+': (Error: )?/, ""), "err");
    }
  }

  const sel = d ? [...d.outputs, ...d.inputFiles].find((f) => f.path === selected) ?? null : null;
  const isTimelineRender = !!(sel && d?.timeline && sel.path.startsWith("output/") && sel.kind === "video" && sel.name.startsWith(d.timeline.name));
  const mediaMeta = (f: OutputFile) => {
    const m = d?.media.find((x) => x.path === f.path);
    return m?.duration ? `${fmtTime(m.duration)}${m.width ? ` · ${m.width}×${m.height}` : ""} · ${fmtSize(f.size)}` : fmtSize(f.size);
  };

  return (
    <>
      <div className="topbar drag">
        <h1>{name}</h1>
        {d && (
          <span className="meta">
            {d.settings.width}×{d.settings.height} · {d.settings.fps} fps{d.length ? ` · ${fmtTime(d.length)}` : ""}
          </span>
        )}
        <span className="spacer" />
        <div className="row no-drag">
          <button className="btn" disabled={busy === "import"} onClick={async () => importPaths(await window.ea.system.pickMedia())}>
            {busy === "import" ? <Spinner /> : <Icon name="upload" />} Importar
          </button>
          <button className="btn" disabled={!d?.hasTimeline || !!busy} onClick={renderPreview} title="Renderiza a timeline atual em baixa resolução">
            {busy === "render" ? <Spinner /> : <Icon name="play" />} Preview
          </button>
          <div style={{ position: "relative" }}>
            <button className="btn primary" disabled={!d?.hasTimeline} onClick={() => setExportOpen(!exportOpen)}>
              <Icon name="export" /> Exportar <Icon name="down" size={13} />
            </button>
            {exportOpen && (
              <div
                className="card"
                style={{ position: "absolute", right: 0, top: 36, width: 250, padding: 4, zIndex: 20, boxShadow: "var(--shadow)" }}
                onMouseLeave={() => setExportOpen(false)}
              >
                {EXPORTS.map(([label, prompt]) => (
                  <button key={label} className="side-item" onClick={() => sendToAgent(prompt)}>
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button className="btn ghost icon" title="Mostrar pasta" onClick={() => d && window.ea.system.reveal(`${d.dir}/project.json`)}>
            <Icon name="folder" />
          </button>
          <button className="btn ghost icon" title="Mover para o Lixo" onClick={() => setConfirmDelete(true)}>
            <Icon name="trash" />
          </button>
        </div>
      </div>
      <div className="project">
        <section
          className="workspace"
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={(e) => e.currentTarget.contains(e.relatedTarget as Node) || setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void importPaths([...e.dataTransfer.files].map((f) => window.ea.pathForFile(f)).filter(Boolean));
          }}
          style={{ position: "relative" }}
        >
          {dragging && <div className="dropzone">Solte para importar para input/</div>}
          <div className="tabs">
            {(
              [
                ["preview", "Preview", 0],
                ["media", "Mídia", d?.inputFiles.length ?? 0],
                ["outputs", "Saídas", d?.outputs.length ?? 0],
              ] as [Tab, string, number][]
            ).map(([t, label, n]) => (
              <button key={t} className={`tab ${tab === t ? "on" : ""}`} onClick={() => setTab(t)}>
                {label}
                {n ? <span className="count">{n}</span> : null}
              </button>
            ))}
          </div>
          {tab === "preview" && (
            <div className="viewer">
              <div className="player">
                {!sel ? (
                  <div className="empty">
                    <Icon name="film" size={30} />
                    <h3>{d?.inputFiles.length ? "Nada renderizado ainda" : "Comece importando os vídeos"}</h3>
                    <p style={{ margin: 0 }}>
                      {d?.inputFiles.length ? "Peça uma edição no chat; o preview aparece aqui." : "Arraste os arquivos para cá ou clique em Importar."}
                    </p>
                  </div>
                ) : sel.kind === "video" ? (
                  <video
                    key={`${sel.path}@${sel.mtime}`}
                    ref={video}
                    src={window.ea.projects.mediaUrl(name, sel.path)}
                    controls
                    autoPlay={false}
                    onTimeUpdate={(e) => isTimelineRender && setPlayhead(e.currentTarget.currentTime)}
                  />
                ) : sel.kind === "image" ? (
                  <img src={window.ea.projects.mediaUrl(name, sel.path)} alt="" />
                ) : sel.kind === "audio" ? (
                  <audio src={window.ea.projects.mediaUrl(name, sel.path)} controls />
                ) : (
                  <div className="empty">
                    <Icon name="film" size={30} />
                    <h3>{sel.name}</h3>
                    <button className="btn" onClick={() => window.ea.system.openPath(`${d!.dir}/${sel.path}`)}>
                      Abrir no app padrão
                    </button>
                  </div>
                )}
              </div>
              {sel && (
                <div className="player-bar">
                  <span className="mono grow" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {sel.path}
                  </span>
                  <span className="hint">{fmtSize(sel.size)}</span>
                  <button className="btn sm" onClick={() => window.ea.system.reveal(`${d!.dir}/${sel.path}`)}>
                    Mostrar no Finder
                  </button>
                </div>
              )}
            </div>
          )}
          {tab === "media" && (
            <div className="pane">
              {!d?.inputFiles.length ? (
                <div className="empty" style={{ height: "100%" }}>
                  <Icon name="upload" size={30} />
                  <h3>Arraste vídeos, áudios e imagens para cá</h3>
                  <p style={{ margin: 0 }}>Os originais não são alterados: o app copia para input/ e cataloga.</p>
                  <button className="btn primary" onClick={async () => importPaths(await window.ea.system.pickMedia())}>
                    Escolher arquivos
                  </button>
                </div>
              ) : (
                <div className="file-list">
                  {d.inputFiles.map((f) => (
                    <FileCard
                      key={f.path}
                      project={name}
                      dir={d.dir}
                      f={f}
                      meta={mediaMeta(f)}
                      on={selected === f.path}
                      onClick={() => {
                        setSelected(f.path);
                        setTab("preview");
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
          {tab === "outputs" && (
            <div className="pane">
              {!d?.outputs.length ? (
                <div className="empty" style={{ height: "100%" }}>
                  <Icon name="export" size={30} />
                  <h3>Sem saídas ainda</h3>
                  <p style={{ margin: 0 }}>Previews, renders finais, legendas e projetos para Resolve/Premiere aparecem aqui.</p>
                </div>
              ) : (
                <div className="file-list">
                  {d.outputs.map((f) => (
                    <FileCard
                      key={f.path}
                      project={name}
                      dir={d.dir}
                      f={f}
                      on={selected === f.path}
                      onClick={() => {
                        if (f.kind === "video" || f.kind === "image" || f.kind === "audio") {
                          setSelected(f.path);
                          setTab("preview");
                        } else void window.ea.system.reveal(`${d.dir}/${f.path}`);
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
          {(busy === "render" || busy === "import") && (
            <div style={{ padding: "0 12px 10px" }}>
              <LogView lines={log.lines.length ? log.lines : [busy === "render" ? "Renderizando o preview…" : "Importando…"]} height={90} />
            </div>
          )}
          {d?.timeline && (
            <TimelineView
              timeline={d.timeline}
              playhead={isTimelineRender ? playhead : null}
              onSeek={(t) => {
                if (isTimelineRender && video.current) video.current.currentTime = t;
                setPlayhead(t);
              }}
            />
          )}
        </section>
        <ChatPanel project={name} detail={d} settings={settings} onSettings={onSettings} />
      </div>
      {confirmDelete && (
        <Modal onClose={() => setConfirmDelete(false)}>
          <h2>Mover "{name}" para o Lixo?</h2>
          <p className="muted">A pasta inteira do projeto (mídia copiada, renders e conversa) vai para o Lixo. Dá para recuperar de lá.</p>
          <div className="actions">
            <button className="btn ghost" onClick={() => setConfirmDelete(false)}>
              Cancelar
            </button>
            <button
              className="btn primary"
              onClick={async () => {
                await window.ea.projects.trash(name);
                setConfirmDelete(false);
                onDeleted();
              }}
            >
              Mover para o Lixo
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
