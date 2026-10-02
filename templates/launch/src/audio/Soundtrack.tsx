import React from "react";
import { Audio, Sequence, staticFile, useVideoConfig } from "remotion";
import audio from "../audio.json";
import film from "../film.json";
import { SCENES } from "../scenes";
import { BEATS } from "../stage/Stage";
import { WORD_GAP, wordCount } from "../stage/Title";
import type { Cue, SfxKind } from "../types";

type Placed = { at: number; kind: SfxKind; gainDb: number };
const PRIORITY: SfxKind[] = ["hit", "whoosh", "click", "chime", "glitch", "pop", "blip", "key", "swoosh"];

/** Every sound the picture asks for, in PICTURE frames: stage (word pops, wipes) + scene cues. */
export const allCues = (): Placed[] => {
  const out: Placed[] = [];
  for (const b of BEATS) {
    if (b.transition && b.from > 0) {
      out.push({ at: b.from, kind: "whoosh", gainDb: -4 });
      if (b.transition.glitch !== false) out.push({ at: b.from + Math.round((b.transition.duration ?? 12) * 0.45), kind: "glitch", gainDb: -8 });
    }
    if (b.kind === "title" && b.title) {
      const n = wordCount(b.title);
      for (let i = 0; i < n; i++) out.push({ at: b.from + i * WORD_GAP, kind: "pop", gainDb: -10 });
    }
    const scene = b.scene ? SCENES[b.scene] : undefined;
    for (const c of scene?.cues ?? []) out.push({ at: b.from + c.at, kind: c.kind, gainDb: c.gainDb ?? 0 });
  }
  // no pile-ups: within 2 frames keep only the most important sound
  out.sort((a, b) => a.at - b.at || PRIORITY.indexOf(a.kind) - PRIORITY.indexOf(b.kind));
  const kept: Placed[] = [];
  for (const c of out) {
    const last = kept[kept.length - 1];
    if (last && c.at - last.at <= 2) {
      if (PRIORITY.indexOf(c.kind) < PRIORITY.indexOf(last.kind)) kept[kept.length - 1] = c;
      continue;
    }
    kept.push(c);
  }
  return kept;
};

const dbToGain = (db: number) => Math.pow(10, db / 20);

/** Audio at REAL speed, outside the slowed picture: cue frames are divided by `playback`. */
export const Soundtrack: React.FC = () => {
  const { fps } = useVideoConfig();
  const pb = film.playback || 1;
  const toOut = (pictureFrame: number) => Math.round(pictureFrame / pb);
  const sfx = audio.sfx as Record<string, string>;
  const vo = (audio.vo as { file: string; at: number; dur: number; gainDb?: number }[]) ?? [];
  const music = audio.music as null | { file: string; gainDb?: number; duckDb?: number; startAt?: number };
  const voRanges = vo.map((v) => [toOut(v.at), toOut(v.at) + Math.round(v.dur * fps)] as const);
  const duckAt = (f: number) => {
    const ramp = 6;
    let d = 0;
    for (const [a, b] of voRanges) d = Math.max(d, Math.min(1, (f - a + ramp) / ramp, (b + ramp - f) / ramp));
    return Math.max(0, d);
  };
  return (
    <>
      {music ? (
        <Sequence from={toOut(music.startAt ?? 0)} layout="none">
          <Audio src={staticFile(music.file)}
            volume={(f) => dbToGain((music.gainDb ?? 0) + duckAt(f + toOut(music.startAt ?? 0)) * (music.duckDb ?? -8))} />
        </Sequence>
      ) : null}
      {vo.map((v, i) => (
        <Sequence key={`vo${i}`} from={toOut(v.at)} layout="none">
          <Audio src={staticFile(v.file)} volume={dbToGain(v.gainDb ?? 0)} />
        </Sequence>
      ))}
      {allCues().filter((c) => sfx[c.kind]).map((c, i) => (
        <Sequence key={`s${i}`} from={toOut(c.at)} durationInFrames={Math.round(fps * 2)} layout="none">
          <Audio src={staticFile(sfx[c.kind])} volume={dbToGain(c.gainDb - 6)} />
        </Sequence>
      ))}
    </>
  );
};
