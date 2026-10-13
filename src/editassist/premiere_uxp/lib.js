// editassist operations for Premiere Pro (UXP API, 25.6+; checked against the 26.3 typings).
//
// Sent at runtime by `ea` (premiere_bridge.call) and evaluated inside the panel as
// `new Function("ppro", "uxp", "require", source)`: this file is a function BODY that returns the
// table of operations. Each op is `async (args, ctx, requestId) => plain JSON`.
//
// Conventions shared with the Python side (premiere_native.py):
// - Times travel as seconds (floats) for reading, and as exact tick strings ("ticks") for building:
//   254016000000 ticks per second, so NTSC frame boundaries are exact integers.
// - Tracks are named "V1".."Vn" / "A1".."An" (1-based, like the Premiere UI).
// - A track item is referenced as {track: "V1", index: 0} (clips sorted by start) or
//   {track: "V1", at: 12.5} (the clip under that time).
// - Every change runs inside project.lockedAccess + executeTransaction, so it is ONE undo step in
//   Premiere (Edit > Undo shows the label).
"use strict";

const TPS = 254016000000;  // Premiere ticks per second
const C = ppro.Constants;

// ------------------------------------------------------------------------------------- basics

async function project() {
  const p = await ppro.Project.getActiveProject();
  if (!p) throw new Error("no project open in Premiere");
  return p;
}

const T = (sec) => ppro.TickTime.createWithSeconds(Number(sec));
const TK = (ticks) => ppro.TickTime.createWithTicks(String(ticks));
const time = (v) => (v && v.ticks !== undefined ? TK(v.ticks) : T(v));
const sec = (tt) => (tt && typeof tt.seconds === "number" ? Math.round(tt.seconds * 1e6) / 1e6 : null);

function tx(proj, label, build) {
  let ok = false;
  let err = null;
  proj.lockedAccess(() => {
    try {
      ok = proj.executeTransaction((compound) => {
        const actions = build();
        for (const a of [].concat(actions || [])) if (a) compound.addAction(a);
      }, label);
    } catch (e) { err = e; }
  });
  if (err) throw err;
  if (!ok) throw new Error(`Premiere refused: ${label}`);
  return ok;
}

async function sequenceByName(proj, name) {
  if (!name) {
    const s = await proj.getActiveSequence();
    if (!s) throw new Error("no active sequence (open one or pass sequence)");
    return s;
  }
  for (const s of await proj.getSequences()) {
    if (s.name === name || String(s.guid) === name) return s;
  }
  throw new Error(`no sequence named ${name}`);
}

function parseTrack(name) {
  const m = /^([VAva])(\d+)$/.exec(String(name || ""));
  if (!m) throw new Error(`track must look like V1 or A2, got ${name}`);
  return { kind: m[1].toUpperCase() === "V" ? "video" : "audio", index: Number(m[2]) - 1 };
}

async function getTrack(seq, name) {
  const t = parseTrack(name);
  const count = t.kind === "video" ? await seq.getVideoTrackCount() : await seq.getAudioTrackCount();
  if (t.index >= count) throw new Error(`${name} does not exist (sequence has ${count} ${t.kind} tracks)`);
  const track = t.kind === "video" ? await seq.getVideoTrack(t.index) : await seq.getAudioTrack(t.index);
  return { ...t, track };
}

async function trackItems(track) {
  const items = await track.getTrackItems(C.TrackItemType.CLIP, false);
  const withStart = [];
  for (const it of items) withStart.push({ it, start: (await it.getStartTime()).seconds });
  withStart.sort((a, b) => a.start - b.start);
  return withStart.map((x) => x.it);
}

async function findItem(seq, ref) {
  if (!ref || !ref.track) throw new Error("item reference needs {track, index} or {track, at}");
  const { track } = await getTrack(seq, ref.track);
  const items = await trackItems(track);
  if (ref.index !== undefined) {
    const it = items[Number(ref.index)];
    if (!it) throw new Error(`${ref.track} has no clip #${ref.index} (${items.length} clips)`);
    return it;
  }
  if (ref.at !== undefined) {
    for (const it of items) {
      const a = (await it.getStartTime()).seconds;
      const b = (await it.getEndTime()).seconds;
      if (ref.at >= a - 1e-6 && ref.at < b) return it;
    }
    throw new Error(`no clip on ${ref.track} at ${ref.at}s`);
  }
  throw new Error("item reference needs index or at");
}

async function mediaPath(projectItem) {
  try {
    const clip = ppro.ClipProjectItem.cast(projectItem);
    return clip ? await clip.getMediaFilePath() : null;
  } catch (e) {
    return null;
  }
}

async function describeItem(it, i) {
  const out = {
    index: i,
    name: await it.getName(),
    start: sec(await it.getStartTime()),
    end: sec(await it.getEndTime()),
    in: sec(await it.getInPoint()),
    out: sec(await it.getOutPoint()),
    disabled: await it.isDisabled(),
  };
  try { out.speed = await it.getSpeed(); } catch (e) { /* not on every item */ }
  try { out.media = await mediaPath(await it.getProjectItem()); } catch (e) { /* graphics */ }
  return out;
}

async function frameRateOf(seq) {
  // getTimebase() = ticks per frame as a string (e.g. "8475667200" at 29.97)
  const tpf = Number(await seq.getTimebase());
  return { tpf, fps: tpf ? Math.round((TPS / tpf) * 1000) / 1000 : null };
}

// --------------------------------------------------------------------------- project items / bins

async function walk(folder, visit, depth = 0, maxDepth = 50, trail = "") {
  const items = await folder.getItems();
  for (const pi of items) {
    let clip = null, bin = null;
    try { clip = ppro.ClipProjectItem.cast(pi); } catch (e) { clip = null; }
    if (!clip) { try { bin = ppro.FolderItem.cast(pi); } catch (e) { bin = null; } }
    const here = trail ? `${trail}/${pi.name}` : pi.name;
    if (await visit(pi, { depth, isBin: !!bin, path: here }) === true) return true;
    if (bin && depth < maxDepth && await walk(bin, visit, depth + 1, maxDepth, here)) return true;
  }
  return false;
}

function isBin(pi) {
  try { if (ppro.ClipProjectItem.cast(pi)) return false; } catch (e) { /* not a clip */ }
  try { return !!ppro.FolderItem.cast(pi); } catch (e) { return false; }
}

function samePath(a, b) {
  if (!a || !b) return false;
  const n = (p) => String(p).replace(/\\/g, "/").replace(/\/+$/, "").normalize("NFC");
  const x = n(a), y = n(b);
  return x === y || x.toLowerCase() === y.toLowerCase();
}

async function isOffline(pi) {
  try { return await ppro.ClipProjectItem.cast(pi).isOffline(); } catch (e) { return false; }
}

async function itemsByPath(proj, paths, skipOffline = false) {
  const want = new Map(paths.map((p) => [p, null]));
  const root = await proj.getRootItem();
  await walk(root, async (pi, info) => {
    if (info.isBin) return false;
    const mp = await mediaPath(pi);
    if (!mp) return false;
    for (const p of want.keys()) {
      if (!want.get(p) && samePath(mp, p) && !(skipOffline && await isOffline(pi))) want.set(p, pi);
    }
    return [...want.values()].every(Boolean);
  });
  return want;
}

// An item whose file was deleted and written again (work/baked cleaned, a project re-created) stays
// offline in Premiere and plays silence / "media offline" when reused: relink it to the same path
// (refreshMedia() does not bring it back, checked on 26.3). False when it stays offline.
async function online(pi, path) {
  if (!(await isOffline(pi))) return true;
  try { await ppro.ClipProjectItem.cast(pi).changeMediaFilePath(path, true); } catch (e) { /* stays offline */ }
  return !(await isOffline(pi));
}

async function binNamed(proj, name, create = true) {
  const root = await proj.getRootItem();
  if (!name) return root;
  let folder = ppro.FolderItem.cast(root);
  for (const part of String(name).split("/").filter(Boolean)) {
    let found = null;
    for (const pi of await folder.getItems()) {
      if (pi.name === part && isBin(pi)) { found = ppro.FolderItem.cast(pi); break; }
    }
    if (!found) {
      if (!create) throw new Error(`no bin ${name}`);
      const parent = folder;
      tx(proj, `editassist: bin ${part}`, () => parent.createBinAction(part, false));
      for (const pi of await parent.getItems()) {
        if (pi.name === part && isBin(pi)) { found = ppro.FolderItem.cast(pi); break; }
      }
      if (!found) throw new Error(`could not create bin ${part}`);
    }
    folder = found;
  }
  return folder;
}

async function importInto(proj, paths, bin) {
  const have = await itemsByPath(proj, paths);
  for (const p of paths) if (have.get(p) && !(await online(have.get(p), p))) have.set(p, null);
  const missing = paths.filter((p) => !have.get(p));
  if (missing.length) {
    const target = bin ? ppro.ProjectItem.cast(await binNamed(proj, bin)) : undefined;
    const ok = await proj.importFiles(missing, true, target, false);
    if (!ok) throw new Error(`Premiere could not import: ${missing.join(", ")}`);
    const again = await itemsByPath(proj, missing, true);
    for (const p of missing) have.set(p, again.get(p));
  }
  const lost = paths.filter((p) => !have.get(p));
  if (lost.length) throw new Error(`imported but not found in the project: ${lost.join(", ")}`);
  return { items: have, imported: missing.length };
}

// ------------------------------------------------------------------------------ components / params

async function componentsOf(it) {
  const chain = await it.getComponentChain();
  const out = [];
  const n = chain.getComponentCount();
  for (let i = 0; i < n; i++) {
    const comp = chain.getComponentAtIndex(i);
    out.push({ comp, index: i, matchName: await comp.getMatchName(), name: await comp.getDisplayName() });
  }
  return { chain, list: out };
}

async function findParam(it, component, param) {
  const { list } = await componentsOf(it);
  const want = String(component).toLowerCase();
  const c = list.find((x) => x.matchName.toLowerCase() === want || x.name.toLowerCase() === want)
    || list.find((x) => x.matchName.toLowerCase().includes(want) || x.name.toLowerCase().includes(want));
  if (!c) throw new Error(`no component ${component} (has: ${list.map((x) => x.name).join(", ")})`);
  const n = c.comp.getParamCount();
  const names = [];
  for (let i = 0; i < n; i++) {
    const p = c.comp.getParam(i);
    names.push(p.displayName);
    if (typeof param === "number" ? i === param : String(p.displayName).toLowerCase() === String(param).toLowerCase()) {
      return { comp: c, param: p };
    }
  }
  throw new Error(`no param ${param} in ${c.name} (has: ${names.join(", ")})`);
}

function plainValue(v) {
  if (v === null || v === undefined) return null;
  if (typeof v !== "object") return v;
  if (Array.isArray(v)) return v.map(plainValue);
  if (v.value !== undefined && v.position !== undefined) return plainValue(v.value);  // Keyframe
  if (Object.keys(v).length === 1 && v.value !== undefined) return plainValue(v.value);  // 26.3 wraps values: {value: x}
  if (typeof v.x === "number" && typeof v.y === "number") return [v.x, v.y];
  if (typeof v.red === "number") return { r: v.red, g: v.green, b: v.blue, a: v.alpha };
  if (typeof v.getText === "function") return v.getText();
  return String(v);
}

function makeValue(param, value, like) {
  if (Array.isArray(value)) {
    const pt = new ppro.PointF(value[0], value[1]);
    return param.createKeyframe(pt);
  }
  if (value && typeof value === "object" && value.r !== undefined) {
    return param.createKeyframe(new ppro.Color(value.r, value.g, value.b, value.a === undefined ? 1 : value.a));
  }
  return param.createKeyframe(value);
}

async function setParamValue(proj, it, component, paramName, value, keyframes, label) {
  const { param } = await findParam(it, component, paramName);
  if (keyframes && keyframes.length) {
    const itemStart = (await it.getStartTime()).seconds;
    const itemIn = (await it.getInPoint()).seconds;
    tx(proj, `${label}: keyframes`, () => param.createSetTimeVaryingAction(true));
    tx(proj, label, () => keyframes.map(([t, v]) => {
      // keyframe times are clip-relative seconds from the clip's first frame (source time = in + t)
      const kf = makeValue(param, v);
      kf.position = T(itemIn + Number(t));
      return param.createAddKeyframeAction(kf);
    }));
    return { keyframes: keyframes.length, item_start: itemStart };
  }
  if (param.isTimeVarying()) tx(proj, `${label}: static`, () => param.createSetTimeVaryingAction(false));
  tx(proj, label, () => param.createSetValueAction(makeValue(param, value), true));
  return { value: plainValue(await param.getStartValue()) };
}

// Motion: `scale` in % of source pixels, `center` in sequence pixels ([x, y] from top-left).
// `ramp` [[t, scale%], ...] and `center_ramp` [[t, [x, y]], ...] animate a push-in (clip-relative seconds).
// The Position param is normalised (0..1 of the frame) on recent versions and pixels on some older
// builds: read the current value and answer in the same unit.
async function setMotion(proj, it, motion, frame, label) {
  const { param: scale } = await findParam(it, "AE.ADBE Motion", "Scale");
  const { param: pos } = await findParam(it, "AE.ADBE Motion", "Position");
  const cur = plainValue(await pos.getStartValue());
  const normalised = Array.isArray(cur) && Math.abs(cur[0]) <= 2 && Math.abs(cur[1]) <= 2;
  const unit = (c) => (normalised ? [c[0] / frame.width, c[1] / frame.height] : c);
  const p = unit(motion.center || [frame.width / 2, frame.height / 2]);
  const itemIn = (await it.getInPoint()).seconds;
  const ramp = motion.ramp && motion.ramp.length ? motion.ramp : null;
  const pramp = motion.center_ramp && motion.center_ramp.length ? motion.center_ramp : null;
  if (ramp) {
    tx(proj, `${label}: scale keyframes on`, () => scale.createSetTimeVaryingAction(true));
    tx(proj, `${label}: push-in`, () => ramp.map(([t, s]) => {
      const kf = scale.createKeyframe(Number(s));
      kf.position = T(itemIn + Number(t));
      return scale.createAddKeyframeAction(kf);
    }));
  } else if (motion.scale !== undefined && scale.isTimeVarying()) {
    tx(proj, `${label}: scale static`, () => scale.createSetTimeVaryingAction(false));
  }
  if (pramp) {
    tx(proj, `${label}: position keyframes on`, () => pos.createSetTimeVaryingAction(true));
    tx(proj, `${label}: push-in drift`, () => pramp.map(([t, c]) => {
      const q = unit(c);
      const kf = pos.createKeyframe(new ppro.PointF(q[0], q[1]));
      kf.position = T(itemIn + Number(t));
      return pos.createAddKeyframeAction(kf);
    }));
  } else if (pos.isTimeVarying()) {
    tx(proj, `${label}: position static`, () => pos.createSetTimeVaryingAction(false));
  }
  // Actions must be created inside the transaction: ones made earlier are stale by then (26.3)
  tx(proj, label, () => {
    const a = [];
    if (!pramp) a.push(pos.createSetValueAction(pos.createKeyframe(new ppro.PointF(p[0], p[1])), true));
    if (!ramp && motion.scale !== undefined) a.push(scale.createSetValueAction(scale.createKeyframe(Number(motion.scale)), true));
    return a;
  });
  return { scale: motion.scale, position: p, normalised, keyframed: !!(ramp || pramp) };
}

// ------------------------------------------------------------------------------------- transitions

async function transitionMatch(kind) {
  const names = await ppro.TransitionFactory.getVideoTransitionMatchNames();
  if (kind && names.includes(kind)) return kind;
  const want = { dissolve: ["Cross Dissolve", "CrossDissolve"], dip: ["Dip to Black", "DipToBlack"],
                 fade: ["Dip to Black", "DipToBlack"], white: ["Dip to White", "DipToWhite"],
                 film: ["Film Dissolve"] }[kind || "dissolve"] || [kind];
  for (const w of want) {
    const hit = names.find((n) => n.toLowerCase().replace(/[^a-z]/g, "").includes(w.toLowerCase().replace(/[^a-z]/g, "")));
    if (hit) return hit;
  }
  throw new Error(`no transition like ${kind}; available: ${names.join(", ")}`);
}

async function addTransition(proj, it, { type, duration, at, alignment, single }) {
  const match = await transitionMatch(type);
  const tr = await ppro.TransitionFactory.createVideoTransition(match);
  const opts = ppro.AddTransitionOptions();
  opts.setApplyToStart(at !== "end");
  if (duration) opts.setDuration(T(duration));
  if (alignment !== undefined) opts.setTransitionAlignment(Number(alignment));
  if (single) opts.setForceSingleSided(true);
  tx(proj, `editassist: ${type || "dissolve"} ${at || "start"}`, () => it.createAddVideoTransitionAction(tr, opts));
  return { transition: match };
}

// --------------------------------------------------------------------------------------- placing

// One clip onto the sequence. Overwrite edit: the project item's in/out are set first, then
// SequenceEditor.createOverwriteItemAction places it on video track `video_track` and audio track
// `audio_track` (0-based); the end is then trimmed to the exact tick. `find` lists the halves to
// locate afterwards ("video", "audio"): a pure audio file has no video half, and V1 may already hold
// another clip at that time, so only the requested halves are looked up.
async function placeOne(proj, seq, editor, pi, c) {
  if (!pi) throw new Error("media not in the project");
  const clip = ppro.ClipProjectItem.cast(pi);
  const vIdx = Number(c.video_track || 0);
  const aIdx = Number(c.audio_track || 0);
  if (c.in !== undefined && c.out !== undefined) {
    tx(proj, "editassist: source in/out", () => clip.createSetInOutPointsAction(time(c.in), time(c.out)));
  }
  const at = time(c.start);
  const find = c.find || ["video", "audio"];
  tx(proj, `editassist: place ${pi.name}`, () => editor.createOverwriteItemAction(pi, at, vIdx, aIdx));
  const placed = {};
  for (const kind of find) {
    const track = kind === "video" ? await seq.getVideoTrack(vIdx) : await seq.getAudioTrack(aIdx);
    if (!track) continue;
    for (const it of await trackItems(track)) {
      const s = (await it.getStartTime()).ticks;
      if (Math.abs(Number(s) - Number(at.ticks)) < 1000) { placed[kind] = it; break; }
    }
  }
  if (c.end !== undefined) {
    const end = time(c.end);
    for (const it of Object.values(placed)) {
      const e = await it.getEndTime();
      if (e.ticks !== end.ticks) tx(proj, "editassist: trim end", () => it.createSetEndAction(end));
    }
  }
  return placed;
}

async function itemAtTicks(seq, kind, idx, ticks) {
  const track = kind === "video" ? await seq.getVideoTrack(idx) : await seq.getAudioTrack(idx);
  if (!track) return null;
  for (const it of await trackItems(track)) {
    if (Math.abs(Number((await it.getStartTime()).ticks) - Number(ticks)) < 1000) return it;
  }
  return null;
}

// The sequence's own selection object: a TrackItemSelection from createEmptySelection() is only
// valid inside its callback ("The script object is no longer valid" afterwards, 26.3).
async function selectionOf(seq, items) {
  await seq.clearSelection();
  const sel = await seq.getSelection();
  for (const it of items) sel.addItem(it, true);
  return sel;
}

// The other halves of linked A/V items: same media, same start and end, on any track. The API has no
// link query and, unlike a click in the timeline, selects only the item given; a ripple delete of one half
// does nothing while its linked half stays (checked on 26.3).
async function withLinked(seq, items) {
  const out = [...items];
  const key = async (it) => `${(await it.getStartTime()).ticks}|${(await it.getEndTime()).ticks}|${await mediaPath(await it.getProjectItem())}`;
  const where = async (it) => `${(await it.getMediaType()).toString() === C.MediaType.AUDIO.toString() ? "audio" : "video"}:${await it.getTrackIndex()}`;
  const want = new Map();  // key -> tracks the given items sit on (wrappers differ per fetch: no identity)
  for (const it of items) {
    const k = await key(it);
    if (!want.has(k)) want.set(k, new Set());
    want.get(k).add(await where(it));
  }
  for (const kind of ["video", "audio"]) {
    const n = kind === "video" ? await seq.getVideoTrackCount() : await seq.getAudioTrackCount();
    for (let i = 0; i < n; i++) {
      const tr = kind === "video" ? await seq.getVideoTrack(i) : await seq.getAudioTrack(i);
      for (const it of await tr.getTrackItems(C.TrackItemType.CLIP, false)) {
        const k = await key(it);
        if (want.has(k) && !want.get(k).has(`${kind}:${i}`)) out.push(it);
      }
    }
  }
  return out;
}

async function removeItems(proj, seq, items, ripple, label) {
  if (!items.length) return 0;
  const sel = await selectionOf(seq, items);
  const editor = ppro.SequenceEditor.getEditor(seq);
  tx(proj, label, () => editor.createRemoveItemsAction(sel, !!ripple, C.MediaType.VIDEO, false));
  await seq.clearSelection();
  return items.length;
}

// ============================================================================================ ops

const ops = {
  async info() {
    const p = await ppro.Project.getActiveProject();
    if (!p) return { project: null };
    const active = await p.getActiveSequence();
    const seqs = [];
    for (const s of await p.getSequences()) seqs.push({ name: s.name, guid: String(s.guid), active: !!active && String(active.guid) === String(s.guid) });
    return { project: { name: p.name, path: p.path }, sequences: seqs, active: active ? active.name : null };
  },

  async sequence(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const { fps } = await frameRateOf(seq);
    const rect = await seq.getFrameSize();
    const out = {
      name: seq.name, guid: String(seq.guid), fps, width: rect.width, height: rect.height,
      end: sec(await seq.getEndTime()), playhead: sec(await seq.getPlayerPosition()),
      in: Math.max(sec(await seq.getInPoint()), -1) < 0 ? null : sec(await seq.getInPoint()),
      out: Math.max(sec(await seq.getOutPoint()), -1) < 0 ? null : sec(await seq.getOutPoint()), tracks: [],
    };
    const nv = await seq.getVideoTrackCount();
    const na = await seq.getAudioTrackCount();
    for (const [kind, n] of [["V", nv], ["A", na]]) {
      for (let i = 0; i < n; i++) {
        const tr = kind === "V" ? await seq.getVideoTrack(i) : await seq.getAudioTrack(i);
        const items = await trackItems(tr);
        const entry = { track: `${kind}${i + 1}`, name: tr.name, muted: await tr.isMuted(), count: items.length };
        if (args.items !== false) {
          entry.clips = [];
          const from = args.from || 0, to = args.to === undefined ? Infinity : args.to;
          for (let j = 0; j < items.length; j++) {
            const d = await describeItem(items[j], j);
            if (d.end > from && d.start < to) entry.clips.push(d);
          }
        }
        out.tracks.push(entry);
      }
    }
    const markers = await ppro.Markers.getMarkers(seq);
    out.markers = markers.getMarkers().map((m) => ({ name: m.getName(), start: sec(m.getStart()), duration: sec(m.getDuration()), comment: m.getComments(), color: m.getColorIndex() }));
    return out;
  },

  async clip(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const it = await findItem(seq, args);
    const d = await describeItem(it, args.index);
    const { list } = await componentsOf(it);
    d.components = [];
    for (const c of list) {
      const params = [];
      const n = c.comp.getParamCount();
      for (let i = 0; i < n; i++) {
        const p = c.comp.getParam(i);
        let value = null;
        try { value = plainValue(await p.getStartValue()); } catch (e) { value = null; }
        params.push({ index: i, name: p.displayName, value, keyframed: p.isTimeVarying() });
      }
      d.components.push({ index: c.index, name: c.name, matchName: c.matchName, params });
    }
    return d;
  },

  async items(args) {
    const proj = await project();
    const start = args.bin ? await binNamed(proj, args.bin, false) : await proj.getRootItem();
    const out = [];
    const limit = args.limit || 500;
    await walk(start, async (pi, info) => {
      const row = { path: info.path, bin: info.isBin, id: pi.getId ? pi.getId() : null };
      if (!info.isBin) row.media = await mediaPath(pi);
      out.push(row);
      return out.length >= limit;
    }, 0, args.depth === undefined ? 50 : args.depth);
    return { items: out, truncated: out.length >= limit };
  },

  async open_project(args) {
    const p = await ppro.Project.open(args.path);
    return { name: p.name, path: p.path };
  },

  async new_project(args) {
    const p = await ppro.Project.createProject(args.path);
    return { name: p.name, path: p.path };
  },

  async save(args) {
    const proj = await project();
    const ok = args.path ? await proj.saveAs(args.path) : await proj.save();
    return { saved: ok, path: args.path || proj.path };
  },

  async import(args) {
    const proj = await project();
    const { items, imported } = await importInto(proj, args.paths, args.bin);
    return { imported, items: [...items.entries()].map(([p, pi]) => ({ path: p, name: pi.name })) };
  },

  async bin(args) {
    const proj = await project();
    await binNamed(proj, args.name, true);
    return { bin: args.name };
  },

  async create_sequence(args) {
    const proj = await project();
    const seq = args.preset ? await proj.createSequence(args.name, args.preset) : await proj.createSequence(args.name);
    if (!seq) throw new Error("Premiere did not create the sequence");
    await proj.setActiveSequence(seq);
    try { await proj.openSequence(seq); } catch (e) { /* already open */ }
    if (args.bin) {
      const bin = await binNamed(proj, args.bin, true);
      const si = await seq.getProjectItem();
      const root = ppro.FolderItem.cast(await proj.getRootItem());
      tx(proj, "editassist: file sequence", () => root.createMoveItemAction(si, bin));
    }
    return { name: seq.name, guid: String(seq.guid) };
  },

  async activate_sequence(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    await proj.setActiveSequence(seq);
    try { await proj.openSequence(seq); } catch (e) { /* already open */ }
    return { active: seq.name };
  },

  async place(args, ctx, id) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const editor = ppro.SequenceEditor.getEditor(seq);
    const paths = [...new Set(args.clips.map((c) => c.path))];
    const { items } = await importInto(proj, paths, args.bin);
    const out = [];
    for (let i = 0; i < args.clips.length; i++) {
      const c = args.clips[i];
      const placed = await placeOne(proj, seq, editor, items.get(c.path), c);
      out.push(Object.keys(placed));
      ctx.progress(id, i + 1, args.clips.length, c.path);
    }
    return { placed: out.length, tracks: out };
  },

  async move(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const it = await findItem(seq, args);
    const start = (await it.getStartTime()).seconds;
    tx(proj, "editassist: move", () => it.createMoveAction(T(Number(args.start) - start)));
    return await describeItem(it);
  },

  async trim(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const it = await findItem(seq, args);
    tx(proj, "editassist: trim", () => {
      const a = [];
      if (args.in !== undefined) a.push(it.createSetInPointAction(T(args.in)));
      if (args.out !== undefined) a.push(it.createSetOutPointAction(T(args.out)));
      if (args.start !== undefined) a.push(it.createSetStartAction(T(args.start)));
      if (args.end !== undefined) a.push(it.createSetEndAction(T(args.end)));
      return a;
    });
    return await describeItem(it);
  },

  async remove(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const items = [];
    for (const ref of args.items) items.push(await findItem(seq, ref));
    const all = args.linked === false ? items : await withLinked(seq, items);
    // Premiere closes a ripple gap only as far as the other sync-locked tracks allow (a clip on another
    // track inside the gap stops it, as in the UI): report how far the next clip actually moved
    let next = null;
    if (args.ripple) {
      const end = (await items[0].getEndTime()).seconds;
      const { track } = await getTrack(seq, args.items[0].track);
      for (const it of await trackItems(track)) {
        const st = (await it.getStartTime()).seconds;
        if (st >= end - 1e-6) { next = { before: st, ticks: (await it.getEndTime()).ticks }; break; }
      }
    }
    const n = await removeItems(proj, seq, all, args.ripple, args.ripple ? "editassist: ripple delete" : "editassist: delete");
    const out = { removed: n, linked_halves: all.length - items.length, ripple: !!args.ripple };
    if (next) {
      const { track } = await getTrack(seq, args.items[0].track);
      for (const it of await trackItems(track)) {
        const e = (await it.getEndTime()).ticks;
        // the same clip: its end moved by the same amount as its start
        const st = (await it.getStartTime()).seconds;
        const moved = Math.round((next.before - st) * 1e6) / 1e6;
        if (Math.abs(Number(e) - Number(next.ticks) + moved * TPS) < 1000) { out.closed = moved; break; }
      }
    }
    return out;
  },

  async enable(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const items = [];
    for (const ref of args.items) items.push(await findItem(seq, ref));
    tx(proj, args.enabled === false ? "editassist: disable" : "editassist: enable",
      () => items.map((it) => it.createSetDisabledAction(args.enabled === false)));
    return { changed: items.length };
  },

  async rename(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const it = await findItem(seq, args);
    tx(proj, "editassist: rename", () => it.createSetNameAction(args.name));
    return { name: args.name };
  },

  async transition(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const it = await findItem(seq, args);
    if (args.remove) {
      tx(proj, "editassist: remove transition", () => it.createRemoveVideoTransitionAction(
        args.at === "end" ? C.TransitionPosition.END : C.TransitionPosition.START));
      return { removed: true };
    }
    return await addTransition(proj, it, args);
  },

  async catalog(args) {
    const kind = args.kind || "video";
    let names;
    if (kind === "transition") names = await ppro.TransitionFactory.getVideoTransitionMatchNames();
    else if (kind === "audio") names = await ppro.AudioFilterFactory.getDisplayNames();
    else {
      const m = await ppro.VideoFilterFactory.getMatchNames();
      const d = await ppro.VideoFilterFactory.getDisplayNames();
      names = m.map((x, i) => `${x} | ${d[i] || ""}`);
    }
    const f = (args.filter || "").toLowerCase();
    return names.filter((n) => !f || n.toLowerCase().includes(f));
  },

  async add_effect(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const it = await findItem(seq, args);
    const chain = await it.getComponentChain();
    let comp;
    if (parseTrack(args.track).kind === "audio") {
      comp = await ppro.AudioFilterFactory.createComponentByDisplayName(args.name, it);
    } else {
      let match = args.match_name;
      if (!match) {
        const m = await ppro.VideoFilterFactory.getMatchNames();
        const d = await ppro.VideoFilterFactory.getDisplayNames();
        const i = d.findIndex((x) => x.toLowerCase() === String(args.name).toLowerCase());
        if (i < 0) throw new Error(`no video effect named ${args.name} (see catalog)`);
        match = m[i];
      }
      comp = await ppro.VideoFilterFactory.createComponent(match);
    }
    tx(proj, `editassist: effect ${args.name || args.match_name}`, () => chain.createAppendComponentAction(comp));
    return { added: args.name || args.match_name };
  },

  async remove_effect(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const it = await findItem(seq, args);
    const { chain, list } = await componentsOf(it);
    const c = list.find((x) => x.index === args.component || x.name === args.component || x.matchName === args.component);
    if (!c) throw new Error(`no component ${args.component}`);
    tx(proj, `editassist: remove ${c.name}`, () => chain.createRemoveComponentAction(c.comp));
    return { removed: c.name };
  },

  async set_param(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const it = await findItem(seq, args);
    return await setParamValue(proj, it, args.component, args.param, args.value, args.keyframes, `editassist: ${args.param}`);
  },

  async motion(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const it = await findItem(seq, args);
    const rect = await seq.getFrameSize();
    return await setMotion(proj, it, args, { width: rect.width, height: rect.height }, "editassist: motion");
  },

  async add_marker(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const markers = await ppro.Markers.getMarkers(seq);
    tx(proj, "editassist: marker", () => markers.createAddMarkerAction(
      args.name || "", args.type || "Comment", T(args.time), T(args.duration || 0), args.comment || ""));
    if (args.color !== undefined) {
      const all = markers.getMarkers();
      const m = all.find((x) => Math.abs(x.getStart().seconds - Number(args.time)) < 1e-3 && x.getName() === (args.name || ""));
      if (m) tx(proj, "editassist: marker colour", () => m.createSetColorByIndexAction(Number(args.color)));
    }
    return { marker: args.name, time: args.time };
  },

  async remove_markers(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const markers = await ppro.Markers.getMarkers(seq);
    const hit = markers.getMarkers().filter((m) => (args.name === undefined || m.getName() === args.name)
      && (args.time === undefined || Math.abs(m.getStart().seconds - Number(args.time)) < 1e-3));
    if (hit.length) tx(proj, "editassist: remove markers", () => hit.map((m) => markers.createRemoveMarkerAction(m)));
    return { removed: hit.length };
  },

  async playhead(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    if (args.time !== undefined) await seq.setPlayerPosition(T(args.time));
    return { playhead: sec(await seq.getPlayerPosition()) };
  },

  async select(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const items = [];
    for (const ref of args.items || []) items.push(await findItem(seq, ref));
    const sel = await selectionOf(seq, items);
    if (items.length) seq.setSelection(sel);
    return { selected: items.length };
  },

  async selection(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const sel = await seq.getSelection();
    const out = [];
    for (const it of await sel.getTrackItems()) {
      const d = await describeItem(it);
      const k = (await it.getMediaType()).toString() === C.MediaType.AUDIO.toString() ? "A" : "V";
      d.track = `${k}${(await it.getTrackIndex()) + 1}`;
      out.push(d);
    }
    return out;
  },

  async frame(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const rect = await seq.getFrameSize();
    const w = args.width || rect.width, h = args.height || Math.round(rect.height * (args.width || rect.width) / rect.width);
    // split at the last separator of either kind, keeping the OS's own (C:\... on Windows)
    const path = String(args.path);
    const cut = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
    const dir = path.slice(0, cut);
    const name = path.slice(cut + 1);
    const ok = await ppro.Exporter.exportSequenceFrame(seq, T(args.time), name, dir, w, h);
    if (!ok) throw new Error("exportSequenceFrame failed");
    return { path: args.path, time: args.time, width: w, height: h };
  },

  async export(args) {
    const proj = await project();
    const seq = await sequenceByName(proj, args.sequence);
    const mgr = ppro.EncoderManager.getManager();
    const mode = { now: C.ExportType.IMMEDIATELY, queue: C.ExportType.QUEUE_TO_APP, ame: C.ExportType.QUEUE_TO_AME }[args.mode || "now"];
    const ok = await mgr.exportSequence(seq, mode, args.path, args.preset, args.work_area ? false : true);
    return { started: ok, path: args.path, mode: args.mode || "now" };
  },

  // What exists in this Premiere build: own keys of ppro.<name> and its prototype methods.
  async api(args) {
    const target = args.name ? ppro[args.name] : ppro;
    if (target === undefined) throw new Error(`ppro.${args.name} does not exist in this version`);
    const keys = new Set(Object.keys(target));
    let proto = Object.getPrototypeOf(target);
    while (proto && proto !== Object.prototype) {
      for (const k of Object.getOwnPropertyNames(proto)) if (k !== "constructor") keys.add(k);
      proto = Object.getPrototypeOf(proto);
    }
    return [...keys].sort();
  },

  // Build a whole editassist timeline (spec from premiere_native.plan) into a new sequence.
  async build(args, ctx, id) {
    const spec = args.spec;
    const proj = await project();
    const report = { sequence: spec.name, placed: 0, failed: [], motion: 0, transitions: 0, opacity: 0,
                     markers: 0, notes: [] };
    const paths = [...new Set(spec.clips.map((c) => c.path).concat(spec.srt ? [spec.srt] : []))];
    ctx.log(`importing ${paths.length} files`);
    const { items, imported } = await importInto(proj, paths, spec.bin);
    report.imported = imported;

    let seq;
    if (spec.into_current) {
      seq = await sequenceByName(proj, null);
    } else {
      seq = await proj.createSequence(spec.name, spec.preset);
      if (!seq) throw new Error("Premiere did not create the sequence (preset: " + spec.preset + ")");
      if (spec.bin) {
        try {
          const bin = await binNamed(proj, spec.bin, true);
          const root = ppro.FolderItem.cast(await proj.getRootItem());
          const si = await seq.getProjectItem();
          tx(proj, "editassist: file sequence", () => root.createMoveItemAction(si, bin));
        } catch (e) { report.notes.push(`sequence left in the root bin: ${e.message || e}`); }
      }
    }
    await proj.setActiveSequence(seq);
    try { await proj.openSequence(seq); } catch (e) { /* open already */ }
    report.sequence = seq.name;
    const nv = await seq.getVideoTrackCount();
    const na = await seq.getAudioTrackCount();
    if (nv < spec.video_tracks || na < spec.audio_tracks) {
      report.notes.push(`sequence has ${nv}V/${na}A tracks, the edit needs ${spec.video_tracks}V/${spec.audio_tracks}A`);
    }

    const editor = ppro.SequenceEditor.getEditor(seq);
    const frame = { width: spec.width, height: spec.height };
    const scratch = [];  // [kind, track index, start ticks] of halves to delete
    let done = 0;
    for (const c of spec.clips) {
      done++;
      ctx.progress(id, done, spec.clips.length, `${c.track} ${c.name}`);
      let step = "place";
      try {
        const placed = await placeOne(proj, seq, editor, items.get(c.path), c);
        if (!placed[c.kind]) throw new Error("placed but not found on the track");
        report.placed++;
        const idx = c.kind === "video" ? Number(c.video_track || 0) : Number(c.audio_track || 0);
        const at = time(c.start).ticks;
        // track item objects can go stale between transactions: look the clip up again for each step
        const fresh = async () => {
          const it = await itemAtTicks(seq, c.kind, idx, at);
          if (!it) throw new Error("clip vanished from its track");
          return it;
        };
        // the other half of a linked A/V item that the edit doesn't use lands on a scratch track
        if (c.kind === "video" && c.drop_audio && placed.audio) scratch.push(["audio", Number(c.audio_track), at]);
        if (c.kind === "audio" && c.drop_video && placed.video) scratch.push(["video", Number(c.video_track), at]);
        if (c.motion) { step = "framing"; await setMotion(proj, await fresh(), c.motion, frame, "editassist: framing"); report.motion++; }
        if (c.opacity !== undefined) {
          step = "opacity";
          await setParamValue(proj, await fresh(), "AE.ADBE Opacity", "Opacity", c.opacity * 100, null, "editassist: opacity");
          report.opacity++;
        }
        for (const t of c.transitions || []) {
          step = `transition ${t.type} ${t.at || "start"}`;
          try { await addTransition(proj, await fresh(), t); report.transitions++; }
          catch (e) { report.failed.push({ clip: c.name, track: c.track, start: c.start_s, step, error: String(e.message || e) }); }
        }
        for (const name of c.effects || []) {
          step = name;
          try {
            const m = await ppro.VideoFilterFactory.getMatchNames();
            const d = await ppro.VideoFilterFactory.getDisplayNames();
            const i = d.findIndex((x) => x.toLowerCase() === name.toLowerCase());
            if (i < 0) throw new Error(`no effect ${name}`);
            const comp = await ppro.VideoFilterFactory.createComponent(m[i]);
            const chain = await (await fresh()).getComponentChain();
            tx(proj, `editassist: ${name}`, () => chain.createAppendComponentAction(comp));
            report.effects = (report.effects || 0) + 1;
          } catch (e) { report.failed.push({ clip: c.name, track: c.track, start: c.start_s, step, error: String(e.message || e) }); }
        }
        if (c.rename) { step = "rename"; const it = await fresh(); tx(proj, "editassist: rename", () => it.createSetNameAction(c.rename)); }
        if (c.disabled) { step = "disable"; const it = await fresh(); tx(proj, "editassist: disable", () => it.createSetDisabledAction(true)); }
      } catch (e) {
        report.failed.push({ clip: c.name, track: c.track, start: c.start_s, step, error: String(e.message || e) });
      }
    }
    if (scratch.length) {
      try {
        const extra = [];
        for (const [kind, idx, at] of scratch) {
          const it = await itemAtTicks(seq, kind, idx, at);
          if (it) extra.push(it);
        }
        report.dropped_halves = await removeItems(proj, seq, extra, false, "editassist: drop unused A/V halves");
      } catch (e) { report.notes.push(`unused A/V halves left on the scratch tracks: ${e.message || e}`); }
    }

    const markers = await ppro.Markers.getMarkers(seq);
    for (const m of spec.markers || []) {
      try {
        tx(proj, "editassist: marker", () => markers.createAddMarkerAction(m.name || "", "Comment", T(m.time), T(m.duration || 0), m.comment || ""));
        report.markers++;
      } catch (e) { report.failed.push({ step: "marker", time: m.time, error: String(e.message || e) }); }
    }
    // spec.srt is only imported (with the media, into the bin): the 26.x API has no way to create a
    // caption track from it (overwrite/insert of the .srt item succeed and place nothing, checked on 26.3)
    if (spec.srt) report.srt = items.get(spec.srt) ? items.get(spec.srt).name : null;
    report.end = sec(await seq.getEndTime());
    report.tracks = { video: await seq.getVideoTrackCount(), audio: await seq.getAudioTrackCount() };
    try { await seq.setPlayerPosition(T(0)); } catch (e) { /* cosmetic */ }
    return report;
  },
};

return ops;
