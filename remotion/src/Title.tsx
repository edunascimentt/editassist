import React from "react";
import { FONT } from "./fonts";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

export type TitleProps = { text: string; kicker?: string; accent?: string; y?: number }; // y: vertical centre, 0..1 of height

export const Title: React.FC<TitleProps> = ({ text, kicker, accent = "#FFE500", y }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const inn = spring({ frame, fps, config: { damping: 16 } });
  const out = interpolate(frame, [durationInFrames - fps * 0.4, durationInFrames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const u = Math.min(width, height) / 1080; // vertical frames scale by width, or text overflows
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: out,
                           ...(y === undefined ? {} : { transform: `translateY(${(y - 0.5) * 100}%)` }) }}>
      <div style={{ textAlign: "center", fontFamily: FONT, color: "white",
                    transform: `translateY(${interpolate(inn, [0, 1], [40 * u, 0])}px)`, opacity: inn,
                    textShadow: "0 4px 24px rgba(0,0,0,.55)" }}>
        {kicker ? <div style={{ color: accent, fontSize: 36 * u, letterSpacing: 6 * u, marginBottom: 12 * u }}>{kicker}</div> : null}
        <div style={{ fontSize: 110 * u, fontWeight: 900, lineHeight: 1 }}>{text}</div>
      </div>
    </AbsoluteFill>
  );
};
