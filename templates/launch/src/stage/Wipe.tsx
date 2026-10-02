import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { ACCENT } from "../brand/palette";
import { clamp, spr } from "../kit/motion";
import type { Shape } from "../types";

/** Polar radius multiplier of each wipe shape at angle a (wobble animates the edge). */
const radius = (shape: Shape, a: number, wobble: number) => {
  const w = 1 + wobble * Math.sin(a * 6 + wobble * 40) * 0.6;
  switch (shape) {
    case "star": return (0.78 + 0.22 * Math.cos(5 * a)) * w;
    case "bloom": return (0.82 + 0.18 * Math.abs(Math.cos(4 * a))) * w;
    case "diamond": return (1 / (Math.abs(Math.cos(a)) + Math.abs(Math.sin(a)))) * w;
    case "squircle": return Math.pow(Math.pow(Math.abs(Math.cos(a)), 4) + Math.pow(Math.abs(Math.sin(a)), 4), -1 / 4) * w;
    case "blob": return (1 + 0.1 * Math.sin(3 * a + 1) + 0.06 * Math.sin(5 * a)) * w;
    default: return w; // circle, donut
  }
};

/** clip-path polygon for a shape of radius r (px) around the centre. */
export const shapeClip = (shape: Shape, r: number, W: number, H: number, wobble: number) => {
  const pts: string[] = [];
  for (let i = 0; i < 120; i++) {
    const a = (i / 120) * Math.PI * 2;
    const k = radius(shape, a, wobble) * r;
    pts.push(`${(W / 2 + Math.cos(a) * k).toFixed(1)}px ${(H / 2 + Math.sin(a) * k).toFixed(1)}px`);
  }
  return `polygon(${pts.join(",")})`;
};

/** Elastic wipe: the incoming scene grows from the centre inside `shape`, overshoots past full cover
 *  with a wobbling edge, the outgoing scene squashes away, the incoming lands with a bounce, and a
 *  short glitch (slice shift + colour split) punctuates the cover. */
export const ElasticWipe: React.FC<{ from: React.ReactNode; to: React.ReactNode; shape: Shape; duration: number; glitch?: boolean }> = ({
  from, to, shape, duration, glitch = true,
}) => {
  const f = useCurrentFrame();
  const { width: W, height: H, fps } = useVideoConfig();
  const cover = Math.hypot(W, H) / 2 / 0.75; // star/bloom valleys still cover the corners
  const p = spr(f, fps, 0, "bouncy");
  const done = f >= duration;
  const r = interpolate(p, [0, 1], [0, cover * 1.06]);
  const wobble = Math.max(0, 1 - f / duration) * 0.05;
  const out = interpolate(f, [0, duration * 0.7], [1, 0.9], clamp);
  const land = done ? 1 : interpolate(p, [0, 0.8, 1], [1.12, 0.98, 1], clamp);
  const g = glitch && f >= duration * 0.45 && f < duration * 0.45 + 3; // 3-frame glitch accent
  const toLayer = <div style={{ position: "absolute", inset: 0, transform: `scale(${land})` }}>{to}</div>;
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      {!done ? <div style={{ position: "absolute", inset: 0, transform: `scale(${out})`, filter: `brightness(${0.9 + out * 0.1})` }}>{from}</div> : null}
      <div style={{ position: "absolute", inset: 0, clipPath: done ? undefined : shape === "donut"
        ? `${shapeClip("circle", r, W, H, wobble)}` : shapeClip(shape, r, W, H, wobble) }}>
        {toLayer}
      </div>
      {g ? (
        <>
          {[0, 1, 2].map((i) => {
            const y0 = ((i * 31 + f * 17) % 78) / 100;
            const hgt = 0.05 + ((i * 13 + f * 7) % 9) / 100;
            const dx = (i % 2 ? -1 : 1) * (18 + i * 8);
            return (
              <div key={i} style={{ position: "absolute", inset: 0, clipPath: `inset(${y0 * 100}% 0 ${Math.max(0, 1 - y0 - hgt) * 100}% 0)`,
                transform: `translateX(${dx}px)`, filter: `drop-shadow(${-dx / 3}px 0 0 ${ACCENT})` }}>
                {toLayer}
              </div>
            );
          })}
        </>
      ) : null}
    </div>
  );
};
