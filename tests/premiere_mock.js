// Minimal fake of Premiere's UXP `premierepro` module, enough to run lib.js ops under Node.
// Usage: node premiere_mock.js <lib.js> <op> <args.json>  -> prints {result, state} as JSON.
// It models what lib.js relies on: bins, importFiles, sequences from a .sqpreset (track counts),
// overwrite edits from a project item's in/out, trims, removals, components, transitions, markers, offline items, ripple with linked halves.
"use strict";
const fs = require("fs");

const TPS = 254016000000;
class TickTime {
  constructor(ticks) { this._t = BigInt(ticks); }
  get ticks() { return this._t.toString(); }
  get ticksNumber() { return Number(this._t); }
  get seconds() { return Number(this._t) / TPS; }
  add(o) { return new TickTime(this._t + o._t); }
  subtract(o) { return new TickTime(this._t - o._t); }
  equals(o) { return this._t === o._t; }
}
TickTime.createWithSeconds = (s) => new TickTime(Math.round(s * TPS));
TickTime.createWithTicks = (t) => new TickTime(t);
TickTime.TIME_ZERO = new TickTime(0);

const state = { imported: [], transactions: [], sequences: [], log: [] };
let active = null;

class PointF { constructor(x, y) { this.x = x; this.y = y; } }
class Color { constructor(r, g, b, a) { this.red = r; this.green = g; this.blue = b; this.alpha = a; } }

class Param {
  constructor(name, value) { this.displayName = name; this.value = value; this.varying = false; this.keys = []; }
  createKeyframe(v) { return { value: v, position: TickTime.TIME_ZERO }; }
  // 26.3 shape: Keyframe {value: {value: x}}; points come back as [x, y]
  async getStartValue() {
    const v = this.value instanceof PointF ? [this.value.x, this.value.y] : this.value;
    return { value: { value: v }, position: TickTime.TIME_ZERO };
  }
  isTimeVarying() { return this.varying; }
  createSetTimeVaryingAction(on) { return () => { this.varying = on; }; }
  createSetValueAction(kf) { return () => { this.value = kf.value; }; }
  createAddKeyframeAction(kf) { return () => { this.keys.push([kf.position.seconds, kf.value]); }; }
}
class Component {
  constructor(matchName, name, params) { this.matchName = matchName; this.name = name; this.params = params; }
  async getMatchName() { return this.matchName; }
  async getDisplayName() { return this.name; }
  getParamCount() { return this.params.length; }
  getParam(i) { return this.params[i]; }
}
class Chain {
  constructor(kind) {
    this.list = kind === "video"
      ? [new Component("AE.ADBE Opacity", "Opacity", [new Param("Opacity", 100)]),
         new Component("AE.ADBE Motion", "Motion", [new Param("Position", new PointF(0.5, 0.5)), new Param("Scale", 100)])]
      : [new Component("AE.ADBE Volume", "Volume", [new Param("Level", 0.1778)])];
  }
  getComponentCount() { return this.list.length; }
  getComponentAtIndex(i) { return this.list[i]; }
  createAppendComponentAction(c) { return () => { this.list.push(c); }; }
  createRemoveComponentAction(c) { return () => { this.list = this.list.filter((x) => x !== c); }; }
}

class ProjectItem {
  constructor(name, path, isBin) {
    this.name = name; this.path = path; this.bin = isBin; this.children = []; this.inT = null; this.outT = null;
    this.isAudioOnly = /\.(wav|mp3|aac|m4a)$/i.test(path || "");
    this.offline = false;
  }
  getId() { return this.name; }
  async getItems() { if (!this.bin) throw new Error("not a bin"); return this.children; }
  async getMediaFilePath() { return this.path; }
  // like 26.3: an item whose file vanished stays offline after the file comes back, until relinked
  async isOffline() { return this.offline; }
  async refreshMedia() { return true; }
  async changeMediaFilePath(p) { if (!fs.existsSync(p)) return false; this.path = p; this.offline = false; return true; }
  createSetInOutPointsAction(a, b) { return () => { this.inT = a; this.outT = b; }; }
  createSetInputLUTIDAction(id) { return () => { this.lut = id; }; }
  createBinAction(name) { return () => { this.children.push(new ProjectItem(name, null, true)); }; }
  createMoveItemAction(item, bin) { return () => { bin.children.push(item); }; }
}

class TrackItem {
  constructor(pi, kind, start, end, inT) { this.pi = pi; this.kind = kind; this.start = start; this.end = end; this.inT = inT; this.disabled = false; this.chain = new Chain(kind); this.transitions = []; this.trackIndex = 0; }
  async getName() { return this.pi.name; }
  async getStartTime() { return this.start; }
  async getEndTime() { return this.end; }
  async getInPoint() { return this.inT; }
  async getOutPoint() { return this.inT.add(this.end.subtract(this.start)); }
  async isDisabled() { return this.disabled; }
  async getSpeed() { return 1; }
  async getProjectItem() { return this.pi; }
  async getComponentChain() { return this.chain; }
  async getTrackIndex() { return this.trackIndex; }
  async getMediaType() { return this.kind === "audio" ? 3 : 2; }
  createSetEndAction(t) { return () => { this.end = t; }; }
  createSetStartAction(t) { return () => { this.start = t; }; }
  createSetInPointAction(t) { return () => { this.inT = t; }; }
  createSetOutPointAction() { return () => {}; }
  createMoveAction(d) { return () => { this.start = this.start.add(d); this.end = this.end.add(d); }; }
  createSetDisabledAction(d) { return () => { this.disabled = d; }; }
  createSetNameAction() { return () => {}; }
  createAddVideoTransitionAction(tr, opts) { return () => { this.transitions.push({ name: tr.name, ...(opts || {}).o }); }; }
}

class Track {
  constructor(kind, i) { this.kind = kind; this.index = i; this.items = []; this.name = `${kind === "video" ? "V" : "A"}${i + 1}`; }
  getTrackItems() { return this.items.slice(); }
  async isMuted() { return false; }
  // overwrite: anything under [start, end) is cut away
  overwrite(item) {
    const a = Number(item.start.ticks), b = Number(item.end.ticks);
    this.items = this.items.filter((x) => Number(x.end.ticks) <= a || Number(x.start.ticks) >= b);
    item.trackIndex = this.index;
    this.items.push(item);
  }
}

class Sequence {
  constructor(name, nv, na, preset) {
    this.name = name; this.guid = `guid-${name}`; this.preset = preset;
    this.video = Array.from({ length: nv }, (_, i) => new Track("video", i));
    this.audio = Array.from({ length: na }, (_, i) => new Track("audio", i));
    this.markers = []; this.playhead = TickTime.TIME_ZERO; this.projectItem = new ProjectItem(name, null, false);
    this.captionTracks = 0;
  }
  async getVideoTrackCount() { return this.video.length; }
  async getAudioTrackCount() { return this.audio.length; }
  async getCaptionTrackCount() { return this.captionTracks; }
  async getVideoTrack(i) { return this.video[i]; }
  async getAudioTrack(i) { return this.audio[i]; }
  async getProjectItem() { return this.projectItem; }
  async getEndTime() {
    let e = 0;
    for (const t of this.video.concat(this.audio)) for (const it of t.items) e = Math.max(e, Number(it.end.ticks));
    return new TickTime(e);
  }
  async setPlayerPosition(t) { this.playhead = t; return true; }
  async getPlayerPosition() { return this.playhead; }
  async getTimebase() { return String(Math.round(TPS / (this.fps || 30))); }
  async getInPoint() { return TickTime.TIME_ZERO; }
  async getOutPoint() { return TickTime.TIME_ZERO; }
  async getSelection() {
    if (!this.sel) this.sel = { items: [], addItem(it) { this.items.push(it); return true; }, getTrackItems: async () => this.sel.items };
    return this.sel;
  }
  async clearSelection() { if (this.sel) this.sel.items = []; return true; }
  setSelection() { return true; }
  async getFrameSize() { return { width: this.width || 1920, height: this.height || 1080 }; }
}

const root = new ProjectItem("root", null, true);
const project = {
  name: "Mock.prproj", path: "/tmp/Mock.prproj",
  async getRootItem() { return root; },
  async getActiveSequence() { return active; },
  async setActiveSequence(s) { active = s; return true; },
  async openSequence() { return true; },
  async getSequences() { return state.sequences; },
  async importFiles(paths, suppress, bin) {
    const target = bin || root;
    for (const p of paths) {
      if (!fs.existsSync(p)) return false;
      target.children.push(new ProjectItem(p.split(/[\\/]/).pop(), p, false));
      state.imported.push(p);
    }
    return true;
  },
  async createSequence(name, preset) {
    const xml = preset ? fs.readFileSync(preset, "utf8") : "";
    const nv = Number((/<InitialNumberOfVideoTracks>(\d+)/.exec(xml) || [0, 3])[1]);
    const na = ((/<AudioTracks>(.*)<\/AudioTracks>/.exec(xml) || [0, "[{},{},{}]"])[1].match(/mTrackID/g) || [1, 2, 3]).length;
    const s = new Sequence(name, nv, na, preset);
    const size = /<VideoFrameSize>0,0,(\d+),(\d+)/.exec(xml);
    if (size) { s.width = Number(size[1]); s.height = Number(size[2]); }
    const tpf = /<VideoFrameRate>(\d+)/.exec(xml);
    if (tpf) s.fps = TPS / Number(tpf[1]);
    state.sequences.push(s);
    return s;
  },
  async save() { state.saved = true; return true; },
  lockedAccess(cb) { cb(); },
  executeTransaction(cb, label) {
    const actions = [];
    cb({ addAction: (a) => { actions.push(a); return true; } });
    for (const a of actions) a();
    state.transactions.push(label);
    return true;
  },
};

const ppro = {
  TickTime, PointF, Color,
  Constants: { TrackItemType: { CLIP: 1 }, MediaType: { ANY: 0, DATA: 1, VIDEO: 2, AUDIO: 3 },
               TransitionPosition: { START: 0, END: 1 }, ExportType: { QUEUE_TO_AME: 0, QUEUE_TO_APP: 1, IMMEDIATELY: 2 } },
  Project: { getActiveProject: async () => project },
  ClipProjectItem: { cast: (pi) => (pi && !pi.bin ? pi : null) },
  FolderItem: { cast: (pi) => (pi && pi.bin ? pi : null) },
  ProjectItem: { cast: (pi) => pi },
  SequenceEditor: {
    getEditor: (seq) => ({
      createOverwriteItemAction(pi, at, v, a) {
        return () => {
          if (/\.srt$/i.test(pi.path)) return;  // 26.3: placing an .srt item succeeds and adds nothing
          const inT = pi.inT || TickTime.TIME_ZERO;
          const len = pi.outT ? pi.outT.subtract(inT) : TickTime.createWithSeconds(5);
          const end = at.add(len).add(TickTime.createWithSeconds(1 / 30));  // Premiere's out point is inclusive
          if (!pi.isAudioOnly) seq.video[v].overwrite(new TrackItem(pi, "video", at, end, inT));
          if (!/\.(png|jpg)$/i.test(pi.path)) seq.audio[a].overwrite(new TrackItem(pi, "audio", at, end, inT));
        };
      },
      createRemoveItemsAction(sel, ripple) {
        if (sel.dead) throw new Error("The script object is no longer valid.");
        return () => {
          const all = seq.video.concat(seq.audio);
          const key = (it) => `${it.start.ticks}|${it.end.ticks}|${it.pi.path}`;
          for (const it of sel.items) for (const t of all) t.items = t.items.filter((x) => x !== it);
          state.removed = (state.removed || 0) + sel.items.length;
          // like 26.3: a ripple closes the gap only when no linked half (same media, start, end) stays behind
          const keys = new Set(sel.items.map(key));
          const left = all.some((t) => t.items.some((x) => keys.has(key(x))));
          if (!ripple || left) return;
          for (const it of sel.items) {
            const len = it.end.subtract(it.start);
            const track = it.kind === "video" ? seq.video[it.trackIndex] : seq.audio[it.trackIndex];
            for (const x of track.items) if (Number(x.start.ticks) >= Number(it.end.ticks)) { x.start = x.start.subtract(len); x.end = x.end.subtract(len); }
          }
        };
      },
    }),
  },
  // like 26.3: the selection handed to the callback dies when the callback returns
  TrackItemSelection: { createEmptySelection: (cb) => { const sel = { items: [], dead: false, addItem(it) { if (this.dead) throw new Error("The script object is no longer valid."); this.items.push(it); return true; } }; cb(sel); sel.dead = true; return true; } },
  TransitionFactory: {
    getVideoTransitionMatchNames: async () => ["AE.ADBE Cross Dissolve New", "AE.ADBE Dip To Black", "AE.ADBE Dip To White"],
    createVideoTransition: (name) => ({ name }),
  },
  AddTransitionOptions: () => {
    const o = {};
    return { o, setApplyToStart(v) { o.start = v; return this; }, setDuration(t) { o.duration = t.seconds; return this; },
             setTransitionAlignment(v) { o.alignment = v; return this; }, setForceSingleSided(v) { o.single = v; return this; } };
  },
  VideoFilterFactory: {
    getMatchNames: async () => ["AE.ADBE SubspaceStabilizer", "AE.ADBE Lumetri"],
    getDisplayNames: async () => ["Warp Stabilizer", "Lumetri Color"],
    createComponent: async (m) => new Component(m, m === "AE.ADBE SubspaceStabilizer" ? "Warp Stabilizer" : m, []),
  },
  Exporter: { exportSequenceFrame: async (seq, t, name, dir) => { state.frames = (state.frames || []).concat([[dir, name]]); return true; } },
  Markers: {
    getMarkers: async (seq) => ({
      getMarkers: () => seq.markers.map((m) => ({ getName: () => m.name, getStart: () => m.start, getDuration: () => m.duration, getComments: () => m.comment, getColorIndex: () => 0 })),
      createAddMarkerAction: (name, type, start, duration, comment) => () => { seq.markers.push({ name, start, duration, comment }); },
    }),
  },
};

async function main() {
  const [libPath, op, argsPath] = process.argv.slice(2);
  const lib = new Function("ppro", "uxp", "require", fs.readFileSync(libPath, "utf8"))(ppro, {}, require);
  const args = JSON.parse(fs.readFileSync(argsPath, "utf8"));
  for (const p of args.preimported || []) {  // already in the project, offline (file deleted then rewritten)
    const pi = new ProjectItem(p.split(/[\\/]/).pop(), p, false);
    pi.offline = true;
    root.children.push(pi);
  }
  const events = [];
  const ctx = { log: () => {}, progress: (id, done, total, text) => events.push([done, total, text]) };
  let result;
  if (op === "chain") {  // several ops in one session: [[op, args], ...]
    result = [];
    for (const [o, a] of args.ops) {
      try { result.push(await lib[o](a, ctx, "r1")); } catch (e) { result.push({ error: String(e.message || e) }); }
    }
  } else {
    result = await lib[op](args, ctx, "r1");
  }
  const seqs = state.sequences.map((s) => ({
    name: s.name, preset: s.preset, captionTracks: s.captionTracks,
    markers: s.markers.map((m) => ({ name: m.name, time: m.start.seconds })),
    tracks: s.video.concat(s.audio).map((t) => ({
      track: t.name, items: t.items.sort((a, b) => Number(a.start.ticks) - Number(b.start.ticks)).map((it) => ({
        path: it.pi.path, start: it.start.ticks, end: it.end.ticks, in: it.inT.ticks, disabled: it.disabled,
        transitions: it.transitions,
        components: it.chain.list.map((c) => ({ name: c.name, params: c.params.map((p) => [p.displayName, p.value, p.keys]) })),
        lut: it.pi.lut || null,
      })),
    })),
  }));
  process.stdout.write(JSON.stringify({ result, events, state: { imported: state.imported, frames: state.frames || [], removed: state.removed || 0, transactions: state.transactions.length, sequences: seqs } }));
}
main().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
