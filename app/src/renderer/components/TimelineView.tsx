import { useMemo, useRef, useState, useEffect } from "react";
import type { Timeline } from "../../shared/types";
import { fmtTime } from "./ui";

const clipEnd = (c: { start: number; in: number; out: number; speed?: unknown }) => c.start + (c.out - c.in) / (Number(c.speed) || 1);

function clipClass(kind: string, name: string, index: number): string {
  if (kind === "audio") return /music|trilha|bed/i.test(name) || index > 0 ? "music" : "audio";
  return index > 0 ? "overlay" : "video";
}

/** Read-only view of timeline.json. The playhead follows the preview player when it shows a render of this timeline. */
export function TimelineView({
  timeline,
  playhead,
  onSeek,
}: {
  timeline: Timeline;
  playhead: number | null;
  onSeek?: (t: number) => void;
}) {
  const length = useMemo(() => Math.max(1, ...timeline.tracks.flatMap((t) => t.clips.map(clipEnd))), [timeline]);
  const body = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  useEffect(() => {
    const el = body.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(Math.max(200, el.clientWidth - 52 - 16)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const pps = width / length; // pixels per second
  const step = [1, 2, 5, 10, 15, 30, 60, 120, 300].find((s) => s * pps >= 60) ?? 600;
  const ticks = Array.from({ length: Math.floor(length / step) + 1 }, (_, i) => i * step);
  const tracks = [...timeline.tracks].sort((a, b) => (a.kind === b.kind ? 0 : a.kind === "video" ? -1 : 1));
  const counters: Record<string, number> = { video: 0, audio: 0 };

  return (
    <div className="timeline">
      <div className="tl-head">
        <b style={{ color: "var(--text)" }}>Timeline</b>
        <span>{fmtTime(length)}</span>
        <span>
          {timeline.width}×{timeline.height} · {timeline.fps} fps
        </span>
        <span>{tracks.reduce((n, t) => n + t.clips.length, 0)} clipes</span>
      </div>
      <div
        className="tl-body"
        ref={body}
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const x = e.clientX - rect.left - 52 + e.currentTarget.scrollLeft;
          if (x >= 0 && onSeek) onSeek(Math.min(length, x / pps));
        }}
      >
        <div className="tl-ruler" style={{ width }}>
          {ticks.map((t) => (
            <span key={t} style={{ left: t * pps }}>
              {fmtTime(t)}
            </span>
          ))}
        </div>
        {tracks.map((tr) => {
          const idx = counters[tr.kind]++;
          return (
            <div className="tl-track" key={`${tr.kind}-${tr.name}`}>
              <div className="tl-label">{tr.name}</div>
              <div className="tl-lane" style={{ width, flex: "none" }}>
                {tr.clips.map((c, i) => {
                  const left = c.start * pps;
                  const w = Math.max(2, (clipEnd(c) - c.start) * pps - 1);
                  const name = c.note || c.media.split("/").pop();
                  return (
                    <div
                      key={i}
                      className={`tl-clip ${clipClass(tr.kind, tr.name, idx)}`}
                      style={{ left, width: w }}
                      title={`${c.media}\n${fmtTime(c.in)}–${fmtTime(c.out)} na fonte · início ${c.start.toFixed(2)}s${c.note ? `\n${c.note}` : ""}`}
                    >
                      {w > 40 ? name : ""}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
        {(timeline.markers ?? []).map((m, i) => (
          <div key={i} className="tl-marker" style={{ left: 52 + m.time * pps }} title={m.note} />
        ))}
        {playhead !== null && <div className="tl-playhead" style={{ left: 52 + Math.min(length, playhead) * pps }} />}
      </div>
    </div>
  );
}
