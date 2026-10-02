import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C } from "../brand/palette";
import { FONT, RADIUS } from "../brand/theme";
import { clamp, ease, rnd, spr } from "./motion";

/** Number that rolls digit by digit and FINISHES before `at + dur` (never caught mid-roll on a hold). */
export const RollingNumber: React.FC<{ value: number; at: number; dur?: number; prefix?: string; suffix?: string; size?: number; decimals?: number }> = ({
  value, at, dur = 24, prefix = "", suffix = "", size = 64, decimals = 0,
}) => {
  const f = useCurrentFrame();
  const t = ease(f, at, at + dur);
  const v = value * t;
  const text = v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return (
    <span style={{ fontFamily: FONT, fontWeight: 900, fontSize: size, color: C.ink, fontVariantNumeric: "tabular-nums",
      display: "inline-block", transform: `translateY(${(1 - t) * 8}px)` }}>
      {prefix}{text}{suffix}
    </span>
  );
};

/** List rows that stagger in with a sparkle burst each. */
export const Rows: React.FC<{ rows: React.ReactNode[]; at: number; gap?: number; height?: number }> = ({ rows, at, gap = 4, height = 76 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {rows.map((r, i) => {
        const s = at + i * gap;
        const p = spr(f, fps, s);
        return (
          <div key={i} style={{ position: "relative", height, borderRadius: RADIUS.md, background: C.paper, border: `2px solid ${C.line}`,
            display: "flex", alignItems: "center", padding: "0 22px", fontFamily: FONT,
            transform: `translateX(${interpolate(p, [0, 1], [80, 0])}px)`, opacity: Math.min(1, p * 1.5) }}>
            {r}
            <Sparkles at={s + 2} x={18} y={height / 2} seed={i} count={5} />
          </div>
        );
      })}
    </div>
  );
};

export const Sparkles: React.FC<{ at: number; x: number; y: number; seed?: number; count?: number; color?: string }> = ({
  at, x, y, seed = 0, count = 6, color = C.brand,
}) => {
  const f = useCurrentFrame();
  const t = f - at;
  if (t < 0 || t > 16) return null;
  return (
    <>
      {Array.from({ length: count }, (_, i) => {
        const a = rnd(`${seed}-${i}`) * Math.PI * 2;
        const d = interpolate(t, [0, 16], [0, 30 + rnd(`d${seed}${i}`) * 30]);
        return <div key={i} style={{ position: "absolute", left: x + Math.cos(a) * d, top: y + Math.sin(a) * d, width: 8, height: 8,
          borderRadius: 2, background: color, opacity: 1 - t / 16, transform: `rotate(${45 + t * 10}deg)` }} />;
      })}
    </>
  );
};

export const StatCard: React.FC<{ label: string; value: number; at: number; prefix?: string; suffix?: string }> = ({ label, value, at, prefix, suffix }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spr(f, fps, at);
  return (
    <div style={{ padding: 26, borderRadius: RADIUS.lg, background: C.paper, border: `2px solid ${C.line}`, fontFamily: FONT,
      transform: `scale(${interpolate(p, [0, 1], [0.8, 1], clamp)})`, opacity: Math.min(1, p * 2) }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: C.muted }}>{label}</div>
      <RollingNumber value={value} at={at + 4} prefix={prefix} suffix={suffix} size={54} />
    </div>
  );
};
