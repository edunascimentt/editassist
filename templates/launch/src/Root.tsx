import React from "react";
import { AbsoluteFill, type CalculateMetadataFunction, Composition, Sequence } from "remotion";
import "./brand/theme";
import { Soundtrack } from "./audio/Soundtrack";
import { Bench } from "./Bench";
import film from "./film.json";
import { PICTURE_FRAMES, Stage } from "./stage/Stage";

type Size = { width?: number; height?: number };
const playback = film.playback || 1; // 2/3 = whole film 1.5x slower, animations untouched

/** Film: picture inside a slowed Sequence, audio OUTSIDE at real speed (or music drops in pitch). */
export const Film: React.FC<Size> = () => (
  <AbsoluteFill>
    <Sequence playbackRate={playback} layout="none">
      <Stage />
    </Sequence>
    <Soundtrack />
  </AbsoluteFill>
);

// width/height props render other formats (1080x1080, 1080x1350, 1080x1920) from the same film;
// scenes read useVideoConfig() so the layout reflows instead of cropping
const meta = (frames: number): CalculateMetadataFunction<Size> => ({ props }) => ({
  durationInFrames: frames,
  width: props.width ?? film.width,
  height: props.height ?? film.height,
  fps: film.fps,
});

export const Root: React.FC = () => (
  <>
    <Composition id="Film" component={Film} durationInFrames={Math.ceil(PICTURE_FRAMES / playback)} fps={film.fps}
      width={film.width} height={film.height} defaultProps={{}} calculateMetadata={meta(Math.ceil(PICTURE_FRAMES / playback))} />
    <Composition id="Bench" component={Bench} durationInFrames={film.fps * 8} fps={film.fps} width={film.width} height={film.height} />
  </>
);
