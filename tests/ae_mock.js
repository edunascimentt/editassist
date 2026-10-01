// Minimal After Effects scripting mock: runs an editassist .jsx and reports what it built.
// Usage: node tests/ae_mock.js output/x.jsx  -> prints JSON summary, exits 1 on any error.
const fs = require("fs");
const log = { layers: [], keyframes: 0, texts: 0, comps: [] };
function prop(name) {
  const p = { name, value: null, keys: [],
    property: (n) => prop(n),
    setValue(v) { if (v === undefined || (Array.isArray(v) && v.some((x) => typeof x !== "number" || isNaN(x)))) throw new Error(`bad value for ${name}: ${v}`); p.value = v; },
    setValueAtTime(t, v) { if (typeof t !== "number" || isNaN(t)) throw new Error(`bad time for ${name}`); p.setValue(v); log.keyframes++; },
  };
  if (name === "ADBE Text Document") p.value = { fontSize: 0 };
  return p;
}
function layer(src) {
  const L = { name: "", startTime: 0, inPoint: 0, outPoint: 0, stretch: 100, enabled: true, audioEnabled: true,
    hasAudio: !!(src && src.hasAudio), hasVideo: !(src && src.audioOnly), source: src, props: {},
    property(n) { return (this.props[n] = this.props[n] || prop(n)); } };
  log.layers.push(L);
  return L;
}
global.File = function (p) { this.path = p; this.exists = fs.existsSync(p); };
global.ImportOptions = function (f) { this.file = f; };
global.ParagraphJustification = { CENTER_JUSTIFY: 1 };
global.alert = (m) => { throw new Error("alert: " + m); };
const items = { addFolder: (n) => ({ name: n }),
  addComp: (n, w, h, pa, d, fps) => { const comp = { name: n, w, h, d, fps,
      layers: { add: (it) => layer(it), addText: (t) => { log.texts++; return layer({ text: t }); } }, openInViewer() {} };
    log.comps.push({ n, w, h, d, fps }); return comp; } };
global.app = { project: { items, importFile: (io) => {
  const p = io.file.path; const audioOnly = /\.(wav|mp3|m4a|aac)$/i.test(p);
  return { name: p.split("/").pop(), width: audioOnly ? 0 : 1920, height: audioOnly ? 0 : 1080, hasAudio: true, audioOnly }; } },
  beginUndoGroup() {}, endUndoGroup() {} };
const src = fs.readFileSync(process.argv[2], "utf8").replace(/^﻿/, "");
eval(src);
for (const L of log.layers) {
  if (!(L.outPoint > L.inPoint)) throw new Error(`layer ${L.name} has out <= in`);
}
console.log(JSON.stringify({ comps: log.comps, layers: log.layers.length, keyframes: log.keyframes, texts: log.texts }));
