import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C } from "../brand/palette";
import { FONT, RADIUS } from "../brand/theme";
import { clamp, rnd, spr } from "./motion";

/** Toast that drops in with a jelly and leaves at `outAt`. */
export const Toast: React.FC<{ at: number; text: string; outAt?: number }> = ({ at, text, outAt }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spr(f, fps, at) - (outAt !== undefined ? spr(f, fps, outAt, "crisp") : 0);
  if (p <= 0.001 && f > at) return null;
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 14, padding: "18px 28px", borderRadius: RADIUS.lg, background: C.ink,
      color: C.paper, fontFamily: FONT, fontWeight: 800, fontSize: 26, transform: `translateY(${(1 - p) * -90}px) scale(${0.9 + p * 0.1})`,
      opacity: Math.max(0, Math.min(1, p * 1.5)), boxShadow: "0 20px 50px rgba(20,22,26,0.3)" }}>
      <span style={{ width: 28, height: 28, borderRadius: 14, background: C.brand, display: "inline-block" }} />
      {text}
    </div>
  );
};

/** A check that draws itself, with a confetti burst. */
export const Check: React.FC<{ at: number; size?: number; confetti?: boolean }> = ({ at, size = 160, confetti = true }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const disc = spr(f, fps, at);
  const draw = interpolate(f, [at + 4, at + 16], [1, 0], clamp);
  const t = f - at;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} viewBox="0 0 100 100" style={{ transform: `scale(${disc})` }}>
        <circle cx="50" cy="50" r="46" fill={C.brand} />
        <path d="M28 52 L44 67 L73 36" fill="none" stroke={C.paper} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round"
          pathLength={1} strokeDasharray={1} strokeDashoffset={draw} />
      </svg>
      {confetti && t > 6 && t < 40
        ? Array.from({ length: 18 }, (_, i) => {
            const a = rnd(`c${i}`) * Math.PI * 2;
            const v = 4 + rnd(`v${i}`) * 6;
            const tt = t - 6;
            const colors = [C.brand, C.lemon, C.sky, C.blush];
            return <div key={i} style={{ position: "absolute", left: size / 2 + Math.cos(a) * v * tt, top: size / 2 + Math.sin(a) * v * tt + 0.15 * tt * tt,
              width: 12, height: 7, background: colors[i % 4], opacity: 1 - tt / 34, transform: `rotate(${tt * 20 + i * 30}deg)` }} />;
          })
        : null}
    </div>
  );
};

/** Modal / drawer panel that slides in from the right (drawer) or pops (modal). */
export const Panel: React.FC<{ at: number; kind?: "drawer" | "modal"; width?: number; children?: React.ReactNode }> = ({
  at, kind = "drawer", width = 560, children,
}) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spr(f, fps, at, kind === "drawer" ? "crisp" : "bouncy");
  const style: React.CSSProperties = kind === "drawer"
    ? { position: "absolute", top: 0, right: 0, bottom: 0, width, transform: `translateX(${(1 - p) * (width + 40)}px)` }
    : { position: "absolute", left: "50%", top: "50%", width, transform: `translate(-50%, -50%) scale(${0.85 + p * 0.15})`, opacity: Math.min(1, p * 2) };
  return <div style={{ ...style, background: C.paper, borderRadius: kind === "drawer" ? 0 : RADIUS.xl, padding: 36, boxSizing: "border-box",
    boxShadow: "-20px 0 60px rgba(20,22,26,0.15)", fontFamily: FONT }}>{children}</div>;
};
