import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C } from "../brand/palette";
import { FONT, RADIUS } from "../brand/theme";
import { clamp, press, spr, typed } from "./motion";

/** Button with hover (lift), press (squash) and an optional spinner until `doneAt`. */
export const Button: React.FC<{ label: string; hoverAt?: number; pressAt?: number; doneAt?: number; doneLabel?: string;
  tone?: "brand" | "ink" | "ghost"; size?: number }> = ({ label, hoverAt, pressAt, doneAt, doneLabel, tone = "brand", size = 26 }) => {
  const f = useCurrentFrame();
  const hover = hoverAt !== undefined ? interpolate(f, [hoverAt, hoverAt + 6], [0, 1], clamp) : 0;
  const s = pressAt !== undefined ? press(f, pressAt) : 1;
  const spinning = pressAt !== undefined && doneAt !== undefined && f >= pressAt + 4 && f < doneAt;
  const done = doneAt !== undefined && f >= doneAt;
  const bg = tone === "brand" ? C.brand : tone === "ink" ? C.ink : C.paper;
  const fg = tone === "ghost" ? C.ink : tone === "brand" ? C.ink : C.paper;
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 12, padding: `${size * 0.55}px ${size * 1.1}px`, borderRadius: RADIUS.md,
      background: bg, color: fg, fontFamily: FONT, fontWeight: 800, fontSize: size, border: tone === "ghost" ? `2px solid ${C.line}` : "none",
      transform: `translateY(${-hover * 4}px) scale(${s})`, boxShadow: `0 ${6 + hover * 8}px ${18 + hover * 14}px rgba(20,22,26,${0.12 + hover * 0.08})` }}>
      {spinning ? <Spinner size={size} color={fg} /> : null}
      {done && doneLabel ? doneLabel : label}
    </div>
  );
};

export const Spinner: React.FC<{ size?: number; color?: string }> = ({ size = 24, color = C.ink }) => {
  const f = useCurrentFrame();
  return <div style={{ width: size, height: size, borderRadius: size, border: `${size / 7}px solid ${color}33`, borderTopColor: color,
    transform: `rotate(${f * 18}deg)` }} />;
};

/** Field that types itself with a blinking caret. */
export const TypeField: React.FC<{ label?: string; text: string; at: number; cps?: number; width?: number; size?: number }> = ({
  label, text, at, cps = 18, width = 520, size = 26,
}) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const shown = typed(text, f, at, fps, cps);
  const active = f >= at - 4;
  const caret = active && Math.floor(f / 8) % 2 === 0;
  return (
    <div style={{ fontFamily: FONT, width }}>
      {label ? <div style={{ fontSize: size * 0.72, fontWeight: 700, color: C.muted, marginBottom: 8 }}>{label}</div> : null}
      <div style={{ height: size * 2.2, borderRadius: RADIUS.sm, border: `2px solid ${active ? C.brand : C.line}`, background: C.paper,
        display: "flex", alignItems: "center", padding: "0 18px", fontSize: size, fontWeight: 600, color: C.ink,
        boxShadow: active ? `0 0 0 6px ${C.mint}` : "none" }}>
        {shown}
        <span style={{ width: 3, height: size * 1.1, background: caret ? C.ink : "transparent", marginLeft: 2 }} />
      </div>
    </div>
  );
};

export const Toggle: React.FC<{ onAt: number; size?: number }> = ({ onAt, size = 34 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spr(f, fps, onAt, "crisp");
  return (
    <div style={{ width: size * 1.9, height: size, borderRadius: size, background: p > 0.5 ? C.brand : C.line, padding: 4, boxSizing: "border-box" }}>
      <div style={{ width: size - 8, height: size - 8, borderRadius: size, background: C.paper, transform: `translateX(${p * size * 0.9}px)`,
        boxShadow: "0 2px 6px rgba(20,22,26,0.2)" }} />
    </div>
  );
};

/** Status pill that morphs Pending → Approved (or any two states) at `at`. */
export const Pill: React.FC<{ at?: number; from?: string; to?: string; size?: number }> = ({ at, from = "Pending", to = "Approved", size = 20 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = at === undefined ? 0 : spr(f, fps, at, "bouncy");
  const on = p > 0.5;
  return (
    <span style={{ display: "inline-block", padding: `${size * 0.3}px ${size * 0.8}px`, borderRadius: size, fontFamily: FONT, fontWeight: 800,
      fontSize: size, background: on ? C.mint : C.lemon, color: on ? C.brandDark : C.ink, transform: `scale(${1 + Math.sin(p * Math.PI) * 0.15})` }}>
      {on ? to : from}
    </span>
  );
};
