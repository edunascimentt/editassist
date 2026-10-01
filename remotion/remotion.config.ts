import { Config } from "@remotion/cli/config";

// Share the repo's bundled fonts (assets/fonts) with the templates via staticFile().
Config.setPublicDir("../assets");
