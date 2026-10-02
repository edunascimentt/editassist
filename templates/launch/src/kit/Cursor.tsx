import React from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { C } from "../brand/palette";
import { clamp } from "./motion";

/** A keyframed path: the cursor travels between points; `click: true` squashes and rings. */
export type CursorKey = { at: number; x: number; y: number; click?: boolean };

const posAt = (keys: CursorKey[], f: number) => {
  if (f <= keys[0].at) return keys[0];
  for (let i = 1; i < keys.length; i++) {
    const a = keys[i - 1], b = keys[i];
    if (f <= b.at) {
      const t = interpolate(f, [a.at, b.at], [0, 1], { ...clamp, easing: Easing.bezier(0.65, 0, 0.35, 1) });
      return { at: f, x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
    }
  }
  return keys[keys.length - 1];
};

/** Big blob cursor with a smear trail, press squash and click ring.
 *  Rule: click on the EDGE of a button, never over its label. */
export const Cursor: React.FC<{ keys: CursorKey[]; size?: number; color?: string; appearAt?: number }> = ({
  keys, size = 44, color = C.ink, appearAt = keys[0]?.at ?? 0,
}) => {
  const f = useCurrentFrame();
  if (f < appearAt) return null;
  const p = posAt(keys, f);
  const clicks = keys.filter((k) => k.click);
  const squash = clicks.reduce((s, k) => s * (1 - 0.25 * Math.max(0, 1 - Math.abs(f - k.at) / 3)), 1);
  const trail = [1, 2, 3, 4, 5, 6].map((d) => ({ d, q: posAt(keys, f - d) }));
  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {trail.map(({ d, q }) => (
        <div key={d} style={{ position: "absolute", left: q.x - size / 2, top: q.y - size / 2, width: size, height: size,
          borderRadius: size, background: color, opacity: 0.16 * (1 - d / 7), transform: `scale(${1 - d * 0.08})` }} />
      ))}
      {clicks.map((k, i) => {
        const t = f - k.at;
        if (t < 0 || t > 14) return null;
        const r = interpolate(t, [0, 14], [size * 0.6, size * 2.2]);
        return <div key={i} style={{ position: "absolute", left: k.x - r / 2, top: k.y - r / 2, width: r, height: r, borderRadius: r,
          border: `4px solid ${C.brand}`, opacity: 1 - t / 14 }} />;
      })}
      <div style={{ position: "absolute", left: p.x - size / 2, top: p.y - size / 2, width: size, height: size, borderRadius: size,
        background: color, border: `4px solid ${C.paper}`, boxShadow: "0 6px 18px rgba(20,22,26,0.3)",
        transform: `scale(${squash}, ${2 - squash})` }} />
    </div>
  );
};

/** The click frames of a cursor path: use them as sound cues. */
export const clickFrames = (keys: CursorKey[]) => keys.filter((k) => k.click).map((k) => k.at);
