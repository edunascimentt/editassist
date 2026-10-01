import React from "react";
import { FONT } from "./fonts";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

export type LowerThirdProps = { name: string; role?: string; accent?: string };

export const LowerThird: React.FC<LowerThirdProps> = ({ name, role, accent = "#FFE500" }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, height } = useVideoConfig();
  const inn = spring({ frame, fps, config: { damping: 18 } });
  const out = spring({ frame: frame - (durationInFrames - Math.round(fps * 0.6)), fps, config: { damping: 18 } });
  const p = inn - out;
  const u = height / 1080;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 96 * u, bottom: 120 * u, display: "flex", alignItems: "stretch",
                    transform: `translateX(${interpolate(p, [0, 1], [-60 * u, 0])}px)`, opacity: p }}>
        <div style={{ width: 10 * u, background: accent, marginRight: 20 * u }} />
        <div style={{ fontFamily: FONT, color: "white", textShadow: "0 2px 12px rgba(0,0,0,.6)" }}>
          <div style={{ fontSize: 54 * u, fontWeight: 800, lineHeight: 1.1 }}>{name}</div>
          {role ? <div style={{ fontSize: 32 * u, opacity: 0.85, marginTop: 6 * u }}>{role}</div> : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
