import { continueRender, delayRender, staticFile } from "remotion";

// Bundled Montserrat (assets/fonts, exposed as the public dir in remotion.config.ts).
const faces = [
  { family: "Montserrat", weight: "900", file: "fonts/Montserrat-Black.ttf" },
  { family: "Montserrat", weight: "700", file: "fonts/Montserrat-Bold.ttf" },
];

if (typeof window !== "undefined" && "FontFace" in window) {
  const handle = delayRender("loading fonts");
  Promise.all(
    faces.map((f) => new FontFace(f.family, `url(${staticFile(f.file)})`, { weight: f.weight }).load().then((ff) => {
      document.fonts.add(ff);
    })),
  ).then(() => continueRender(handle), () => continueRender(handle));
}

export const FONT = "Montserrat, Arial, sans-serif";
