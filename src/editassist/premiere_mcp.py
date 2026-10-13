"""premiere-mcp: MCP server (stdio) that lets the agent edit a RUNNING Premiere Pro live, through the
editassist UXP panel (premiere_bridge). `.mcp.json` starts it as `uv run ea premiere-mcp`.

Dependency-free JSON-RPC 2.0 over stdin/stdout (one message per line). While this process runs it
also owns the bridge hub, so the panel in Premiere stays connected for the whole session.
Nothing may be printed to stdout except protocol messages.
"""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import traceback
from pathlib import Path

PROTOCOL = "2025-06-18"

REF = {"track": {"type": "string", "description": "V1..Vn or A1..An (as in the Premiere UI)"},
       "index": {"type": "integer", "description": "clip number on that track, 0 = first (by start time)"},
       "at": {"type": "number", "description": "or: the clip under this sequence time (seconds)"}}
SEQ = {"sequence": {"type": "string", "description": "sequence name; default the active one"}}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": True}


TOOLS = [
    {"name": "premiere_status",
     "description": "Is Premiere connected? Version, open project, sequences, active sequence. Call first.",
     "inputSchema": _obj({})},
    {"name": "premiere_sequence",
     "description": "Read a sequence: fps, frame size, playhead, every track with its clips (name, start/end "
                    "on the sequence, in/out in the source, media path, disabled) and markers. "
                    "`from`/`to` (seconds) limit the clips listed; items=false gives counts only.",
     "inputSchema": _obj({**SEQ, "from": {"type": "number"}, "to": {"type": "number"},
                          "items": {"type": "boolean"}})},
    {"name": "premiere_clip",
     "description": "One clip in detail: timing plus every component (Motion, Opacity, effects, Volume) "
                    "with its params, values and whether they are keyframed.",
     "inputSchema": _obj({**SEQ, **REF}, ["track"])},
    {"name": "premiere_project",
     "description": "Project-level actions. action: items (bin tree; bin, depth, limit) | import (paths[], bin) | "
                    "bin (name, e.g. 'editassist/b-roll') | create_sequence (name, preset .sqpreset path, bin) | "
                    "activate_sequence (sequence) | save (path for Save As) | open_project (path) | "
                    "new_project (path) | selection (clips selected in the timeline).",
     "inputSchema": _obj({"action": {"type": "string", "enum": ["items", "import", "bin", "create_sequence",
                                                                 "activate_sequence", "save", "open_project",
                                                                 "new_project", "selection"]}}, ["action"])},
    {"name": "premiere_edit",
     "description": "Change the timeline (each call = one undo step in Premiere). action:\n"
                    "- place: clips[] of {path, in, out, start, video_track, audio_track (0-based), end?, find?} "
                    "(overwrite edit; imports media not yet in the project)\n"
                    "- move: {track,index|at, start}\n- trim: {track,index|at, in?, out?, start?, end?}\n"
                    "- remove: items[] of refs, ripple (bool); linked A/V halves go too (linked=false: only that half); "
                    "`closed` = seconds the ripple actually closed (Premiere stops at clips on other sync-locked tracks)\n- enable: items[], enabled (bool)\n"
                    "- rename: ref + name\n- transition: ref + type (dissolve|dip|fade|white|<matchName>), "
                    "duration, at (start|end), alignment (0..1), single; remove=true deletes\n"
                    "- add_effect: ref + name (display name) or match_name; audio tracks use display names\n"
                    "- remove_effect: ref + component (index or name)\n"
                    "- set_param: ref + component + param + value, or keyframes [[clip seconds, value], ...]; "
                    "points as [x, y], colours as {r,g,b,a}\n"
                    "- motion: ref + scale (% of source) + center [x, y] (sequence pixels); push-in: ramp [[t, scale%], ...] "
                    "and center_ramp [[t, [x, y]], ...] (t = seconds from the clip's first frame)\n"
                    "- add_marker: time, name, comment, duration, color (0-6) | remove_markers: name?/time?\n"
                    "- playhead: time? | select: items[] (empty = clear)",
     "inputSchema": _obj({"action": {"type": "string", "enum": ["place", "move", "trim", "remove", "enable", "rename",
                                                                 "transition", "add_effect", "remove_effect",
                                                                 "set_param", "motion", "add_marker",
                                                                 "remove_markers", "playhead", "select"]},
                          **SEQ, **REF}, ["action"])},
    {"name": "premiere_catalog",
     "description": "Names Premiere accepts: kind video (effects 'matchName | display name'), audio (effect "
                    "display names) or transition (match names); filter is a substring.",
     "inputSchema": _obj({"kind": {"type": "string", "enum": ["video", "audio", "transition"]},
                          "filter": {"type": "string"}})},
    {"name": "premiere_frame",
     "description": "Render the sequence frame at `time` (seconds) as an image and return it, to SEE what "
                    "Premiere shows (framing, effects, titles). width default 960.",
     "inputSchema": _obj({**SEQ, "time": {"type": "number"}, "width": {"type": "integer"}}, ["time"])},
    {"name": "premiere_build",
     "description": "Build an editassist project's timeline.json LIVE as a new sequence in the open Premiere "
                    "project (bin 'editassist'), clip by clip, with framing, transitions, markers and captions (a "
                    "picture layer + the .srt in the bin). LUT grades, speed and whip zooms play from rendered "
                    "copies (the API can't set them). Run `ea qa` first. into_current=true builds into the "
                    "active sequence instead. Read `warnings` and `failed` in the result.",
     "inputSchema": _obj({"project": {"type": "string", "description": "editassist project name (projects/<name>)"},
                          "name": {"type": "string", "description": "sequence name (default the timeline's)"},
                          "into_current": {"type": "boolean"}}, ["project"])},
    {"name": "premiere_export",
     "description": "Render the sequence to a file. preset: an encoder preset (.epr path), default Premiere's "
                    "'Match Source - High bitrate' H.264. mode now (renders in Premiere, returns when the file is "
                    "complete), queue (Premiere's export queue) or ame (Media Encoder).",
     "inputSchema": _obj({**SEQ, "path": {"type": "string"}, "preset": {"type": "string"},
                          "mode": {"type": "string", "enum": ["now", "queue", "ame"]}}, ["path"])},
    {"name": "premiere_api",
     "description": "What the installed Premiere's UXP API offers: names on `ppro` (no name) or on ppro.<name> "
                    "(e.g. SequenceEditor, VideoClipTrackItem). Check before writing premiere_exec code.",
     "inputSchema": _obj({"name": {"type": "string"}})},
    {"name": "premiere_exec",
     "description": "Run JavaScript inside Premiere for anything the other tools don't cover. `code` is the "
                    "BODY of an async function with `ppro` (require('premierepro')), `lib` (editassist ops, "
                    "e.g. await lib.sequence({})), `args`, `ctx` (ctx.log) in scope; `return` a JSON-able "
                    "value. Changes must go through project.lockedAccess + executeTransaction. Say what you "
                    "will change before running code that edits the user's project.",
     "inputSchema": _obj({"code": {"type": "string"}, "args": {"type": "object"}}, ["code"])},
]

EDIT_OPS = {"place", "move", "trim", "remove", "enable", "rename", "transition", "add_effect", "remove_effect",
            "set_param", "motion", "add_marker", "remove_markers", "playhead", "select"}
PROJECT_OPS = {"items": "items", "import": "import", "bin": "bin", "create_sequence": "create_sequence",
               "activate_sequence": "activate_sequence", "save": "save", "open_project": "open_project",
               "new_project": "new_project", "selection": "selection"}


def _text(value) -> list[dict]:
    return [{"type": "text", "text": value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1)}]


def run_tool(name: str, args: dict) -> list[dict]:
    from . import premiere_bridge as B

    args = dict(args or {})
    if name == "premiere_status":
        st = B.status(wait=8)
        if st.get("connected"):
            try:
                st["project"] = B.call("info", wait=5)
            except B.BridgeError as e:
                st["project_error"] = str(e)
        else:
            st["next"] = B.NO_PANEL
        return _text(st)
    if name == "premiere_sequence":
        return _text(B.call("sequence", args))
    if name == "premiere_clip":
        return _text(B.call("clip", args))
    if name == "premiere_project":
        op = PROJECT_OPS[args.pop("action")]
        return _text(B.call(op, args))
    if name == "premiere_edit":
        op = args.pop("action")
        if op not in EDIT_OPS:
            raise ValueError(f"unknown action {op}")
        return _text(B.call(op, args))
    if name == "premiere_catalog":
        return _text(B.call("catalog", args))
    if name == "premiere_api":
        return _text(B.call("api", args))
    if name == "premiere_exec":
        return _text(B.exec_js(args["code"], args.get("args")))
    if name == "premiere_frame":
        path = Path(tempfile.gettempdir()) / f"ea_premiere_frame_{abs(hash((args.get('sequence'), args['time'])))}.png"
        out = B.frame(float(args["time"]), path, int(args.get("width", 960)), args.get("sequence"))
        data = base64.b64encode(out.read_bytes()).decode()
        mime = "image/png" if out.suffix.lower() == ".png" else "image/jpeg"
        return [{"type": "image", "data": data, "mimeType": mime},
                {"type": "text", "text": f"frame at {args['time']} s ({out})"}]
    if name == "premiere_export":
        return _text(B.export(Path(args["path"]), args.get("sequence"), args.get("preset"), args.get("mode", "now")))
    if name == "premiere_build":
        from .premiere_native import build
        from .project import Project

        rep = build(Project(args["project"]), args.get("name"), bool(args.get("into_current")))
        return _text(rep)
    raise ValueError(f"unknown tool {name}")


def _reply(mid, result=None, error=None) -> None:
    msg = {"jsonrpc": "2.0", "id": mid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(msg: dict) -> dict | None:
    """One JSON-RPC message -> the response object (None for notifications)."""
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None
    if method == "initialize":
        return {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", PROTOCOL),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "premiere", "version": "1.0.0"},
                "instructions": "Live control of Adobe Premiere Pro through the editassist panel. Start with "
                                "premiere_status; read before you change; every edit is one undo step in "
                                "Premiere. Use premiere_frame to look at the result."}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        p = msg.get("params") or {}
        try:
            return {"content": run_tool(p.get("name"), p.get("arguments") or {}), "isError": False}
        except SystemExit as e:
            return {"content": _text(str(e)), "isError": True}
        except Exception as e:  # noqa: BLE001  the agent reads the error and adjusts
            from . import premiere_bridge as B

            detail = str(e) if isinstance(e, (B.BridgeError, ValueError, KeyError)) else traceback.format_exc(limit=3)
            return {"content": _text(detail), "isError": True}
    raise LookupError(method)


def serve() -> int:
    from . import premiere_bridge as B

    # UTF-8 both ways and bare \n line ends: Windows pipes default to the ANSI code page (a clip named
    # "edição" broke the reply) and to \r\n
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n" if stream is sys.stdout else None)
    B.ensure_hub()  # keep the panel connected for the whole session
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _reply(None, error={"code": -32700, "message": "parse error"})
            continue
        try:
            result = handle(msg)
            if result is not None:
                _reply(msg.get("id"), result)
        except LookupError as e:
            _reply(msg.get("id"), error={"code": -32601, "message": f"method not found: {e}"})
        except Exception as e:  # noqa: BLE001
            _reply(msg.get("id"), error={"code": -32603, "message": str(e)})
    return 0
