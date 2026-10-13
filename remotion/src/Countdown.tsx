import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { FONT, HAND } from "./fonts";

// "N days to go" teaser: a split-flap card hanging from a string drops in, rolls from `from` down to
// `to`, then a handwritten line writes itself under it. Opaque (paper background), made to be posted
// as is. Text marks: _words_ get a hand-drawn underline, (words) a hand-drawn circle.
export type CountdownProps = {
  kicker?: string;       // small word on the card, above the number ("FALTAM")
  from?: number;         // first number shown (the card rolls down from it)
  to: number;            // the number it lands on
  lines?: string[];      // handwritten text under the card
  paper?: string;        // background colour
  ink?: string;          // card, string and text colour
  digit?: string;        // number colour (default: the paper, as if cut out of the card)
  tag?: string;          // pill top-left
  symbol?: string;       // public path of an icon top-right (ea motion stages image files)
  logo?: string;         // public path of a logo bottom-right
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.45, 0, 0.2, 1);

// timing (seconds)
const DROP = 0.15, FLIP0 = 1.0, FAST = 0.13, PAUSE = 0.18, LAST = 0.42, WRITE = 2.45;

type Seg = { text: string; mark?: "under" | "circle" };
const parse = (line: string): Seg[] =>
  line.split(/(_[^_]+_|\([^)]+\))/).filter(Boolean).map((t) =>
    t.startsWith("_") ? { text: t.slice(1, -1), mark: "under" }
      : t.startsWith("(") ? { text: t.slice(1, -1), mark: "circle" } : { text: t });

// when the card shows which numbers: [start, end, a, b] flips in seconds
const flips = (from: number, to: number) => {
  const out: { t0: number; t1: number; a: number; b: number }[] = [];
  let t = FLIP0;
  const step = from > to ? -1 : 1;
  for (let n = from; n !== to; n += step) {
    const last = n + step === to;
    if (last) t += PAUSE;
    const d = last ? LAST : FAST;
    out.push({ t0: t, t1: t + d, a: n, b: n + step });
    t += d;
  }
  return out;
};

// Hand-drawn underline / loop around a word. Percent geometry (no viewBox), so the stroke keeps its
// width and the dash animation its length whatever the word's size.
const Mark: React.FC<{ kind: "under" | "circle"; p: number; ink: string; u: number }> = ({ kind, p, ink, u }) => {
  const stroke = { fill: "none", stroke: ink, strokeWidth: 5 * u, strokeLinecap: "round" as const, pathLength: 1, strokeDasharray: 1 };
  const a = Math.min(1, p * 1.25), b = Math.max(0, p * 1.25 - 0.25) / 1;
  return (
    <svg style={{ position: "absolute", overflow: "visible", left: 0, top: 0, width: "100%", height: "100%", pointerEvents: "none" }}>
      {kind === "under" ? (
        <>
          <line x1="-2%" y1="92%" x2="102%" y2="88%" {...stroke} strokeDashoffset={1 - a} />
          <line x1="8%" y1="99%" x2="88%" y2="97%" {...stroke} strokeWidth={3.5 * u} strokeDashoffset={1 - b} />
        </>
      ) : (
        <>
          <ellipse cx="50%" cy="56%" rx="55%" ry="50%" {...stroke} strokeDashoffset={1 - a}
                   style={{ transform: "rotate(-3deg)", transformOrigin: "50% 56%", transformBox: "fill-box" }} />
          <ellipse cx="50%" cy="54%" rx="53%" ry="46%" {...stroke} strokeWidth={3.5 * u} strokeDashoffset={1 - b * 0.35}
                   style={{ transform: "rotate(2deg)", transformOrigin: "50% 54%", transformBox: "fill-box" }} />
        </>
      )}
    </svg>
  );
};

export const Countdown: React.FC<CountdownProps> = ({
  kicker = "FALTAM", from, to, lines = [], paper = "#D1D5E0", ink = "#203055", digit, tag, symbol, logo,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const t = frame / fps;
  const u = width / 1080;
  const start = from ?? to + 6;
  const fl = flips(start, to);
  const landed = fl.length ? fl[fl.length - 1].t1 : FLIP0;
  const num = digit ?? paper;

  // card geometry
  const cw = 520 * u, ch = 800 * u, gap = 12 * u, r = 34 * u;
  const cardTop = height * 0.22;
  const cx = width / 2;

  // drop in on the string, then swing; the last flip kicks it again
  const drop = spring({ frame: frame - DROP * fps, fps, config: { damping: 11, stiffness: 90, mass: 0.9 } });
  const dy = interpolate(drop, [0, 1], [-cardTop - ch - 80 * u, 0]);
  const sw = (t0: number, amp: number) => (t < t0 ? 0 : amp * Math.sin((t - t0) * 5.2) * Math.exp(-(t - t0) * 1.6));
  const angle = sw(DROP + 0.35, 3.2) + sw(landed, -1.6);
  const bump = 1 + 0.035 * Math.sin(Math.PI * interpolate(t, [landed - 0.02, landed + 0.22], [0, 1], clamp));

  // which numbers are on which half right now
  const cur = fl.find((f) => t >= f.t0 && t < f.t1);
  const shown = t < (fl[0]?.t0 ?? 0) ? start : cur ? cur.a : to;
  const p = cur ? ease(interpolate(t, [cur.t0, cur.t1], [0, 1], clamp)) : 0;

  const face = (n: number) => (
    <div style={{ position: "absolute", left: 0, top: 0, width: cw, height: ch, display: "flex",
                  flexDirection: "column", alignItems: "center" }}>
      <div style={{ position: "absolute", top: 46 * u, width: "100%", textAlign: "center", fontFamily: FONT,
                    fontWeight: 700, fontSize: 50 * u, letterSpacing: 2 * u, color: "#FFFFFF" }}>{kicker}</div>
      <div style={{ position: "absolute", top: 66 * u, width: "100%", textAlign: "center", fontFamily: FONT,
                    fontWeight: 900, fontSize: 680 * u, lineHeight: `${ch - 66 * u}px`, color: num,
                    textShadow: `0 ${8 * u}px ${14 * u}px rgba(0,0,0,.28)` }}>{n}</div>
    </div>
  );
  const half = (n: number, top: boolean, style: React.CSSProperties = {}, shade = 0) => (
    <div style={{ position: "absolute", left: 0, top: top ? 0 : ch / 2 + gap / 2, width: cw, height: ch / 2 - gap / 2,
                  overflow: "hidden", background: ink, borderRadius: r, backfaceVisibility: "hidden", ...style }}>
      <div style={{ position: "absolute", left: 0, top: top ? 0 : -(ch / 2 + gap / 2), width: cw, height: ch }}>{face(n)}</div>
      {shade ? <div style={{ position: "absolute", inset: 0, background: `rgba(0,0,0,${shade})` }} /> : null}
    </div>
  );

  const card = cur ? (
    <>
      {half(cur.b, true)}
      {half(cur.a, false, {}, p > 0.5 ? 0.25 * (1 - p) * 2 : 0)}
      {p < 0.5
        ? half(cur.a, true, { transformOrigin: `50% ${ch / 2}px`, transform: `rotateX(${-180 * p}deg)` }, 0.45 * p * 2)
        : half(cur.b, false, { transformOrigin: `50% ${-gap / 2}px`, transform: `rotateX(${180 * (1 - p)}deg)` }, 0.45 * (1 - p) * 2)}
    </>
  ) : (<>{half(shown, true)}{half(shown, false)}</>);

  // handwriting writes on line by line; marks draw after their line
  const lineDur = 0.75;
  const fade = (a: number, b: number) => interpolate(t, [a, b], [0, 1], clamp);
  const push = interpolate(frame, [0, durationInFrames], [1, 1.035]);

  return (
    <AbsoluteFill style={{ background: paper, overflow: "hidden" }}>
      <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        <filter id="paper" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.55" numOctaves={4} seed={7} result="n" />
          <feDiffuseLighting in="n" lightingColor="#ffffff" surfaceScale={1.6} result="l">
            <feDistantLight azimuth={45} elevation={58} />
          </feDiffuseLighting>
          <feColorMatrix in="l" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -0.9 0 0 0 0.9" />
        </filter>
        <rect width="100%" height="100%" filter="url(#paper)" opacity={0.55} />
        <radialGradient id="vig" cx="50%" cy="45%" r="75%">
          <stop offset="60%" stopColor="#000" stopOpacity={0} />
          <stop offset="100%" stopColor="#000" stopOpacity={0.12} />
        </radialGradient>
        <rect width="100%" height="100%" fill="url(#vig)" />
      </svg>

      <AbsoluteFill style={{ transform: `scale(${push})` }}>
        {/* top bar */}
        <div style={{ position: "absolute", top: 130 * u, left: 80 * u, right: 80 * u, display: "flex",
                      justifyContent: "space-between", alignItems: "center", opacity: fade(0, 0.5),
                      transform: `translateY(${interpolate(fade(0, 0.6), [0, 1], [-20 * u, 0])}px)` }}>
          {tag ? <div style={{ border: `${3 * u}px solid ${ink}`, borderRadius: 999, padding: `${4 * u}px ${26 * u}px`,
                               fontFamily: HAND, fontWeight: 700, fontSize: 46 * u, color: ink }}>{tag}</div> : <div />}
          {symbol ? <Img src={staticFile(symbol)} style={{ height: 78 * u }} /> : null}
        </div>

        {/* string + card, swinging from the top edge */}
        <div style={{ position: "absolute", left: 0, top: 0, width, height, transformOrigin: `${cx}px 0px`,
                      transform: `rotate(${angle}deg)` }}>
          <div style={{ position: "absolute", left: cx - 4 * u, top: 0, width: 8 * u, height: cardTop + dy + 18 * u,
                        background: ink, borderRadius: 4 * u }} />
          <div style={{ position: "absolute", left: cx - cw / 2, top: cardTop + dy, width: cw, height: ch,
                        perspective: 4200 * u, transform: `scale(${bump})`,
                        filter: `drop-shadow(0 ${26 * u}px ${30 * u}px rgba(20,28,50,.28))` }}>
            {card}
          </div>
          <div style={{ position: "absolute", left: cx - 16 * u, top: cardTop + dy - 8 * u, width: 32 * u, height: 32 * u,
                        borderRadius: "50%", background: ink, boxShadow: `0 ${3 * u}px ${6 * u}px rgba(0,0,0,.3)` }} />
        </div>

        {/* handwriting */}
        <div style={{ position: "absolute", top: cardTop + ch + 90 * u, width: "100%", display: "flex",
                      flexDirection: "column", alignItems: "center", gap: 6 * u }}>
          {lines.map((line, i) => {
            const t0 = WRITE + i * (lineDur + 0.15);
            const reveal = interpolate(t, [t0, t0 + lineDur], [0, 112], { ...clamp, easing: Easing.inOut(Easing.quad) });
            const mark = ease(interpolate(t, [t0 + lineDur - 0.1, t0 + lineDur + 0.45], [0, 1], clamp));
            return (
              <div key={i} style={{ fontFamily: HAND, fontWeight: 500, fontSize: 112 * u, lineHeight: 1.12, color: ink,
                                    clipPath: `inset(-40% ${100 - reveal}% -40% -10%)`, whiteSpace: "nowrap" }}>
                {parse(line).map((s, j) => s.mark ? (
                  <span key={j} style={{ position: "relative", display: "inline-block", ...(s.mark === "circle" ? { margin: "0 0.12em 0 0.22em" } : {}) }}>
                    {s.text}
                    <Mark kind={s.mark} p={mark} ink={ink} u={u} />
                  </span>
                ) : <span key={j} style={{ whiteSpace: "pre" }}>{s.text}</span>)}
              </div>
            );
          })}
        </div>

        {/* footer: ornament line + logo */}
        <div style={{ position: "absolute", bottom: 150 * u, left: 80 * u, right: 80 * u, height: 90 * u,
                      display: "flex", alignItems: "center", gap: 30 * u }}>
          <div style={{ flex: 1, position: "relative", height: 12 * u }}>
            <div style={{ position: "absolute", left: 0, top: 0, width: 12 * u, height: 12 * u, background: ink,
                          transform: `rotate(45deg) scale(${fade(1.6, 1.9)})` }} />
            <div style={{ position: "absolute", left: 22 * u, top: 3 * u, height: 2 * u, background: ink,
                          width: `calc((100% - ${22 * u}px) * ${ease(fade(1.7, 2.5))})` }} />
            <div style={{ position: "absolute", left: 22 * u, top: 8 * u, height: 2 * u, background: ink, opacity: 0.6,
                          width: `calc((100% - ${22 * u}px) * ${ease(fade(1.8, 2.6))})` }} />
          </div>
          {logo ? <Img src={staticFile(logo)} style={{ height: 90 * u, opacity: fade(2.3, 2.8) }} /> : null}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
