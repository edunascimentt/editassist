import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C } from "../brand/palette";
import { FONT, RADIUS } from "../brand/theme";
import { clamp, spr } from "./motion";

/** Browser window that rises in with overshoot and settles from a slight tilt. */
export const Browser: React.FC<{ at?: number; width?: number; height?: number; url?: string; children?: React.ReactNode; exitAt?: number }> = ({
  at = 0, width = 1440, height = 860, url = "app.product.com", children, exitAt,
}) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spr(f, fps, at);
  const out = exitAt !== undefined ? spr(f, fps, exitAt, "crisp") : 0;
  const y = interpolate(p, [0, 1], [380, 0]) + out * -60;
  const tilt = interpolate(p, [0, 1], [18, 0], clamp) + out * 8;
  return (
    <div style={{ width, height, transform: `perspective(2400px) translateY(${y}px) rotateX(${tilt}deg) scale(${1 - out * 0.06})`,
      opacity: Math.min(1, p * 1.4) * (1 - out), borderRadius: RADIUS.lg, background: C.paper, overflow: "hidden",
      boxShadow: "0 40px 120px rgba(20,22,26,0.18), 0 2px 0 rgba(20,22,26,0.04)", fontFamily: FONT, display: "flex", flexDirection: "column" }}>
      <div style={{ height: 56, display: "flex", alignItems: "center", gap: 10, padding: "0 22px", borderBottom: `2px solid ${C.line}` }}>
        {[C.danger, C.lemon, C.brand].map((c, i) => <div key={i} style={{ width: 14, height: 14, borderRadius: 7, background: c }} />)}
        <div style={{ marginLeft: 24, flex: 1, height: 32, borderRadius: 16, background: C.cream, color: C.muted, fontSize: 18,
          display: "flex", alignItems: "center", paddingLeft: 18 }}>{url}</div>
      </div>
      <div style={{ flex: 1, position: "relative" }}>{children}</div>
    </div>
  );
};

/** Phone with a 9:41 status bar; screen content as children. */
export const Phone: React.FC<{ at?: number; scale?: number; children?: React.ReactNode }> = ({ at = 0, scale = 1, children }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spr(f, fps, at);
  return (
    <div style={{ width: 430 * scale, height: 900 * scale, borderRadius: 64 * scale, background: C.ink, padding: 14 * scale,
      transform: `translateY(${interpolate(p, [0, 1], [500, 0])}px) rotate(${interpolate(p, [0, 1], [-8, 0])}deg)`,
      boxShadow: "0 50px 120px rgba(20,22,26,0.25)", fontFamily: FONT }}>
      <div style={{ width: "100%", height: "100%", borderRadius: 52 * scale, background: C.paper, overflow: "hidden", position: "relative" }}>
        <div style={{ height: 54 * scale, display: "flex", alignItems: "center", justifyContent: "space-between", padding: `0 ${34 * scale}px`,
          fontWeight: 700, fontSize: 20 * scale, color: C.ink }}>
          <span>9:41</span>
          <span style={{ width: 120 * scale, height: 32 * scale, borderRadius: 20 * scale, background: C.ink }} />
          <span>●●●</span>
        </div>
        <div style={{ position: "absolute", inset: `${54 * scale}px 0 0 0` }}>{children}</div>
      </div>
    </div>
  );
};

/** Notification banner that drops in with a jelly wobble. */
export const Notification: React.FC<{ at: number; title: string; body: string; scale?: number }> = ({ at, title, body, scale = 1 }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spr(f, fps, at);
  const jelly = 1 + Math.sin(Math.max(0, f - at) / 2.2) * 0.04 * Math.exp(-Math.max(0, f - at) / 8);
  return (
    <div style={{ position: "absolute", left: 14 * scale, right: 14 * scale, top: 8 * scale,
      transform: `translateY(${interpolate(p, [0, 1], [-160, 0])}px) scale(${jelly}, ${2 - jelly})`, opacity: Math.min(1, p * 2),
      background: "rgba(255,255,255,0.96)", borderRadius: 26 * scale, padding: 18 * scale, boxShadow: "0 16px 40px rgba(20,22,26,0.18)" }}>
      <div style={{ fontWeight: 800, fontSize: 20 * scale, color: C.ink }}>{title}</div>
      <div style={{ fontSize: 18 * scale, color: C.muted, marginTop: 4 }}>{body}</div>
    </div>
  );
};
