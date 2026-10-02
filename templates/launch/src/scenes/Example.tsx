import React from "react";
import { AbsoluteFill, useVideoConfig } from "remotion";
import { C, onColor } from "../brand/palette";
import { Browser } from "../kit/Frames";
import { Camera } from "../kit/Camera";
import { Button, Pill } from "../kit/Controls";
import { Cursor, clickFrames, type CursorKey } from "../kit/Cursor";
import { Rows, StatCard } from "../kit/Data";
import { Check, Toast } from "../kit/Feedback";
import { Title } from "../stage/Title";
import type { Beat, Cue } from "../types";

/** One demo scene. ALL timing lives in T, so the animation and its sounds can never drift apart.
 *  Density rule: something meaningful moves in every 8-frame window; 12+ distinct UI animations. */
const T = { title: 0, dock: 26, browser: 18, stats: 34, rows: 46, cursorIn: 70, click: 96, toast: 104, pill: 106, check: 116, push: 60 };

const cursor: CursorKey[] = [
  { at: T.cursorIn, x: 1500, y: 980 },
  { at: T.click - 6, x: 1404, y: 312 },
  { at: T.click, x: 1404, y: 312, click: true },
  { at: T.click + 20, x: 1640, y: 230 }, // park in empty space, never over a label
];

export const cues: Cue[] = [
  { at: T.browser, kind: "swoosh" },
  ...[0, 1, 2, 3].map((i) => ({ at: T.rows + i * 4, kind: "blip" as const, gainDb: -6 })),
  ...clickFrames(cursor).map((at) => ({ at, kind: "click" as const })),
  { at: T.toast, kind: "pop" },
  { at: T.check, kind: "chime" },
];

const row = (name: string, amount: string, at?: number) => (
  <div style={{ display: "flex", width: "100%", alignItems: "center", fontSize: 26, fontWeight: 700, color: C.ink }}>
    <span style={{ flex: 1 }}>{name}</span>
    <span style={{ width: 200, textAlign: "right", marginRight: 30 }}>{amount}</span>
    <Pill at={at} />
  </div>
);

export const Scene: React.FC<{ beat: Beat }> = ({ beat }) => {
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill>
      <Camera keys={[{ at: 0, zoom: 1.0 }, { at: T.push, zoom: 1.06, x: 0.62, y: 0.4 }, { at: T.check + 10, zoom: 1.12, x: 0.7, y: 0.35 }]}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", paddingTop: height * 0.08 }}>
          <Browser at={T.browser} width={width * 0.74} height={height * 0.72}>
            <div style={{ position: "absolute", inset: 36, display: "flex", gap: 30 }}>
              <div style={{ width: 360, display: "flex", flexDirection: "column", gap: 20 }}>
                <StatCard label="Pending" value={12} at={T.stats} />
                <StatCard label="Approved today" value={48250} prefix="$" at={T.stats + 6} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 18 }}>
                  <Button label="Approve all" hoverAt={T.click - 8} pressAt={T.click} doneAt={T.click + 10} doneLabel="Approved" />
                </div>
                <Rows at={T.rows} rows={[row("Refund #4821", "$12,500", T.pill), row("Vendor payout", "$3,200", T.pill + 4),
                  row("Card limit", "$900", T.pill + 8), row("Payroll run", "$48,000", T.pill + 12)]} />
              </div>
            </div>
          </Browser>
        </AbsoluteFill>
        <div style={{ position: "absolute", left: "50%", top: height * 0.16, transform: "translateX(-50%)" }}>
          <Toast at={T.toast} text="4 requests approved" outAt={T.check + 18} />
        </div>
        <div style={{ position: "absolute", right: width * 0.1, bottom: height * 0.1 }}><Check at={T.check} size={150} /></div>
        <Cursor keys={cursor} />
      </Camera>
      {beat.title ? <Title lines={beat.title} at={T.title} color={onColor(beat.bg)} dockAt={T.dock} /> : null}
    </AbsoluteFill>
  );
};
