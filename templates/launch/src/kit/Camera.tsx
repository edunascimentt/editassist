import React from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { clamp } from "./motion";

/** Camera moves on keyframes: zoom and focus point (0..1 of the frame). The camera never rests:
 *  between keys it keeps a tiny push so held shots stay alive. */
export type CamKey = { at: number; zoom: number; x?: number; y?: number };

export const Camera: React.FC<{ keys: CamKey[]; drift?: number; children: React.ReactNode }> = ({ keys, drift = 0.012, children }) => {
  const f = useCurrentFrame();
  const at = keys.map((k) => k.at);
  const e = { ...clamp, easing: Easing.bezier(0.65, 0, 0.35, 1) };
  const zoom = keys.length > 1 ? interpolate(f, at, keys.map((k) => k.zoom), e) : keys[0]?.zoom ?? 1;
  const x = keys.length > 1 ? interpolate(f, at, keys.map((k) => k.x ?? 0.5), e) : keys[0]?.x ?? 0.5;
  const y = keys.length > 1 ? interpolate(f, at, keys.map((k) => k.y ?? 0.5), e) : keys[0]?.y ?? 0.5;
  const z = zoom * (1 + drift * Math.sin(f / 40));
  return (
    <div style={{ position: "absolute", inset: 0, transformOrigin: `${x * 100}% ${y * 100}%`, transform: `scale(${z})` }}>{children}</div>
  );
};
