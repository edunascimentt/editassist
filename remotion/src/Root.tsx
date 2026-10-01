import React from "react";
import { CalculateMetadataFunction, Composition } from "remotion";
import "./fonts";
import { Captions, CaptionsProps } from "./Captions";
import { LowerThird, LowerThirdProps } from "./LowerThird";
import { Title, TitleProps } from "./Title";

// Every composition takes width/height/fps/durationInSeconds from props, so the CLI can
// match the project timeline without editing code.
type Frame = { width?: number; height?: number; fps?: number; durationInSeconds?: number };

const meta: CalculateMetadataFunction<Frame & Record<string, unknown>> = ({ props }) => {
  const fps = props.fps ?? 30;
  return {
    fps,
    width: props.width ?? 1920,
    height: props.height ?? 1080,
    durationInFrames: Math.max(1, Math.round((props.durationInSeconds ?? 5) * fps)),
  };
};

export const Root: React.FC = () => (
  <>
    <Composition
      id="Captions"
      component={Captions as React.FC<any>}
      calculateMetadata={meta as any}
      durationInFrames={150}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{
        lines: [
          { start: 0, end: 1.6, words: [{ word: "Edit", start: 0, end: 0.4 }, { word: "assist", start: 0.4, end: 0.9 }, { word: "captions", start: 0.9, end: 1.6 }] },
        ],
        accent: "#FFE500",
        position: 0.72,
      } satisfies CaptionsProps & Frame}
    />
    <Composition
      id="LowerThird"
      component={LowerThird as React.FC<any>}
      calculateMetadata={meta as any}
      durationInFrames={150}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ name: "Name Surname", role: "Role / company", accent: "#FFE500" } satisfies LowerThirdProps & Frame}
    />
    <Composition
      id="Title"
      component={Title as React.FC<any>}
      calculateMetadata={meta as any}
      durationInFrames={90}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{ text: "Chapter title", kicker: "PART 1", accent: "#FFE500" } satisfies TitleProps & Frame}
    />
  </>
);
