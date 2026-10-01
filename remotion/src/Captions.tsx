import React from "react";
import { FONT } from "./fonts";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

type Word = { word: string; start: number; end: number };
type Line = { start: number; end: number; words: Word[] };

export type CaptionsProps = {
  lines: Line[];
  accent?: string;
  /** vertical centre of the caption, 0 = top, 1 = bottom */
  position?: number;
  uppercase?: boolean;
  fontFamily?: string;
};

// Word-by-word captions on a transparent background, timed on the edited timeline
// (work/captions.json, written by `ea subtitles`).
export const Captions: React.FC<CaptionsProps> = ({
  lines, accent = "#FFE500", position = 0.72, uppercase = true, fontFamily = FONT,
}) => {
  const frame = useCurrentFrame();
  const { fps, height, width } = useVideoConfig();
  const t = frame / fps;
  const line = lines.find((l) => t >= l.start && t < l.end);
  if (!line) return null;
  const enter = spring({ frame: frame - Math.round(line.start * fps), fps, config: { damping: 14, mass: 0.6 } });
  const size = Math.round(Math.min(width, height) * 0.075);
  return (
    <AbsoluteFill style={{ justifyContent: "flex-start", alignItems: "center" }}>
      <div
        style={{
          position: "absolute",
          top: `${position * 100}%`,
          transform: `translateY(-50%) scale(${interpolate(enter, [0, 1], [0.85, 1])})`,
          opacity: enter,
          width: "86%",
          textAlign: "center",
          fontFamily,
          fontWeight: 900,
          fontSize: size,
          lineHeight: 1.15,
          color: "white",
          WebkitTextStroke: `${Math.round(size / 9)}px black`,
          paintOrder: "stroke fill",
          textShadow: `0 ${size / 14}px ${size / 6}px rgba(0,0,0,0.45)`,
        }}
      >
        {line.words.map((w, i) => {
          const active = t >= w.start && t < (line.words[i + 1]?.start ?? line.end);
          return (
            <span key={i} style={{ color: active ? accent : "white", marginRight: "0.25em", display: "inline-block",
                                   transform: active ? "scale(1.08)" : "none" }}>
              {uppercase ? w.word.toUpperCase() : w.word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
