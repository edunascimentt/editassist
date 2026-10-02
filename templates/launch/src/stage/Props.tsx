import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { C } from "../brand/palette";
import { rnd, spr } from "../kit/motion";
import type { ColorName } from "../types";

/** Calm background props: burst in with overshoot, then drift slowly. Keep density LOW:
 *  the energy belongs in the foreground. density 1 ≈ 10 props on a 1080p frame. */
export const Props: React.FC<{ seed: string; density?: number; colors?: ColorName[] }> = ({ seed, density = 1, colors = ["paper", "brand"] }) => {
  const f = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const n = Math.round(10 * density);
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      {Array.from({ length: n }, (_, i) => {
        const k = `${seed}-${i}`;
        const x = rnd(`${k}x`) * width;
        const y = rnd(`${k}y`) * height;
        const s = 16 + rnd(`${k}s`) * 46;
        const kind = Math.floor(rnd(`${k}k`) * 3);
        const p = spr(f, fps, Math.floor(rnd(`${k}d`) * 12));
        const dx = Math.sin(f / (90 + i * 7) + i) * 18;
        const dy = Math.cos(f / (110 + i * 5) + i) * 14;
        const col = C[colors[i % colors.length]];
        const style: React.CSSProperties = { position: "absolute", left: x + dx, top: y + dy, width: s, height: s, opacity: 0.55 * p,
          transform: `scale(${p}) rotate(${f * 0.4 + i * 30}deg)`, background: col };
        return <div key={i} style={{ ...style, borderRadius: kind === 0 ? s : kind === 1 ? s * 0.28 : 2,
          clipPath: kind === 2 ? "polygon(50% 0,61% 39%,100% 50%,61% 61%,50% 100%,39% 61%,0 50%,39% 39%)" : undefined }} />;
      })}
    </div>
  );
};
