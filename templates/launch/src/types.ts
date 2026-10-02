import paletteJson from "./brand/palette.json";

export type ColorName = keyof typeof paletteJson.colors;
export type Span = { t: string; accent?: boolean };
export type Shape = "circle" | "star" | "squircle" | "donut" | "diamond" | "blob" | "bloom";
export type Beat = {
  id: string;
  kind: "title" | "demo";
  from: number;
  duration: number;
  bg: ColorName;
  transition?: { shape: Shape; duration?: number; glitch?: boolean };
  title?: Span[][];
  scene?: string;
  notes?: string;
};
/** A sound the animation asks for, at a frame RELATIVE to the beat start (picture frames). */
export type Cue = { at: number; kind: SfxKind; gainDb?: number };
export type SfxKind = "pop" | "whoosh" | "glitch" | "click" | "key" | "blip" | "chime" | "swoosh" | "hit";
