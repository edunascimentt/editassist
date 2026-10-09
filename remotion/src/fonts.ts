import React from "react";
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

// A font the user owns (e.g. SF Pro Display, licence forbids bundling it): `ea motion` copies the file
// into assets/user-fonts/ (gitignored) and passes its public path; this loads it under its own family.
export const useUserFont = (file?: string, weight = "700"): string | undefined => {
  const family = file ? "User_" + file.replace(/[^A-Za-z0-9]/g, "_") : undefined;
  const [handle] = React.useState(() => (file ? delayRender("loading " + file) : null));
  React.useEffect(() => {
    if (!file || handle === null) return;
    new FontFace(family!, `url(${staticFile(file)})`, { weight })
      .load()
      .then((ff) => { document.fonts.add(ff); continueRender(handle); },
            () => continueRender(handle));
  }, [file, handle, family, weight]);
  return family;
};
