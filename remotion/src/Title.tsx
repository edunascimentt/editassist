import React from "react";
import { FONT, useUserFont } from "./fonts";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

export type TitleProps = {
  text: string; kicker?: string; accent?: string;
  y?: number;          // vertical centre, 0..1 of height
  size?: number;       // title size in px at 1080 short side (default 110)
  maxWidth?: number;   // text block width, 0..1 of frame width (default 0.92): smaller = wider side margins
  upper?: boolean;     // ALL CAPS title
  fontFile?: string;   // public path of a user font (set by `ea motion --props '{"font": "<file>"}'`)
  weight?: number;     // title weight (default 900, or 700 with a user font)
};

export const Title: React.FC<TitleProps> = ({ text, kicker, accent = "#FFE500", y, size = 110, maxWidth = 0.92,
                                              upper = false, fontFile, weight }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const userFont = useUserFont(fontFile, String(weight ?? 700));
  const inn = spring({ frame, fps, config: { damping: 16 } });
  const out = interpolate(frame, [durationInFrames - fps * 0.4, durationInFrames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const u = Math.min(width, height) / 1080; // vertical frames scale by width, or text overflows
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: out,
                           ...(y === undefined ? {} : { transform: `translateY(${(y - 0.5) * 100}%)` }) }}>
      <div style={{ textAlign: "center", fontFamily: FONT, color: "white", maxWidth: width * maxWidth,
                    transform: `translateY(${interpolate(inn, [0, 1], [40 * u, 0])}px)`, opacity: inn,
                    textShadow: "0 4px 24px rgba(0,0,0,.55)" }}>
        {kicker ? <div style={{ color: accent, fontSize: 36 * u, letterSpacing: 6 * u, marginBottom: 12 * u }}>{kicker}</div> : null}
        <div style={{ fontSize: size * u, fontWeight: weight ?? (userFont ? 700 : 900), lineHeight: 1.02,
                      fontFamily: userFont ? `${userFont}, ${FONT}` : FONT,
                      textTransform: upper ? "uppercase" : "none", letterSpacing: upper ? 1 * u : 0 }}>{text}</div>
      </div>
    </AbsoluteFill>
  );
};
