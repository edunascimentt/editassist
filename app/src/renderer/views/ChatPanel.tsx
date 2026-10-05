import { useEffect, useMemo, useRef, useState } from "react";
import type { AgentState, ChatItem, ProjectDetail, Settings } from "../../shared/types";
import { Markdown } from "../components/Markdown";
import { Icon, Segmented, Spinner, fmtTime, useToast } from "../components/ui";

type Tool = Extract<ChatItem, { kind: "tool" }>;
type Approval = Extract<ChatItem, { kind: "approval" }>;
type Ask = Extract<ChatItem, { kind: "question" }>;

function quickActions(p: ProjectDetail | null): [string, string][] {
  if (!p) return [];
  if (!p.inputFiles.length) return [["Questionário de preferências", "Me faz o questionário de preferências."]];
  if (!p.hasTimeline)
    return [
      ["Cortar silêncios", "Corte os silêncios e as hesitações, legende e me mostre um preview."],
      ["Primeiro corte", "Monte um primeiro corte com as melhores falas, gancho no começo, e me mostre um preview."],
      ["Melhores momentos", "Encontre os melhores momentos e transforme em cortes curtos para Reels/TikTok."],
      ["O que tem aqui?", "Assista o material (transcreva e olhe as imagens) e me diga o que tem e o que dá pra fazer."],
    ];
  return [
    ["Legendas", "Adicione legendas no meu estilo."],
    ["Zooms", "Adicione zooms nos pontos fortes e para esconder os cortes."],
    ["Trilha", "Coloque uma trilha de fundo com ducking sob a fala."],
    ["Cor", "Corrija a cor e iguale as câmeras."],
    ["B-roll", "Cubra as partes paradas com b-roll."],
    ["Revisar (QA)", "Rode o QA e corrija o que encontrar."],
  ];
}

function ToolRow({ t, project }: { t: Tool; project: string }) {
  const [open, setOpen] = useState(false);
  const body = [t.detail, t.output].filter(Boolean).join("\n\n");
  return (
    <div className="tool">
      <div className="tool-head" onClick={() => setOpen(!open)}>
        {t.status === "running" ? <Spinner /> : <span className={`status-dot ${t.status}`} />}
        <span className="t">{t.title}</span>
        {body && <Icon name={open ? "down" : "chevron"} size={13} />}
      </div>
      {t.media && <img className="tool-img" src={window.ea.projects.mediaUrl(project, t.media)} alt="" />}
      {open && body && <div className="tool-body">{body}</div>}
    </div>
  );
}

function ApprovalCard({ a }: { a: Approval }) {
  const reply = (decision: "allow" | "always" | "deny") => window.ea.agent.reply(a.requestId, { kind: "approval", decision });
  if (a.status !== "pending")
    return (
      <div className="tool">
        <div className="tool-head">
          <span className={`status-dot ${a.status === "denied" ? "error" : "done"}`} />
          <span className="t">
            {a.status === "denied" ? "Negado" : a.status === "always" ? "Sempre permitido" : "Permitido"}: {a.title}
          </span>
        </div>
      </div>
    );
  return (
    <div className="ask">
      <h4>O editor quer executar</h4>
      <div style={{ fontWeight: 550 }}>{a.title}</div>
      {a.detail && a.detail !== a.title && (
        <div className="tool-body" style={{ border: 0, padding: "6px 0 0", maxHeight: 140 }}>
          {a.detail}
        </div>
      )}
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn primary sm" onClick={() => reply("allow")}>
          Permitir
        </button>
        {a.canRemember && (
          <button className="btn sm" onClick={() => reply("always")}>
            Sempre permitir
          </button>
        )}
        <span className="spacer" />
        <button className="btn ghost sm danger" onClick={() => reply("deny")}>
          Negar
        </button>
      </div>
    </div>
  );
}

function QuestionCard({ q }: { q: Ask }) {
  const [sel, setSel] = useState<Record<string, string[]>>({});
  const [other, setOther] = useState<Record<string, string>>({});
  const done = q.status !== "pending";
  const answerOf = (question: string) => other[question]?.trim() || (sel[question] ?? []).join(", ");
  const complete = q.questions.every((x) => answerOf(x.question));

  function toggle(question: string, label: string, multi: boolean) {
    setOther((o) => ({ ...o, [question]: "" }));
    setSel((s) => {
      const cur = s[question] ?? [];
      return { ...s, [question]: multi ? (cur.includes(label) ? cur.filter((l) => l !== label) : [...cur, label]) : [label] };
    });
  }

  function submit() {
    const answers = Object.fromEntries(q.questions.map((x) => [x.question, answerOf(x.question)]));
    void window.ea.agent.reply(q.requestId, { kind: "question", answers });
  }

  return (
    <div className={`ask ${done ? "done" : ""}`}>
      {q.questions.map((x) => (
        <div key={x.question} style={{ marginBottom: 10 }}>
          <span className="pill accent">{x.header}</span>
          <h4 style={{ marginTop: 6 }}>{x.question}</h4>
          {done ? (
            <div className="muted">→ {q.answers?.[x.question] ?? "—"}</div>
          ) : (
            <div className="opts">
              {x.options.map((o) => (
                <button
                  key={o.label}
                  className={`opt ${(sel[x.question] ?? []).includes(o.label) ? "on" : ""}`}
                  onClick={() => toggle(x.question, o.label, x.multiSelect)}
                >
                  <b>{o.label}</b>
                  <span>{o.description}</span>
                </button>
              ))}
              <input
                className="input"
                placeholder="Outra resposta…"
                value={other[x.question] ?? ""}
                onChange={(e) => {
                  setOther((o) => ({ ...o, [x.question]: e.target.value }));
                  if (e.target.value) setSel((s) => ({ ...s, [x.question]: [] }));
                }}
              />
            </div>
          )}
        </div>
      ))}
      {!done && (
        <div className="row">
          <span className="spacer" />
          <button className="btn primary sm" disabled={!complete} onClick={submit}>
            Responder
          </button>
        </div>
      )}
    </div>
  );
}

export function ChatPanel({
  project,
  detail,
  settings,
  onSettings,
}: {
  project: string;
  detail: ProjectDetail | null;
  settings: Settings;
  onSettings: (p: Partial<Settings>) => void;
}) {
  const [items, setItems] = useState<ChatItem[]>([]);
  const [state, setState] = useState<AgentState>("idle");
  const [text, setText] = useState("");
  const scroll = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const toast = useToast();

  useEffect(() => {
    let alive = true;
    void window.ea.agent.history(project).then((h) => {
      if (!alive) return;
      setItems(h.items);
      setState(h.state);
      stick.current = true;
    });
    const off1 = window.ea.on.chat((e) => {
      if (e.project !== project) return;
      setItems((xs) => {
        const i = xs.findIndex((x) => x.id === e.item.id);
        if (i < 0) return [...xs, e.item];
        const c = xs.slice();
        c[i] = e.item;
        return c;
      });
    });
    const off2 = window.ea.on.state((e) => e.project === project && setState(e.state));
    return () => {
      alive = false;
      off1();
      off2();
    };
  }, [project]);

  useEffect(() => {
    if (stick.current) scroll.current?.scrollTo(0, scroll.current.scrollHeight);
  }, [items]);

  const running = state === "running";
  const waiting = items.some((i) => (i.kind === "approval" || i.kind === "question") && i.status === "pending");

  async function send(t = text) {
    const msg = t.trim();
    if (!msg || running) return;
    setText("");
    stick.current = true;
    try {
      await window.ea.agent.send(project, msg);
    } catch (e) {
      toast((e as Error).message.replace(/^Error invoking remote method '[^']+': (Error: )?/, ""), "err");
    }
  }

  // consecutive tool rows render as one compact group
  const blocks = useMemo(() => {
    const out: (ChatItem | Tool[])[] = [];
    for (const it of items) {
      const last = out[out.length - 1];
      if (it.kind === "tool" && Array.isArray(last)) last.push(it);
      else out.push(it.kind === "tool" ? [it] : it);
    }
    return out;
  }, [items]);

  return (
    <section className="chat">
      <div className="chat-head">
        <Segmented
          value={settings.agent}
          options={[
            ["claude", "Claude"],
            ["codex", "Codex"],
          ]}
          onChange={(agent) => onSettings({ agent })}
        />
        <span className="hint grow">{settings.agent === "claude" ? settings.claudeModel.replace("claude-", "") : settings.codexModel || "Codex"}</span>
        {running && (
          <span className="row hint">
            <Spinner /> {waiting ? "esperando você" : "editando"}
          </span>
        )}
        <button
          className="btn ghost icon"
          title="Nova conversa"
          disabled={running}
          onClick={async () => {
            await window.ea.agent.reset(project);
            setItems([]);
          }}
        >
          <Icon name="reset" size={15} />
        </button>
      </div>
      <div
        className="chat-scroll"
        ref={scroll}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
        }}
      >
        {!items.length && (
          <div className="empty" style={{ marginTop: 30 }}>
            <Icon name="sparkle" size={28} />
            <h3>O que vamos editar?</h3>
            <p style={{ maxWidth: 300, margin: 0 }}>
              {detail?.inputFiles.length
                ? "Descreva o vídeo que você quer, ou escolha uma ação abaixo."
                : "Arraste os vídeos para a área ao lado (ou use Importar) e depois diga o que quer."}
            </p>
          </div>
        )}
        {blocks.map((b, i) => {
          if (Array.isArray(b))
            return (
              <div className="tool-group" key={b[0].id}>
                {b.map((t) => (
                  <ToolRow key={t.id} t={t} project={project} />
                ))}
              </div>
            );
          switch (b.kind) {
            case "user":
              return (
                <div key={b.id} className="msg user">
                  {b.text}
                </div>
              );
            case "assistant":
              return b.text.trim() || b.streaming ? (
                <div key={b.id} className={`msg assistant ${b.streaming ? "caret" : ""}`}>
                  <Markdown text={b.text} />
                </div>
              ) : null;
            case "thinking":
              return (
                <div key={b.id} className="hint" style={{ fontStyle: "italic" }}>
                  {b.text.slice(0, 300)}
                </div>
              );
            case "approval":
              return <ApprovalCard key={b.id} a={b} />;
            case "question":
              return <QuestionCard key={b.id} q={b} />;
            case "notice":
              return (
                <div key={b.id} className="notice">
                  {b.text}
                </div>
              );
            case "error":
              return (
                <div key={b.id} className="notice warn err">
                  {b.text}
                </div>
              );
            case "result":
              return (
                <div key={b.id} className="result" style={i === blocks.length - 1 ? undefined : { opacity: 0.6 }}>
                  {b.isError && <span className="err">{b.text}</span>}
                  {b.durationMs ? <span>{fmtTime(b.durationMs / 1000)}</span> : null}
                  {b.costUsd !== undefined ? <span>US$ {b.costUsd.toFixed(3)}</span> : null}
                  {b.tokens ? <span>{(b.tokens / 1000).toFixed(1)}k tokens</span> : null}
                </div>
              );
          }
        })}
      </div>
      <div className="composer">
        {!running && (
          <div className="chips">
            {quickActions(detail).map(([label, prompt]) => (
              <button key={label} className="chip" onClick={() => send(prompt)}>
                {label}
              </button>
            ))}
          </div>
        )}
        <div className="composer-box">
          <textarea
            rows={1}
            value={text}
            placeholder={running ? "O editor está trabalhando…" : "Peça uma edição: “deixa mais dinâmico”, “corta a parte do preço”…"}
            onChange={(e) => {
              setText(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(160, e.target.scrollHeight)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void send();
              }
            }}
          />
          {running ? (
            <button className="btn icon" title="Parar" onClick={() => window.ea.agent.stop(project)}>
              <Icon name="stop" size={14} />
            </button>
          ) : (
            <button className="btn primary icon" title="Enviar" disabled={!text.trim()} onClick={() => send()}>
              <Icon name="send" size={14} />
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
