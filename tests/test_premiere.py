"""Premiere live bridge: hub routing/auth with a fake panel, lib.js against a mocked `premierepro`
module under Node, build plans from timeline.json, and the MCP server's protocol."""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "src" / "editassist" / "premiere_uxp" / "lib.js"
MOCK = ROOT / "tests" / "premiere_mock.js"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def bridge(tmp_path, monkeypatch):
    from editassist import premiere_bridge as B

    monkeypatch.setenv("EA_PREMIERE_TOKEN_FILE", str(tmp_path / "token"))
    monkeypatch.setattr(B, "PORT", free_port())
    monkeypatch.setattr(B, "_hub", None)
    hub = B.ensure_hub()
    assert hub is not None
    yield B
    hub.server.shutdown()


class FakePanel(threading.Thread):
    """Acts like main.js: hello with the token, answers ops; NEED_LIB until lib.js is loaded."""

    def __init__(self, B, token: str, origin: str | None = None):
        super().__init__(daemon=True)
        self.B, self.token, self.origin = B, token, origin
        self.lib_hash, self.seen, self.closed = None, [], None
        self.ready = threading.Event()

    def run(self):
        from websockets.sync.client import connect

        headers = {"Origin": self.origin} if self.origin else None
        try:
            with connect(f"ws://127.0.0.1:{self.B.PORT}/premiere", additional_headers=headers) as ws:
                ws.send(json.dumps({"type": "hello", "role": "premiere", "token": self.token,
                                    "info": {"version": "26.3.2", "lib_hash": None}}))
                self.ready.set()
                for raw in ws:
                    msg = json.loads(raw)
                    self.seen.append(msg["op"])
                    if msg["op"] == "load":
                        self.lib_hash = msg["args"]["hash"]
                        ws.send(json.dumps({"id": msg["id"], "ok": True, "result": {"lib_hash": self.lib_hash}}))
                    elif msg["op"] == "ping":
                        ws.send(json.dumps({"id": msg["id"], "ok": True, "result": {"version": "26.3.2"}}))
                    elif msg.get("lib_hash") != self.lib_hash:
                        ws.send(json.dumps({"id": msg["id"], "ok": False, "code": "NEED_LIB"}))
                    elif msg["op"] == "slow":
                        ws.send(json.dumps({"type": "event", "id": msg["id"], "event": "progress", "done": 1, "total": 2}))
                        ws.send(json.dumps({"id": msg["id"], "ok": True, "result": {"echo": msg["args"]}}))
                    elif msg["op"] == "boom":
                        ws.send(json.dumps({"id": msg["id"], "ok": False, "error": "Error: Premiere refused"}))
                    else:
                        ws.send(json.dumps({"id": msg["id"], "ok": True, "result": {"op": msg["op"], "args": msg["args"]}}))
        except Exception as e:  # noqa: BLE001
            self.closed = e
            self.ready.set()


def test_hub_routes_loads_lib_once_and_forwards_progress(bridge):
    B = bridge
    panel = FakePanel(B, B.token())
    panel.start()
    panel.ready.wait(5)
    events = []
    assert B.call("sequence", {"items": False}, wait=5) == {"op": "sequence", "args": {"items": False}}
    assert panel.seen[:3] == ["sequence", "load", "sequence"]  # first call loads lib.js, then retries
    assert B.call("slow", {"x": 1}, on_event=events.append) == {"echo": {"x": 1}}
    assert events and events[0]["done"] == 1
    assert panel.seen.count("load") == 1  # same hash: not sent again
    with pytest.raises(B.BridgeError, match="Premiere refused"):
        B.call("boom")
    st = B.status()
    assert st["connected"] and st["premiere"]["version"] == "26.3.2"


def test_hub_refuses_wrong_token_and_browser_origins(bridge):
    B = bridge
    bad = FakePanel(B, "not-the-token")
    bad.start()
    bad.join(5)
    assert not B.status()["connected"]
    web = FakePanel(B, B.token(), origin="https://evil.example")
    web.start()
    web.join(5)
    assert web.closed is not None and not B.status()["connected"]
    assert B.browser_origin("null") and B.browser_origin("http://localhost:3000")
    assert not B.browser_origin(None) and not B.browser_origin("uxp://com.editassist.premiere")
    # a client without the token gets nothing either
    from websockets.sync.client import connect

    with connect(f"ws://127.0.0.1:{B.PORT}/client") as ws:
        ws.send(json.dumps({"id": "x", "op": "_status"}))
        assert json.loads(ws.recv(timeout=5))["code"] == "AUTH"


def test_no_panel_says_how_to_connect(bridge):
    B = bridge
    with pytest.raises(B.BridgeError, match="UXP Plugins > editassist"):
        B.call("info", wait=0.2)


def test_ccx_carries_the_token_and_no_lib(bridge, tmp_path):
    import zipfile

    B = bridge
    ccx = B.build_ccx(tmp_path)
    with zipfile.ZipFile(ccx) as z:
        assert sorted(z.namelist()) == ["index.html", "main.js", "manifest.json"]
        main = z.read("main.js").decode()
        manifest = json.loads(z.read("manifest.json"))
    assert B.token() in main and "__EA_TOKEN__" not in main
    assert manifest["host"]["app"] == "premierepro"
    assert manifest["requiredPermissions"]["allowCodeGenerationFromStrings"] is True
    assert "localFileSystem" not in manifest["requiredPermissions"]


# --- lib.js under Node with a mocked premierepro ---------------------------------------------------

def run_lib(tmp_path: Path, op: str, args: dict) -> dict:
    if not shutil.which("node"):
        pytest.skip("node not installed")
    a = tmp_path / f"{op}_args.json"
    a.write_text(json.dumps(args), encoding="utf-8")
    r = subprocess.run(["node", str(MOCK), str(LIB), op, str(a)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def podcast_timeline(project) -> dict:
    """V1 cam_a with mirrored A1, a b-roll on V2 from cam_b (its audio unused), music with gain on A2."""
    from editassist import timeline as T

    tl = T.new(project)
    tl["tracks"] = [
        {"kind": "video", "name": "V1", "clips": [
            {"media": "input/cam_a.mp4", "in": 0.5, "out": 2.0, "start": 0.0, "transition_in": {"type": "fade", "dur": 0.5}},
            {"media": "input/cam_a.mp4", "in": 3.0, "out": 4.8, "start": 1.5, "zoom": {"scale": 1.2, "x": 0.5, "y": 0.4},
             "transition_in": {"type": "dissolve", "dur": 0.4}, "stabilize": True}]},
        {"kind": "video", "name": "V2", "clips": [
            {"media": "input/cam_b.mp4", "in": 1.0, "out": 2.0, "start": 2.0, "opacity": 0.8}]},
        {"kind": "audio", "name": "A1", "clips": [
            {"media": "input/cam_a.mp4", "in": 0.5, "out": 2.0, "start": 0.0},
            {"media": "input/cam_a.mp4", "in": 3.0, "out": 4.8, "start": 1.5}]},
        {"kind": "audio", "name": "Music", "clips": [
            {"media": "input/music_120.wav", "in": 0, "out": 3.3, "start": 0, "gain_db": -18}]},
    ]
    tl["markers"] = [{"time": 1.5, "note": "second take"}]
    return tl


def test_plan_ticks_links_scratch_tracks_and_preset(project):
    from editassist.premiere_native import TPS, plan

    tl = podcast_timeline(project)
    p = plan(project, tl, "ep1")
    spec = p["spec"]
    assert (spec["video_tracks"], spec["audio_tracks"]) == (3, 3)  # 2 + scratch, 2 + scratch
    preset = Path(spec["preset"]).read_text(encoding="utf-8")
    assert "<InitialNumberOfVideoTracks>3<" in preset and preset.count("mTrackID") == 3
    assert "<VideoFrameRate>8467200000<" in preset and "0,0,640,360" in preset  # 30 fps
    v = [c for c in spec["clips"] if c["kind"] == "video"]
    a = [c for c in spec["clips"] if c["kind"] == "audio"]
    assert len(v) == 3 and len(a) == 1  # A1 rides with V1 (linked); music alone
    first = v[0]
    assert first["audio_track"] == 0 and first["find"] == ["video", "audio"] and not first.get("drop_audio")
    assert first["start"]["ticks"] == "0" and first["in"]["ticks"] == str(round(0.5 * TPS))
    assert int(v[1]["start"]["ticks"]) == 45 * 8467200000  # 1.5 s at 30 fps, frame-exact
    broll = next(c for c in v if c["track"] == "V2")
    assert broll["drop_audio"] and broll["audio_track"] == 2 and broll["opacity"] == 0.8
    zoomed = v[1]
    assert zoomed["motion"]["scale"] == 120.0 and zoomed["effects"] == ["Warp Stabilizer"]
    assert zoomed["motion"]["center"][1] > 180  # y 0.4: the window sits higher, so the picture moves down
    assert [t["type"] for t in zoomed["transitions"]] == ["dissolve"]
    assert first["transitions"][0]["single"] is True
    music = a[0]
    assert "gain_" in music["name"] and music["video_track"] == 2 and music["find"] == ["audio"]
    assert spec["markers"] == [{"time": 1.5, "name": "second take", "comment": "second take"}]


def test_plan_frames_crops_and_fills():
    from editassist.premiere_native import motion

    # 1920x1080 source cropped to a 9:16 window centred at x=1200 in a 1080x1920 sequence
    m = motion({"crop": {"w": 607, "h": 1080, "x": 896, "y": 0}}, 1920, 1080, 1080, 1920, 30)
    assert m["scale"] == pytest.approx(1920 / 1080 * 100, rel=1e-3)
    k = max(1080 / 607, 1920 / 1080)
    assert m["center"][0] == pytest.approx(540 - (896 + 303.5 - 960) * k, abs=0.1) and m["center"][1] == 960
    # a 4K source in a 1080p sequence fills at 50 %; a matching source needs no Motion at all
    assert motion({}, 3840, 2160, 1920, 1080, 30)["scale"] == 50.0
    assert motion({}, 1920, 1080, 1920, 1080, 30) is None
    # "Scale to frame size" on in Premiere: 100 % is the clip fitted in the frame
    assert motion({}, 3840, 2160, 1920, 1080, 30, prescaled=True) is None
    assert motion({"fit": "fit"}, 1600, 1000, 1920, 1080, 30, prescaled=True) is None
    assert motion({}, 1600, 1000, 1920, 1080, 30, prescaled=True)["scale"] == pytest.approx(1920 / 1600 / 1.08 * 100, abs=1e-3)


def test_push_in_animates_position_with_scale():
    """The render crops the growing frame at a fixed fraction, so an off-centre push-in drifts towards its
    focus while it grows: a static Position (the first build) showed a black band at the top on 26.3."""
    from editassist.premiere_native import motion

    m = motion({"zoom": {"scale": 1.4, "x": 0.5, "y": 0.4, "ramp": 2.0}}, 3840, 2160, 1920, 1080, 30)
    assert m["ramp"] == [[0, 50.0], [2.0, 70.0]]
    assert m["center_ramp"][0] == [0, [960.0, 540.0]]  # starts filling, centred
    assert m["center_ramp"][1] == [2.0, m["center"]] and m["center"][1] == pytest.approx(540 + 0.4 * 1080 * 0.1, abs=0.1)


def test_scale_to_frame_preference_is_read(tmp_path, monkeypatch):
    from editassist import premiere_native as N

    monkeypatch.setattr(N.Path, "home", classmethod(lambda cls: tmp_path))
    assert N.scale_to_frame_default() == {"video": False, "image": False}
    prefs = tmp_path / "Documents" / "Adobe" / "Premiere Pro" / "26.0" / "Profile-x" / "Adobe Premiere Pro Prefs"
    prefs.parent.mkdir(parents=True)
    prefs.write_text("<BE.Prefs.General.DefaultScaleToFrameSize>false\n</BE.Prefs.General.DefaultScaleToFrameSize>"
                     "<BE.Prefs.StillImages.ScaleToProject>true\n</BE.Prefs.StillImages.ScaleToProject>", encoding="utf-8")
    assert N.scale_to_frame_default() == {"video": False, "image": True}


def write_cube(path: Path) -> Path:
    n = 2
    lines = ['LUT_3D_SIZE 2']
    for b in range(n):
        for g in range(n):
            for r in range(n):
                lines.append(f"{min(1, r + 0.2):.3f} {g * 0.5:.3f} {b * 0.5:.3f}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_plan_renders_what_the_api_cannot_set(project):
    """26.3: Input LUT takes a registered GUID (a .cube path is accepted and ignored), and there is no
    speed setter. The build used to report luts=1 with no grade, and skipped speed clips (black)."""
    from editassist.premiere_native import plan

    write_cube(project.path("work", "color", "warm.cube"))
    tl = podcast_timeline(project)
    tl["tracks"][0]["clips"][0]["color"] = {"lut": "work/color/warm.cube"}
    tl["tracks"][1]["clips"][0]["speed"] = 2.0
    p = plan(project, tl)
    spec = p["spec"]
    assert p["skipped"] == [] and "luts" not in spec
    graded = next(c for c in spec["clips"] if c["track"] == "V1" and c["start"]["ticks"] == "0")
    assert "_lut_" in graded["name"] and Path(graded["path"]).exists()
    assert graded["in"]["ticks"] == str(round(0.5 * 254016000000))  # in 0.5 s, the copy starts at 0 (no room for a handle)
    assert graded["audio_track"] == 0  # its A1 twin follows it to the copy: still linked
    assert not any(c["kind"] == "audio" and c["track"] == "A1" for c in spec["clips"])
    sped = next(c for c in spec["clips"] if c["track"] == "V2")
    assert sped["name"].startswith("cam_b_") and Path(sped["path"]).exists()
    assert int(sped["end"]["ticks"]) - int(sped["start"]["ticks"]) == 15 * 8467200000  # 1 s of source at 2x
    assert any("LUT warm.cube" in w for w in p["warnings"]) and any("speed rendered" in w for w in p["warnings"])
    # the graded copy carries the LUT: a pure-white frame comes out with the cube's red lift and halved blue
    import subprocess as sp

    px = sp.run(["ffmpeg", "-v", "error", "-ss", "0.5", "-i", graded["path"], "-frames:v", "1", "-vf", "scale=1:1",
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    src = sp.run(["ffmpeg", "-v", "error", "-ss", "1.0", "-i", str(project.abs("input/cam_a.mp4")), "-frames:v", "1",
                  "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    assert px != src


def test_plan_puts_captions_on_a_picture_layer(project):
    """No UXP call creates a caption track from an .srt (26.3 / 26.5): captions go up as a transparent
    layer styled like the preview, the .srt is imported for an editable track."""
    from editassist.premiere_native import plan

    tl = podcast_timeline(project)
    project.path("work", "captions.json").write_text(json.dumps({"timeline": tl["name"], "style": "clean", "lines": [
        {"start": 0.2, "end": 1.4, "words": [{"word": "Olá", "start": 0.2, "end": 0.8}, {"word": "edição", "start": 0.8, "end": 1.4}]}]}),
        encoding="utf-8")
    project.path("output").mkdir(exist_ok=True)
    project.path("output", f"{tl['name']}.srt").write_text("1\n00:00:00,200 --> 00:00:01,400\nOlá edição\n", encoding="utf-8")
    p = plan(project, tl)
    spec = p["spec"]
    cap = next(c for c in spec["clips"] if c["track"] == "Captions")
    assert spec["video_tracks"] == 4 and cap["video_track"] == 2 and cap["find"] == ["video"]  # V1 V2 Captions scratch
    assert spec["srt"].endswith(".srt") and any("caption" in w for w in p["warnings"])
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=pix_fmt,codec_name", "-of", "csv=p=0",
                            cap["path"]], capture_output=True, text=True).stdout
    assert "prores" in probe and "yuva" in probe  # alpha, so the picture below shows


def test_still_images_get_their_size_at_ingest(project, tmp_path):
    from PIL import Image

    from editassist.ingest import image_size

    f = tmp_path / "s.png"
    Image.new("RGB", (1600, 1000)).save(f)
    assert image_size(f) == {"width": 1600, "height": 1000}
    assert image_size(tmp_path / "missing.png") == {}


def test_lib_build_against_mock(project, tmp_path):
    from editassist.premiere_native import plan

    spec = plan(project, podcast_timeline(project), "ep1")["spec"]
    out = run_lib(tmp_path, "build", {"spec": spec})
    rep, seq = out["result"], out["state"]["sequences"][0]
    assert rep["failed"] == [] and rep["placed"] == 4
    assert rep["transitions"] == 2 and rep["motion"] >= 1 and rep["opacity"] == 1 and rep["markers"] == 1
    tracks = {t["track"]: t["items"] for t in seq["tracks"]}
    assert len(tracks["V1"]) == 2 and len(tracks["V2"]) == 1 and len(tracks["A1"]) == 2 and len(tracks["A2"]) == 1
    assert tracks["V3"] == [] and tracks["A3"] == []  # scratch halves removed
    for item, clip in zip(tracks["V1"], [c for c in spec["clips"] if c["track"] == "V1"]):
        assert item["end"] == clip["end"]["ticks"]  # Premiere's inclusive out point trimmed back
    assert [t["name"] for t in tracks["V1"][0]["transitions"]] == ["AE.ADBE Cross Dissolve New"]  # fade in
    assert tracks["V1"][0]["transitions"][0]["single"] is True
    assert tracks["V1"][1]["transitions"][0]["name"] == "AE.ADBE Cross Dissolve New"
    names = [c["name"] for c in tracks["V1"][1]["components"]]
    assert "Warp Stabilizer" in names
    motion = next(c for c in tracks["V1"][1]["components"] if c["name"] == "Motion")
    scale = dict((p[0], p[1]) for p in motion["params"])["Scale"]
    assert scale == pytest.approx(120.0)
    assert len(out["events"]) == 4  # one progress event per clip


def test_lib_reads_and_edits_against_mock(project, tmp_path):
    from editassist.premiere_native import plan

    spec = plan(project, podcast_timeline(project), "ep1")["spec"]
    out = run_lib(tmp_path, "chain", {"ops": [
        ["build", {"spec": spec}],
        ["sequence", {}],
        ["trim", {"track": "V1", "index": 0, "end": 1.0}],
        ["move", {"track": "V2", "at": 2.5, "start": 3.0}],
        ["set_param", {"track": "V1", "index": 1, "component": "Opacity", "param": "Opacity",
                       "keyframes": [[0, 0], [0.5, 100]]}],
        ["motion", {"track": "V2", "index": 0, "scale": 150, "center": [320, 180]}],
        ["transition", {"track": "V1", "index": 1, "type": "white", "at": "end", "duration": 1}],
        ["add_marker", {"time": 2.0, "name": "check"}],
        ["remove", {"items": [{"track": "A2", "index": 0}]}],
        ["trim", {"track": "V9", "index": 0, "end": 1}],
        ["catalog", {"kind": "transition", "filter": "dip"}],
    ]})
    r = out["result"]
    seq = r[1]
    assert "error" not in seq, seq
    assert seq["name"] == "ep1" and [t["count"] for t in seq["tracks"]] == [2, 1, 0, 2, 1, 0]
    assert seq["tracks"][0]["clips"][1]["start"] == 1.5 and seq["tracks"][0]["clips"][0]["media"].endswith("cam_a.mp4")
    assert r[2]["end"] == 1.0 and r[3]["start"] == 3.0
    assert r[4] == {"keyframes": 2, "item_start": 1.5}
    assert r[5]["position"] == [0.5, 0.5] and r[5]["normalised"]
    assert r[6]["transition"] == "AE.ADBE Dip To White"
    assert r[8] == {"removed": 1, "linked_halves": 0, "ripple": False}
    assert "V9 does not exist" in r[9]["error"]
    assert r[10] == ["AE.ADBE Dip To Black", "AE.ADBE Dip To White"]
    final = {t["track"]: t["items"] for t in out["state"]["sequences"][0]["tracks"]}
    assert final["A2"] == [] and out["state"]["sequences"][0]["markers"][-1]["name"] == "check"


# --- MCP protocol ------------------------------------------------------------------------------------

def test_mcp_lists_tools_and_reports_errors(monkeypatch):
    from editassist import premiere_bridge as B
    from editassist import premiere_mcp as M

    init = M.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    assert init["serverInfo"]["name"] == "premiere" and "tools" in init["capabilities"]
    assert M.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = {t["name"] for t in M.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["tools"]}
    assert {"premiere_status", "premiere_edit", "premiere_build", "premiere_exec", "premiere_frame"} <= tools

    calls = []

    def fake_call(op, args=None, **kw):
        calls.append((op, args))
        if op == "boom":
            raise B.BridgeError("Premiere is not connected")
        return {"ok": op}

    monkeypatch.setattr(B, "call", fake_call)
    r = M.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": "premiere_edit", "arguments": {"action": "trim", "track": "V1", "index": 0, "end": 2}}})
    assert not r["isError"] and calls[-1] == ("trim", {"track": "V1", "index": 0, "end": 2})
    monkeypatch.setattr(M, "run_tool", lambda n, a: (_ for _ in ()).throw(B.BridgeError("Premiere is not connected")))
    r = M.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "premiere_sequence"}})
    assert r["isError"] and "not connected" in r["content"][0]["text"]
    with pytest.raises(LookupError):
        M.handle({"jsonrpc": "2.0", "id": 5, "method": "nope"})


def test_mcp_server_speaks_jsonrpc_over_stdio(tmp_path):
    env = {**__import__("os").environ, "EA_PREMIERE_PORT": str(free_port()),
           "EA_PREMIERE_TOKEN_FILE": str(tmp_path / "token")}
    p = subprocess.Popen(["uv", "run", "--quiet", "ea", "premiere-mcp"], cwd=ROOT, env=env, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, text=True)
    try:
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n")
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
        p.stdin.flush()
        a = json.loads(p.stdout.readline())
        b = json.loads(p.stdout.readline())
        assert a["id"] == 1 and a["result"]["serverInfo"]["name"] == "premiere"
        assert b["id"] == 2 and len(b["result"]["tools"]) >= 10
    finally:
        p.stdin.close()
        p.wait(timeout=20)


def test_frames_are_flattened_over_black(tmp_path):
    from PIL import Image

    from editassist.premiere_bridge import flatten

    f = tmp_path / "f.png"
    Image.new("RGBA", (4, 4), (200, 100, 50, 64)).save(f)  # a fade-in frame: picture at 25 % alpha
    flatten(f)
    im = Image.open(f)
    assert im.mode == "RGB" and im.getpixel((0, 0)) == (50, 25, 13)


def test_lib_relinks_offline_media_ripples_linked_pairs_and_ramps(project, tmp_path):
    """Three things the live run on 26.3 caught: a reused project item whose file was rewritten stays
    offline (silent voice track) until relinked; a ripple delete of one half of a linked clip removes it
    but leaves the gap; a push-in needs Position keyframes as well as Scale."""
    from editassist.premiere_native import plan

    spec = plan(project, podcast_timeline(project), "ep1")["spec"]
    music = next(c for c in spec["clips"] if c["track"] == "Music")
    spec["clips"][1]["motion"] = {"scale": 70.0, "center": [320, 200], "ramp": [[0, 50], [2, 70]],
                                  "center_ramp": [[0, [320, 180]], [2, [320, 200]]]}
    out = run_lib(tmp_path, "chain", {"preimported": [music["path"]], "ops": [
        ["build", {"spec": spec}],
        ["remove", {"items": [{"track": "V1", "index": 0}], "ripple": True}],
        ["frame", {"time": 1, "path": "C:\\Users\\me\\frames\\f 1.png", "width": 320}],
    ]})
    rep, rm = out["result"][0], out["result"][1]
    assert rep["failed"] == [] and music["path"] not in out["state"]["imported"]  # relinked, not imported twice
    tracks = {t["track"]: t["items"] for t in out["state"]["sequences"][0]["tracks"]}
    assert len(tracks["A2"]) == 1
    assert rm["removed"] == 2 and rm["linked_halves"] == 1 and rm["closed"] == pytest.approx(1.5)
    assert tracks["V1"][0]["start"] == "0" and tracks["A1"][0]["start"] == "0"  # the gap closed on both
    motion = next(c for c in tracks["V1"][0]["components"] if c["name"] == "Motion")
    params = {p[0]: p for p in motion["params"]}
    assert len(params["Scale"][2]) == 2 and len(params["Position"][2]) == 2  # keyframes on both
    assert params["Position"][2][1][1]["x"] == pytest.approx(0.5) and params["Position"][2][1][1]["y"] == pytest.approx(200 / 360)
    assert out["state"]["frames"] == [["C:\\Users\\me\\frames", "f 1.png"]]  # Windows separators kept


def test_export_finds_premieres_own_preset_on_both_systems(tmp_path, monkeypatch):
    from editassist import premiere_bridge as B

    monkeypatch.setattr(B.platform, "system", lambda: "Windows")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "PF"))
    monkeypatch.setenv("CommonProgramFiles", str(tmp_path / "CPF"))
    folder = tmp_path / "PF" / "Adobe" / "Adobe Premiere Pro 2026" / "MediaIO" / "systempresets" / B.H264
    folder.mkdir(parents=True)
    for n in ("00 - Match Source - High bitrate.epr", "01 - Match Source - Adaptive High Bitrate.epr"):
        (folder / n).write_text("<x/>")
    assert B.default_preset() == folder / "00 - Match Source - High bitrate.epr"
    upia = (tmp_path / "CPF" / "Adobe" / "Adobe Desktop Common" / "RemoteComponents" / "UPI" /
            "UnifiedPluginInstallerAgent" / "UnifiedPluginInstallerAgent.exe")
    upia.parent.mkdir(parents=True)
    upia.write_text("")
    assert B.installer_path() == upia

    def fake_call(op, args=None, **kw):  # the panel's export: Premiere writes the file
        Path(args["path"]).write_bytes(b"x" * 2048)
        return {"started": True, "path": args["path"], "mode": args["mode"]}

    monkeypatch.setattr(B, "call", fake_call)
    res = B.export(tmp_path / "out" / "cut.mp4", "seq")
    assert res["bytes"] == 2048 and res["preset"].endswith("High bitrate.epr")
    with pytest.raises(B.BridgeError, match="no export preset"):
        B.export(tmp_path / "x.mp4", preset=str(tmp_path / "missing.epr"))


def test_mcp_stdio_is_utf8_on_windows_code_pages(tmp_path):
    """Windows pipes default to the ANSI code page: a name outside it crashed the reply."""
    env = {**__import__("os").environ, "EA_PREMIERE_PORT": str(free_port()), "PYTHONIOENCODING": "cp1252",
           "EA_PREMIERE_TOKEN_FILE": str(tmp_path / "token")}
    p = subprocess.Popen(["uv", "run", "--quiet", "ea", "premiere-mcp"], cwd=ROOT, env=env, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE)
    try:
        msg = {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "edição 🎬", "arguments": {}}}
        p.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        p.stdin.flush()
        line = p.stdout.readline()
        assert line.endswith(b"\n") and not line.endswith(b"\r\n")
        reply = json.loads(line.decode("utf-8"))
        assert reply["id"] == 7 and reply["result"]["isError"] and "edição 🎬" in reply["result"]["content"][0]["text"]
    finally:
        p.stdin.close()
        p.wait(timeout=20)


def _frame(project, chain: str, t: float, src: str = "testsrc2=s=640x360:r=30:d=3") -> bytes:
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", src, "-vf", chain, "-ss", str(t),
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, cwd=project.dir)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_render_push_in_stays_on_its_focus(project):
    """crop keeps the frame size it saw first, so a push-in whose size changes per frame was cropped from
    the top-left corner in the preview (and in baked files), not around its focus point."""
    import numpy as np

    from editassist.videofx import clip_vfilter

    c = {"media": "input/cam_a.mp4", "in": 0, "out": 3, "zoom": {"scale": 1.4, "x": 0.5, "y": 0.5, "ramp": 1.0}}
    ramp = ",".join(clip_vfilter(project, c, 640, 360, 30, apply_color=False))
    still = ",".join(clip_vfilter(project, {**c, "zoom": {"scale": 1.4, "x": 0.5, "y": 0.5}}, 640, 360, 30, apply_color=False))
    a = np.frombuffer(_frame(project, ramp, 2.0), np.uint8).astype(int)
    b = np.frombuffer(_frame(project, still, 2.0), np.uint8).astype(int)
    assert np.abs(a - b).mean() < 8  # past the ramp: the same window as a static 1.4x zoom


def test_render_letterbox_is_transparent_over_lower_tracks(project):
    """A "fit" clip on an upper track showed opaque black bars over the track below in the preview; every
    NLE (and Premiere's build) shows the lower track there."""
    from editassist.videofx import clip_vfilter

    chain = ",".join(clip_vfilter(project, {"media": "x.png", "in": 0, "out": 1, "fit": "fit"}, 640, 360, 30,
                                  apply_color=False))
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:s=640x360:d=1", "-f", "lavfi", "-i",
                        "testsrc2=s=400x400:d=1", "-filter_complex", f"[1]{chain}[o];[0][o]overlay=format=auto",
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, cwd=project.dir)
    assert r.returncode == 0, r.stderr
    left = r.stdout[(180 * 640 + 10) * 3:(180 * 640 + 10) * 3 + 3]
    assert left[0] > 200 and left[1] < 60 and left[2] < 60  # the red base shows in the side bar
