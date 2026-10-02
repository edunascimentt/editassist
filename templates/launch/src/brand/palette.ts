import paletteJson from "./palette.json";
import type { ColorName } from "../types";

/** Only these colours may appear in the film. `ea launch audit` flags any other literal. */
export const C = paletteJson.colors as Record<ColorName, string>;
export const ACCENT = C[paletteJson.accent as ColorName];
export const TEXT = C[paletteJson.text as ColorName];

/** Is this background dark? Picks readable text automatically. */
export const isDark = (hex: string) => {
  const n = parseInt(hex.slice(1), 16);
  const l = (0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255;
  return l < 0.45;
};
export const onColor = (bg: ColorName) => (isDark(C[bg]) ? C.paper : TEXT);
