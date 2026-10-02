import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { ACCENT, C } from "../brand/palette";
import { FONT } from "../brand/theme";
import { clamp, spr } from "../kit/motion";
import type { Span } from "../types";

export const WORD_GAP = 3; // frames between word pops (guide: 2-3)

/** Word-by-word pop with overshoot and a slight tilt. Sentence case, one accent span per line.
 *  dockAt: from that frame the title shrinks into a pinned caption chip at the top, so a UI demo
 *  never has a frame without readable text. */
export const Title: React.FC<{ lines: Span[][]; at?: number; color: string; size?: number; dockAt?: number; chipBg?: string; accent?: string }> = ({
  lines, at = 0, color, size, dockAt, chipBg = "rgba(255,255,255,0.92)", accent = ACCENT,
}) => {
  const f = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const base = size ?? Math.round(Math.min(width, height) * 0.1);
  const dock = dockAt !== undefined ? spr(f, fps, dockAt, "crisp") : 0;
  const scale = interpolate(dock, [0, 1], [1, 0.36], clamp);
  const top = interpolate(dock, [0, 1], [height / 2, height * 0.07], clamp);
  let w = 0;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, top, transform: `translateY(-50%) scale(${scale})`, transformOrigin: "50% 50%",
      display: "flex", justifyContent: "center", pointerEvents: "none" }}>
      <div style={{ textAlign: "center", fontFamily: FONT, fontWeight: 900, fontSize: base, lineHeight: 1.08, letterSpacing: "-0.03em",
        color, padding: dock > 0.01 ? `${base * 0.18}px ${base * 0.5}px` : 0, borderRadius: base * 0.4,
        background: dock > 0.01 ? chipBg : "transparent", boxShadow: dock > 0.5 ? "0 10px 40px rgba(20,22,26,0.12)" : "none" }}>
        {lines.map((line, li) => (
          <div key={li}>
            {line.flatMap((span, si) =>
              span.t.split(/(\s+)/).filter((x) => x.length).map((word, wi) => {
                if (/^\s+$/.test(word)) return <span key={`${si}-${wi}`}>{word}</span>;
                const start = at + w++ * WORD_GAP;
                const p = spr(f, fps, start);
                // overshoot lives mostly in the lift (y) so neighbours never collide; scale caps at +5%
                const sc = p > 1 ? 1 + (p - 1) * 0.35 : p;
                return (
                  <span key={`${si}-${wi}`} style={{ display: "inline-block", color: span.accent ? accent : color,
                    transform: `translateY(${(1 - p) * base * 0.5}px) scale(${sc}) rotate(${(1 - p) * -8}deg)`, opacity: Math.min(1, p * 3) }}>
                    {word}
                  </span>
                );
              }),
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

/** Accent colour readable on `bg`: the brand accent, unless the background IS the accent. */
export const accentOn = (bgHex: string, fg: string) =>
  bgHex.toLowerCase() === ACCENT.toLowerCase() ? (fg === C.paper ? C.ink : C.paper) : ACCENT;

/** Word count, for scheduling the next move and the pop sounds. */
export const wordCount = (lines: Span[][]) => lines.flat().reduce((n, s) => n + s.t.trim().split(/\s+/).filter(Boolean).length, 0);
