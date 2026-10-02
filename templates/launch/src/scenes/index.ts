import type React from "react";
import type { Beat, Cue } from "../types";
import * as Example from "./Example";

/** Scene registry: beats.json `scene` → component + its sound cues. Add one line per new scene. */
export const SCENES: Record<string, { Scene: React.FC<{ beat: Beat }>; cues: Cue[] }> = {
  Example,
};
