import { continueRender, delayRender, staticFile } from "remotion";
import film from "../film.json";

/** Brand font, loaded from public/fonts (`ea launch new --font` copies yours there). */
export const FONT = `${film.font}, Montserrat, Arial, sans-serif`;
export const RADIUS = { sm: 10, md: 16, lg: 24, xl: 36 };

const faces: { weight: string; file: string }[] = [
  { weight: "900", file: "fonts/Brand-Black.ttf" },
  { weight: "700", file: "fonts/Brand-Bold.ttf" },
];

if (typeof window !== "undefined" && "FontFace" in window) {
  const handle = delayRender("fonts");
  Promise.all(
    faces.map((f) =>
      new FontFace(film.font, `url(${staticFile(f.file)})`, { weight: f.weight }).load().then((ff) => document.fonts.add(ff)),
    ),
  ).then(() => continueRender(handle), () => continueRender(handle));
}
