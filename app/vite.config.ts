import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  root: "src/renderer",
  base: "./",
  plugins: [
    react(),
    {
      // the React refresh preamble is an inline script: allow it in dev only
      name: "dev-csp",
      apply: "serve",
      transformIndexHtml: (html) => html.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'"),
    },
  ],
  build: { outDir: "../../dist/renderer", emptyOutDir: true },
  server: { port: 5217 }, // next free port if taken; dev.mjs reads the real URL
});
