import React from "react";
import { AbsoluteFill } from "remotion";
import { C } from "./brand/palette";
import { Browser, Notification, Phone } from "./kit/Frames";
import { Button, Pill, Toggle, TypeField } from "./kit/Controls";
import { Cursor } from "./kit/Cursor";
import { RollingNumber, Rows } from "./kit/Data";
import { Check, Panel, Toast } from "./kit/Feedback";

/** The bench: every kit piece animating in one 8-second flow. Build and judge the motion HERE
 *  before any scene. Once scenes start, freeze the kit (new needs are built inside the scene). */
export const Bench: React.FC = () => (
  <AbsoluteFill style={{ background: C.cream }}>
    <div style={{ position: "absolute", left: 60, top: 80 }}>
      <Browser at={0} width={1180} height={780}>
        <div style={{ position: "absolute", inset: 30, display: "flex", flexDirection: "column", gap: 24 }}>
          <div style={{ display: "flex", gap: 30, alignItems: "center" }}>
            <RollingNumber value={12500} prefix="$" at={20} />
            <Pill at={150} />
            <Toggle onAt={120} />
          </div>
          <TypeField label="Reason" text="Duplicate vendor payment" at={60} />
          <Rows at={30} rows={["Refund #4821", "Vendor payout", "Card limit"].map((t) => <span key={t} style={{ fontSize: 24, fontWeight: 700 }}>{t}</span>)} />
          <div><Button label="Request change" hoverAt={130} pressAt={140} doneAt={156} doneLabel="Request sent" /></div>
        </div>
        <Panel at={180} kind="drawer" width={420}><div style={{ fontSize: 30, fontWeight: 900 }}>Details</div></Panel>
      </Browser>
    </div>
    <div style={{ position: "absolute", right: 120, top: 90 }}>
      <Phone at={10} scale={0.95}>
        <Notification at={90} title="Approval needed" body="Refund of $12,500" scale={0.95} />
        <div style={{ position: "absolute", left: 0, right: 0, top: 320, display: "flex", justifyContent: "center" }}><Check at={200} size={140} /></div>
      </Phone>
    </div>
    <div style={{ position: "absolute", left: 420, top: 40 }}><Toast at={160} text="Request sent" outAt={215} /></div>
    <Cursor keys={[{ at: 100, x: 900, y: 900 }, { at: 134, x: 300, y: 640 }, { at: 140, x: 300, y: 640, click: true }, { at: 175, x: 700, y: 700 }]} />
  </AbsoluteFill>
);
