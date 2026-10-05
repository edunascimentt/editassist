// Bundles the Electron main process and the preload script. The agent SDKs stay external:
// they spawn their own native binaries from node_modules (unpacked from the asar, see
// electron-builder.yml).
import { build } from "esbuild";

const common = {
  bundle: true,
  platform: "node",
  target: "node22",
  sourcemap: true,
  external: ["electron", "@anthropic-ai/claude-agent-sdk", "@openai/codex-sdk"],
  logLevel: "info",
};

await build({ ...common, entryPoints: ["src/main/index.ts"], outfile: "dist/main/index.js", format: "cjs" });
await build({ ...common, entryPoints: ["src/preload/index.ts"], outfile: "dist/preload/index.js", format: "cjs" });
