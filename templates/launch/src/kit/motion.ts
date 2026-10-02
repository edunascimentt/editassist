import { Easing, interpolate, random, spring } from "remotion";

/** Everything here is a pure function of the frame: same frame in, same picture out. */
export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** 0 → 1 spring starting at `at`, with overshoot (bouncy) or crisp (stiff). */
export const spr = (frame: number, fps: number, at = 0, kind: "bouncy" | "crisp" | "soft" = "bouncy") =>
  spring({
    frame: frame - at,
    fps,
    config: kind === "bouncy" ? { damping: 11, mass: 0.6, stiffness: 170 }
      : kind === "crisp" ? { damping: 20, mass: 0.5, stiffness: 260 }
      : { damping: 26, mass: 1, stiffness: 90 },
  });

/** Eased 0 → 1 between two frames. */
export const ease = (frame: number, a: number, b: number, e = Easing.bezier(0.22, 1, 0.36, 1)) =>
  interpolate(frame, [a, b], [0, 1], { ...clamp, easing: e });

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Squash on press: 1 → 0.9 → 1 over ~8 frames around `at`. */
export const press = (frame: number, at: number) =>
  1 - 0.1 * Math.max(0, 1 - Math.abs(frame - at - 2) / 4);

/** Characters typed so far: `cps` characters per second starting at `at`. */
export const typed = (text: string, frame: number, at: number, fps: number, cps = 18) =>
  text.slice(0, Math.max(0, Math.min(text.length, Math.floor(((frame - at) / fps) * cps))));

/** Frame at which typing `text` finishes (use it to schedule the next move and the key sounds). */
export const typedEnd = (text: string, at: number, fps: number, cps = 18) => at + Math.ceil((text.length / cps) * fps);

/** Deterministic pseudo-random in [0,1) for seeded layouts (sparkles, confetti). */
export const rnd = (seed: string | number) => random(String(seed));

/** Small idle float so held UI is never fully dead (amplitude in px). */
export const drift = (frame: number, seed: number, amp = 4) =>
  Math.sin(frame / 23 + seed * 1.7) * amp;
