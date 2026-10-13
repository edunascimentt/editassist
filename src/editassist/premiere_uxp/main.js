// editassist bridge panel for Premiere Pro (UXP).
//
// A thin shell: it connects to the `ea` hub on 127.0.0.1 (WebSocket), receives requests
// {id, op, args, lib_hash} and answers {id, ok, result | error}. The editing operations live in
// lib.js, which `ea` sends at runtime (op "load"), so changing them never needs a reinstall.
// Requests run one at a time, in arrival order, so transactions never interleave.
"use strict";

const ppro = require("premierepro");
const uxp = require("uxp");

const PORT = 47821;
const URL = `ws://127.0.0.1:${PORT}/premiere`;
const SHELL_VERSION = "1.0.0";
// written by `ea premiere install` (the same value is in ~/.editassist/premiere-bridge.token):
// the hub only answers a panel and clients that know it
const TOKEN = "__EA_TOKEN__";
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

let ws = null;
let lib = null;
let libHash = null;
let queue = Promise.resolve();
let retry = null;

const $ = (id) => document.getElementById(id);

function log(text, cls) {
  const box = $("log");
  if (!box) return;
  const line = document.createElement("div");
  if (cls) line.className = cls;
  const t = new Date().toTimeString().slice(0, 8);
  line.textContent = `${t} ${text}`;
  box.insertBefore(line, box.firstChild);
  while (box.childNodes.length > 200) box.removeChild(box.lastChild);
}

function setState(on, sub) {
  const el = $("state");
  if (el) {
    el.textContent = on ? "editassist: connected" : "editassist: waiting for ea";
    el.className = on ? "on" : "off";
  }
  if (sub !== undefined && $("sub")) $("sub").textContent = sub;
}

function send(msg) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg));
}

// Host objects (TickTime, Guid...) don't serialise; keep what JSON can carry.
function plain(value, depth = 0) {
  if (value === null || value === undefined) return null;
  const t = typeof value;
  if (t === "number" || t === "string" || t === "boolean") return value;
  if (t === "function") return undefined;
  if (depth > 12) return String(value);
  if (Array.isArray(value)) return value.map((v) => plain(v, depth + 1));
  if (value && typeof value.seconds === "number" && typeof value.ticks === "string") return value.seconds;
  if (value && typeof value.toString === "function" && value.constructor && value.constructor.name === "Guid") {
    return value.toString();
  }
  const out = {};
  for (const k of Object.keys(value)) {
    const v = plain(value[k], depth + 1);
    if (v !== undefined) out[k] = v;
  }
  return out;
}

const ctx = {
  log: (text) => log(String(text)),
  progress: (id, done, total, text) => send({ type: "event", id, event: "progress", done, total, text }),
};

async function hostInfo() {
  let project = null;
  let sequence = null;
  try {
    const p = await ppro.Project.getActiveProject();
    if (p) {
      project = { name: p.name, path: p.path };
      const s = await p.getActiveSequence();
      if (s) sequence = s.name;
    }
  } catch (e) { /* no project open */ }
  return {
    app: "premierepro",
    version: uxp.host && uxp.host.version,
    os: (() => { try { return require("os").platform(); } catch (e) { return null; } })(),
    shell: SHELL_VERSION,
    lib_hash: libHash,
    project,
    sequence,
  };
}

async function run(msg) {
  const { id, op, args = {}, lib_hash } = msg;
  const t0 = Date.now();
  try {
    let result;
    if (op === "ping") {
      result = await hostInfo();
    } else if (op === "load") {
      const factory = new Function("ppro", "uxp", "require", args.source);
      lib = factory(ppro, uxp, require);
      libHash = args.hash;
      result = { lib_hash: libHash, ops: Object.keys(lib).sort() };
      log(`lib loaded (${result.ops.length} ops)`);
    } else {
      if (!lib || (lib_hash && lib_hash !== libHash)) {
        send({ id, ok: false, code: "NEED_LIB", error: "operation library not loaded" });
        return;
      }
      if (op === "exec") {
        log("exec", "op");
        const fn = new AsyncFunction("ppro", "lib", "args", "ctx", "uxp", "require", args.code);
        result = await fn(ppro, lib, args.args || {}, ctx, uxp, require);
      } else {
        if (typeof lib[op] !== "function") throw new Error(`unknown op: ${op}`);
        log(op + (args && args.label ? `: ${args.label}` : ""), "op");
        result = await lib[op](args, ctx, id);
      }
    }
    send({ id, ok: true, result: plain(result), ms: Date.now() - t0 });
  } catch (err) {
    const text = err && err.stack ? String(err.stack) : String(err && err.message ? err.message : err);
    log(`${op} failed: ${String(err && err.message ? err.message : err)}`, "err");
    send({ id, ok: false, error: text, ms: Date.now() - t0 });
  }
}

function connect() {
  retry = null;
  try {
    ws = new WebSocket(URL);
  } catch (e) {
    schedule();
    return;
  }
  ws.onopen = async () => {
    setState(true, `127.0.0.1:${PORT}`);
    send({ type: "hello", role: "premiere", token: TOKEN, info: await hostInfo() });
  };
  ws.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch (e) { return; }
    if (!msg || !msg.id || !msg.op) return;
    queue = queue.then(() => run(msg));
  };
  ws.onclose = () => { setState(false, "retrying every 2 s"); schedule(); };
  ws.onerror = () => {};
}

function schedule() {
  if (!retry) retry = setTimeout(connect, 2000);
}

log(`panel ${SHELL_VERSION} started`);
connect();
