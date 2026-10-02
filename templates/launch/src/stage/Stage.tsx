import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import beatsJson from "../beats.json";
import { C, onColor } from "../brand/palette";
import { Logo } from "../brand/Logo";
import { SCENES } from "../scenes";
import type { Beat } from "../types";
import { Props } from "./Props";
import { Title, accentOn } from "./Title";
import { ElasticWipe } from "./Wipe";

export const BEATS = beatsJson.beats as Beat[];
export const PICTURE_FRAMES = BEATS.reduce((m, b) => Math.max(m, b.from + b.duration), 0);

/** One beat, full frame: flood + props + scene (demo) or title (title beat). Local frame 0 = beat start. */
export const BeatView: React.FC<{ beat: Beat }> = ({ beat }) => {
  const Scene = beat.scene ? SCENES[beat.scene]?.Scene : undefined;
  const fg = onColor(beat.bg);
  const accent = accentOn(C[beat.bg], fg);
  return (
    <AbsoluteFill style={{ background: C[beat.bg] }}>
      <Props seed={beat.id} density={beat.kind === "demo" ? 0.5 : 1} />
      {Scene ? <Scene beat={beat} /> : null}
      {beat.kind === "title" && beat.title ? <Title lines={beat.title} at={0} color={fg} accent={accent} /> : null}
      {beat.kind === "demo" && beat.title && !Scene ? <Title lines={beat.title} at={0} color={fg} accent={accent} dockAt={30} /> : null}
      {beat.id === BEATS[BEATS.length - 1].id ? (
        <div style={{ position: "absolute", left: "50%", bottom: "16%", transform: "translateX(-50%)" }}><Logo size={140} /></div>
      ) : null}
    </AbsoluteFill>
  );
};

/** Plays beats.json: each beat enters through its transition over the tail of the previous one. */
export const Stage: React.FC = () => (
  <AbsoluteFill style={{ background: C[BEATS[0].bg] }}>
    {BEATS.map((b, i) => {
      const prev = BEATS[i - 1];
      return (
        <Sequence key={b.id} from={b.from} durationInFrames={b.duration} layout="none">
          {prev && b.transition ? (
            <ElasticWipe shape={b.transition.shape} duration={b.transition.duration ?? 12} glitch={b.transition.glitch !== false}
              from={<Sequence from={-(b.from - prev.from)} layout="none"><BeatView beat={prev} /></Sequence>}
              to={<BeatView beat={b} />} />
          ) : (
            <BeatView beat={b} />
          )}
        </Sequence>
      );
    })}
  </AbsoluteFill>
);
