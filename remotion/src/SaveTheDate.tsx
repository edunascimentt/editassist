import React from "react";
import { AbsoluteFill, continueRender, delayRender, Easing, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { FONT, SCRIPT, SERIF } from "./fonts";

// "Save the date" teaser: a month calendar on a grainy background. The script title writes itself,
// the month and the days cascade in, a soft highlight sweeps along the week and a solid dot lands on
// the day. Below, the weekday and the date. Opaque, made to be posted as is.
export type SaveTheDateProps = {
  day: number;           // the day to mark (1-31)
  month: number;         // 1-12
  year: number;
  title?: string;        // script title ("Save the date")
  eyebrow?: string;      // small caps line under the calendar (default: the weekday)
  line?: string;         // bold italic line under it (default: "dd/mm")
  paper?: string;        // background colour
  ink?: string;          // text colour
  symbol?: string;       // public path of an icon above the title (ea motion stages image files)
  logo?: string;         // public path of a logo at the bottom (tinted with `ink`)
};

const MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
  "outubro", "novembro", "dezembro"];
const WEEK = ["D", "S", "T", "Q", "Q", "S", "S"];
const WEEKDAYS = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.45, 0, 0.2, 1);
const out = Easing.bezier(0.16, 1, 0.3, 1);

// timing (seconds)
const TITLE = 0.25, GRID = 1.3, SWEEP = 2.9, LAND = 3.45, BOTTOM = 3.9;

// fade + rise in, starting at `at` seconds
const rise = (t: number, at: number, dur = 0.5, dist = 24) => {
  const p = interpolate(t, [at, at + dur], [0, 1], { ...clamp, easing: out });
  return { opacity: p, transform: `translateY(${(1 - p) * dist}px)` };
};

// An image used as a mask, so a one-colour logo or icon takes the ink colour.
const Tinted: React.FC<{ src: string; color: string; h: number; style?: React.CSSProperties }> = ({ src, color, h, style }) => {
  const [ratio, setRatio] = React.useState(1);
  const [handle] = React.useState(() => delayRender("measuring " + src));
  React.useEffect(() => {
    const img = new Image();
    img.onload = () => { setRatio(img.naturalWidth / img.naturalHeight || 1); continueRender(handle); };
    img.onerror = () => continueRender(handle);
    img.src = staticFile(src);
  }, [src, handle]);
  const mask = `url(${staticFile(src)}) center / contain no-repeat`;
  return <div style={{ height: h, width: h * ratio, background: color, WebkitMask: mask, mask, ...style }} />;
};

export const SaveTheDate: React.FC<SaveTheDateProps> = ({
  day, month, year, title = "Save the date", eyebrow, line, paper = "#203055", ink = "#D1D5E0", symbol, logo,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const u = width / 1080;

  const first = new Date(year, month - 1, 1).getDay();
  const days = new Date(year, month, 0).getDate();
  const weekday = new Date(year, month - 1, day).getDay();
  const cell = (n: number) => ({ col: (first + n - 1) % 7, row: Math.floor((first + n - 1) / 7) });
  const target = cell(day);

  // grid geometry (design units at 1080 wide)
  const colW = 112 * u, rowH = 102 * u;
  const gridW = colW * 7, gridL = (width - gridW) / 2;
  const top = height * 0.315;              // month label
  const weekY = top + 96 * u, rowsY = weekY + 100 * u;
  const cx = (col: number) => gridL + colW * (col + 0.5);
  const cy = (row: number) => rowsY + rowH * (row + 0.5);
  const rows = Math.ceil((first + days) / 7);

  // the soft highlight grows from the start of the target's week to the target, then the dot lands
  const sweepFrom = Math.max(0, target.col - 3);
  const sweep = interpolate(t, [SWEEP, LAND], [0, 1], { ...clamp, easing: ease });
  const sweepFade = interpolate(t, [LAND + 0.15, LAND + 0.9], [1, 0.5], clamp);
  const pill = 86 * u;
  const pillL = cx(sweepFrom) - pill / 2;
  const pillR = interpolate(sweep, [0, 1], [cx(sweepFrom) + pill / 2, cx(target.col) + pill / 2]);
  const dot = spring({ frame: frame - LAND * fps, fps, config: { damping: 11, stiffness: 170, mass: 0.7 } });
  const ring = interpolate(t, [LAND, LAND + 0.8], [0, 1], clamp);

  const push = interpolate(t, [0, 8], [1, 1.04], { extrapolateRight: "clamp" });
  const titleReveal = interpolate(t, [TITLE, TITLE + 1.3], [0, 108], { ...clamp, easing: ease });
  const grain = Math.floor(frame / 2) % 24;

  return (
    <AbsoluteFill style={{ background: paper, overflow: "hidden" }}>
      <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        <radialGradient id="glow" cx="50%" cy="42%" r="70%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity={0.07} />
          <stop offset="65%" stopColor="#000000" stopOpacity={0} />
          <stop offset="100%" stopColor="#000000" stopOpacity={0.3} />
        </radialGradient>
        <rect width="100%" height="100%" fill="url(#glow)" />
      </svg>

      <AbsoluteFill style={{ transform: `scale(${push})` }}>
        {symbol && (
          <div style={{ position: "absolute", top: height * 0.12, width: "100%", display: "flex", justifyContent: "center",
                        ...rise(t, 0.05, 0.6) }}>
            <Tinted src={symbol} color={ink} h={74 * u} />
          </div>
        )}

        <div style={{ position: "absolute", top: height * 0.165, width: "100%", textAlign: "center" }}>
          <div style={{ display: "inline-block", fontFamily: SCRIPT, fontSize: 168 * u, color: ink, lineHeight: 1.25,
                        whiteSpace: "nowrap", padding: `0 ${0.12}em`,
                        WebkitMaskImage: `linear-gradient(90deg, #000 ${titleReveal - 8}%, transparent ${titleReveal}%)` }}>
            {title}
          </div>
        </div>

        <div style={{ position: "absolute", left: gridL + colW * 0.5 - 30 * u, top, fontFamily: FONT, fontWeight: 700,
                      fontSize: 44 * u, color: ink, ...rise(t, GRID - 0.25) }}>
          {MONTHS[month - 1]} {year}
        </div>

        {WEEK.map((w, i) => (
          <div key={"w" + i} style={{ position: "absolute", left: cx(i) - colW / 2, width: colW, top: weekY, textAlign: "center",
                                      fontFamily: FONT, fontWeight: 600, fontSize: 40 * u, color: ink,
                                      ...rise(t, GRID - 0.1 + i * 0.03, 0.4, 14) }}>
            {w}
          </div>
        ))}

        <div style={{ position: "absolute", left: pillL, width: Math.max(pill, pillR - pillL), top: cy(target.row) - pill / 2,
                      height: pill, borderRadius: pill / 2, background: ink,
                      opacity: sweep > 0 ? 0.26 * sweepFade : 0 }} />

        <div style={{ position: "absolute", left: cx(target.col) - pill / 2, top: cy(target.row) - pill / 2, width: pill,
                      height: pill, borderRadius: "50%", border: `${3 * u}px solid ${ink}`,
                      transform: `scale(${1 + ring * 0.9})`, opacity: (1 - ring) * 0.7 * (t >= LAND ? 1 : 0) }} />
        <div style={{ position: "absolute", left: cx(target.col) - pill / 2, top: cy(target.row) - pill / 2, width: pill,
                      height: pill, borderRadius: "50%", background: ink, transform: `scale(${dot})`,
                      boxShadow: `0 0 ${40 * u}px rgba(255,255,255,${0.18 * dot})` }} />

        {Array.from({ length: days }, (_, k) => {
          const n = k + 1;
          const c = cell(n);
          const hit = n === day;
          const on = hit && dot > 0.5;
          return (
            <div key={n} style={{ position: "absolute", left: cx(c.col) - colW / 2, width: colW, top: cy(c.row) - rowH / 2,
                                  height: rowH, display: "flex", alignItems: "center", justifyContent: "center",
                                  fontFamily: FONT, fontWeight: on ? 800 : 400, fontSize: (on ? 44 : 40) * u,
                                  color: on ? paper : ink, ...rise(t, GRID + 0.12 + (c.row * 7 + c.col - first) * 0.022, 0.45, 18) }}>
              {n}
            </div>
          );
        })}

        <div style={{ position: "absolute", top: cy(rows - 1) + rowH * 1.35, width: "100%", textAlign: "center" }}>
          <div style={{ display: "inline-block", position: "relative", fontFamily: SERIF, fontWeight: 500, fontSize: 50 * u,
                        letterSpacing: 4 * u, color: ink, ...rise(t, BOTTOM, 0.6) }}>
            <div style={{ position: "absolute", left: -10 * u, right: -10 * u, top: "52%", height: "42%", background: ink,
                          opacity: 0.16, filter: `blur(${5 * u}px)`, borderRadius: 8 * u,
                          transform: `scaleX(${interpolate(t, [BOTTOM + 0.2, BOTTOM + 0.8], [0, 1], { ...clamp, easing: ease })})`,
                          transformOrigin: "0 50%" }} />
            <span style={{ position: "relative" }}>{(eyebrow ?? WEEKDAYS[weekday]).toUpperCase()}</span>
          </div>
          <div style={{ fontFamily: FONT, fontStyle: "italic", fontWeight: 800, fontSize: 128 * u, color: ink, lineHeight: 1.05,
                        marginTop: 6 * u, ...rise(t, BOTTOM + 0.25, 0.6, 34) }}>
            {line ?? `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}`}
          </div>
        </div>

        {logo && (
          <div style={{ position: "absolute", bottom: height * 0.075, width: "100%", display: "flex", justifyContent: "center",
                        ...rise(t, BOTTOM + 0.7, 0.6) }}>
            <Tinted src={logo} color={ink} h={84 * u} />
          </div>
        )}
      </AbsoluteFill>

      <svg width={width} height={height} style={{ position: "absolute", inset: 0, mixBlendMode: "soft-light", opacity: 0.7 }}>
        <filter id="grain" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency={0.9 / u} numOctaves={2} seed={grain} />
          <feColorMatrix type="saturate" values="0" />
          <feComponentTransfer>
            <feFuncR type="linear" slope={3.2} intercept={-1.1} />
            <feFuncG type="linear" slope={3.2} intercept={-1.1} />
            <feFuncB type="linear" slope={3.2} intercept={-1.1} />
          </feComponentTransfer>
        </filter>
        <rect width="100%" height="100%" filter="url(#grain)" />
      </svg>
    </AbsoluteFill>
  );
};
