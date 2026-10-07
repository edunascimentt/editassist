"""End-to-end checks of the `ea` tools on synthetic media. Run: uv run pytest -q"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT, duration

from editassist import timeline as T


def test_ingest_catalog(project):
    from editassist.ingest import media_by_id

    cat = media_by_id(project)
    assert {"cam_a", "cam_b", "music_120"} <= set(cat)
    assert cat["cam_a"]["fps"] == 30 and cat["cam_a"]["has_audio"]
    assert "\\" not in cat["cam_a"]["path"]  # json paths are posix on every OS


def test_silence_cut_drops_pauses_and_hesitation(project):
    from editassist.cut import speech_segments

    segs = speech_segments(project, "cam_a", min_silence=0.45, pad=0.05)
    tl = T.from_segments(project, segs)
    T.save(project, tl)
    assert T.validate(project, tl) == []
    assert len(segs) == 3  # "Olá pessoal." / "Hoje ... vídeo." / "Primeiro ... bruto." ("Hum" removed)
    assert T.length(tl) == pytest.approx(1.1 + 1.9 + 2.0, abs=0.01)  # bites + 2*pad each


def test_phrase_cut_and_captions_follow_the_edit(project):
    from editassist.cut import build, find_phrase
    from editassist.subtitles import build as subs, timeline_words

    hit = find_phrase(project, "primeiro o material")[0]
    assert hit["in"] == pytest.approx(7.5) and hit["out"] == pytest.approx(8.8)
    tl = build(project, [{"media": "cam_a", "from": "primeiro", "to": "bruto"},
                         {"media": "cam_a", "from": "ola", "to": "pessoal"}])  # accent/case-insensitive
    T.save(project, tl)
    ws = timeline_words(project, tl)
    assert [w["word"] for w in ws][:2] == ["Primeiro", "o"]
    assert ws[0]["start"] == pytest.approx(0.12, abs=0.02)  # remapped to timeline time (pad_in 0.12)
    res = subs(project, style="bold")
    assert (project.path(res["srt"])).read_text(encoding="utf-8").startswith("1\n00:00:00,1")


def test_render_with_fx_and_burned_captions(project):
    from editassist import transitions, zoom
    from editassist.cut import speech_segments
    from editassist.render import render
    from editassist.subtitles import build as subs

    T.save(project, T.from_segments(project, speech_segments(project, "cam_a")))
    zoom.punch(project)
    tl = T.load(project)
    transitions.set_at(project, [T.cut_points(tl)[0]], "dissolve", 0.3)
    transitions.fades(project, 0.3, 0.5)
    subs(project)
    out = render(project, "preview", subtitles="output/t.ass")
    assert out.exists()
    assert duration(out) == pytest.approx(T.length(T.load(project)), abs=0.15)


def test_resolve_native_luts_only_from_resolve_lut_folders(project, tmp_path, monkeypatch):
    """Resolve's SetLUT refuses a .cube outside its LUT folders (live, 21.0: our work/color cube was
    rejected, 'LUT on 0'). A grade that is just a creative LUT uses that LUT; a computed cube is
    copied into the LUT folder first."""
    from editassist import color, resolve_native

    lut_root = tmp_path / "ResolveLUT"
    creative = lut_root / "Custom" / "look.cube"
    creative.parent.mkdir(parents=True)
    creative.write_text("LUT_3D_SIZE 2\n" + "\n".join(f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)))
    monkeypatch.setattr(resolve_native, "resolve_lut_dirs", lambda: [lut_root])
    rp = _fake_resolve()
    applied = []

    def set_lut(self, node, path):
        ok = Path(path).is_relative_to(lut_root)
        if ok:
            applied.append(Path(path))
        return ok
    monkeypatch.setattr(type(rp.mp.AppendToTimeline([{"srt": 1}])[0]), "SetLUT", set_lut, raising=False)
    color.grade(project, ["cam_a"], lut=str(creative))
    color.grade(project, ["cam_b"], look="warm")
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0, "out": 1},
                                   {"media": "input/cam_b.mp4", "in": 0, "out": 1}])
    rep = resolve_native.build(project, tl, rp, "lut v1")
    assert rep["luts"] == 2 and not rep["failed"]
    assert applied[0] == creative  # the user's own LUT, not our copy of it
    assert applied[1].parent == lut_root / "editassist" / project.dir.name


def test_render_has_no_black_frames_at_cuts(project):
    """Cuts that don't fall on the output frame grid (59.94 timeline, 2x clips) used to show the black
    base for one frame at almost every cut (second real edit, 2026-10-06)."""
    from editassist.ingest import ingest
    from editassist.render import render

    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=60000/1001:d=11",
                    "-f", "lavfi", "-i", "sine=f=220:d=11", "-c:v", "libx264", "-g", "30", "-shortest",
                    str(project.path("input", "cam60.mp4"))], check=True)
    ingest(project)
    tl = T.from_segments(project, [{"media": "input/cam60.mp4", "in": 0.08, "out": 4.98},
                                   {"media": "input/cam60.mp4", "in": 5.5, "out": 7.98},
                                   {"media": "input/cam60.mp4", "in": 4.11, "out": 5.0}])
    tl["fps"] = 59.94  # 59.94 source, cuts at 4.90 and 7.38 s: between output frames
    v = T.track(tl, "V1")["clips"]
    v[1]["speed"], v[1]["out"] = 2.0, v[1]["in"] + 2 * 0.917
    v[2]["start"] = T.end(v[1])
    a = T.track(tl, "A1")["clips"]
    a[1]["out"], a[2]["start"] = a[1]["in"] + 0.917, v[2]["start"]
    T.save(project, tl)
    out = render(project, "preview")
    r = subprocess.run(["ffmpeg", "-i", str(out), "-vf", "blackdetect=d=0:pix_th=0.05", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    assert "black_start" not in r.stderr
    # and qa catches one if it comes back: blank out the frame at the 4.90 s cut
    from editassist.qa import check

    bad = project.path("output", "bad.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-vf",
                    "drawbox=c=black:t=fill:enable='between(t,4.89,4.91)'", "-c:a", "copy", str(bad)], check=True)
    issues = [i["issue"] for i in check(project, "output/bad.mp4")["issues"]]
    assert any(i.startswith("black flash at the cut 4.9") for i in issues), issues


def test_export_roundtrip_and_dissolve(project):
    import opentimelineio as otio

    from editassist import transitions
    from editassist.cut import speech_segments
    from editassist.export import export

    T.save(project, T.from_segments(project, speech_segments(project, "cam_a")))
    tl = T.load(project)
    transitions.set_at(project, [T.cut_points(tl)[1]], "dissolve", 0.4)
    res = export(project, ["resolve", "premiere", "fcpx", "aftereffects"])
    length = T.length(T.load(project))
    for key in ("resolve", "premiere", "fcpx"):
        back = otio.adapters.read_from_file(str(project.path(res["written"][key])))
        assert back.duration().to_seconds() == pytest.approx(length, abs=1 / 30 + 1e-6)
    ot = otio.adapters.read_from_file(str(project.path(res["written"]["resolve"])))
    assert any(isinstance(x, otio.schema.Transition) for x in ot.tracks[0])
    if shutil.which("node"):
        r = subprocess.run(["node", str(ROOT / "tests" / "ae_mock.js"), str(project.path(res["written"]["aftereffects"]))],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["layers"] >= 6


def test_bake_speed_keeps_timing(project):
    from editassist.bake import bake
    from editassist.cut import speech_segments

    tl = T.from_segments(project, speech_segments(project, "cam_a"))
    for tr in tl["tracks"]:
        tr["clips"][1]["speed"] = 2.0
    T.ripple(tl)
    T.save(project, tl)
    before = T.length(T.load(project))
    bake(project)
    tl = T.load(project)
    assert all("speed" not in c for tr in tl["tracks"] for c in tr["clips"])
    assert T.length(tl) == pytest.approx(before, abs=0.01)
    assert T.validate(project, tl) == []


def test_color_lut_matches_ffmpeg(project, tmp_path):
    import numpy as np

    from editassist.color import apply_ops, grade, write_lut

    ops = [{"op": "gain", "rgb": [1.2, 1.0, 0.8]}, {"op": "look", "name": "film"}]
    cube = write_lut(tmp_path / "x.cube", ops)
    src = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x90", "-frames:v", "1", str(src)], check=True)

    def raw(vf=None):
        cmd = ["ffmpeg", "-v", "error", "-i", src.name] + (["-vf", vf] if vf else []) + ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True, cwd=tmp_path).stdout, np.uint8).reshape(90, 160, 3) / 255

    a = raw()
    assert np.abs(raw(f"lut3d=file={cube.name}") - apply_ops(a, ops)).mean() < 0.005
    res = grade(project, ["cam_a"], auto=True, look="warm")
    assert project.path(res["cam_a"]["lut"]).exists()


def test_beats_on_click_track(project):
    from editassist.beats import detect
    from editassist.project import read_json

    r = detect(project, "music_120")
    assert r["bpm"] == pytest.approx(120, abs=1.5)
    b = read_json(project.path("work", "beats", "music_120.json"))
    err = [abs(t / 0.5 - round(t / 0.5)) * 0.5 for t in b["beats"]]
    assert sorted(err)[len(err) // 2] < 0.03
    assert all(round(t / 0.5) % 4 == 0 for t in b["downbeats"][:4])


def test_sync_finds_camera_offset(project):
    from editassist.sync import sync

    r = sync(project, "cam_a", ["cam_b"])["cam_b"]
    assert r["offset"] == pytest.approx(-1.5, abs=0.01)


def test_diarize_by_tracks(project, tmp_path):
    from conftest import ff

    from editassist.diarize import by_tracks
    from editassist.ingest import ingest

    # mic_x hears words before 5 s loudly, mic_y after
    src = project.path("input", "cam_a.mp4")
    ff("-i", str(src), "-af", "volume='if(lt(t,5),1,0.1)':eval=frame", "-vn", str(project.path("input", "mic_x.wav")))
    ff("-i", str(src), "-af", "volume='if(lt(t,5),0.1,1)':eval=frame", "-vn", str(project.path("input", "mic_y.wav")))
    ingest(project)
    r = by_tracks(project, "cam_a", {"X": "mic_x", "Y": "mic_y"})
    t = json.loads(project.path("work", "transcripts", "cam_a.json").read_text(encoding="utf-8"))
    for s in t["segments"]:
        for w in s["words"]:
            assert w["speaker"] == ("X" if w["start"] < 5 else "Y")
    assert r["words_per_speaker"]["X"] == 6


def test_chapters_rules(project):
    from editassist.chapters import chapters
    from editassist.cut import speech_segments

    T.save(project, T.from_segments(project, speech_segments(project, "cam_a")))
    r = chapters(project, [{"time": 1, "title": "A"}, {"time": 3, "title": "B"}])
    assert any("00:00" in p for p in r["problems"]) and any(">= 10s" in p for p in r["problems"])
    assert T.load(project)["markers"]


def test_thumbnail_compose(project):
    from editassist.thumbnail import compose

    r = compose(project, "Teste *rápido* aqui", media="cam_a", t=2.0)
    assert project.path(r["thumbnail"]).stat().st_size < 2_000_000


@pytest.mark.skipif(not (ROOT / "remotion" / "node_modules").exists(), reason="remotion deps not installed")
def test_remotion_lower_third(project):
    from editassist.motion import render_motion

    T.save(project, T.new(project))
    r = render_motion(project, "LowerThird", {"name": "Teste", "role": "CI"}, seconds=1)
    assert project.path(r["path"]).exists()


def test_resolve_mcp_launcher_paths(monkeypatch, tmp_path):
    from editassist import resolve_mcp

    monkeypatch.setenv("DAVINCI_RESOLVE_MCP_INSTALL_ROOT", str(tmp_path))
    assert resolve_mcp.install_root() == tmp_path
    assert resolve_mcp.serve([]) == 1  # not installed there: clean error, nothing on stdout
    cfg = json.loads((ROOT / ".mcp.json").read_text())
    assert cfg["mcpServers"]["davinci-resolve"]["args"][-1] == "resolve-mcp"


def test_editing_memory_tiers(monkeypatch, tmp_path):
    import editassist.project as P

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(P.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("EA_MEMORY_DIR", raising=False)
    local = tmp_path / "repo_memory"
    monkeypatch.setattr(P, "LOCAL_MEMORY", local)
    # no memory-os: falls back to the gitignored repo folder
    assert P.memory_dir() == local
    P.init_memory()
    (local / "preferences.md").write_text("- Silence cut min 0.3s (2026-10-02)\n", encoding="utf-8")
    # memory-os appears later: taste moves to the private global tier, written content carried over
    (home / ".memory-os" / "memory").mkdir(parents=True)
    (home / ".memory-os" / "memory" / "_index.md").write_text("# index\n", encoding="utf-8")
    res = P.init_memory()
    dst = home / ".memory-os" / "memory" / "editassist"
    assert P.memory_dir() == dst and "preferences.md" in res["migrated"]
    assert "0.3s" in (dst / "preferences.md").read_text(encoding="utf-8")
    assert "editassist/" in (home / ".memory-os" / "memory" / "_index.md").read_text(encoding="utf-8")


def test_install_memory_os_from_vendor(monkeypatch, tmp_path):
    import editassist.project as P

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(P.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("EA_MEMORY_DIR", raising=False)
    monkeypatch.setattr(P, "LOCAL_MEMORY", tmp_path / "repo_memory")
    res = P.install_memory_os(run_installer=False)
    store = home / ".memory-os"
    assert (store / "bin" / "memory-os").exists() and (store / "CLAUDE.md").exists()
    assert (store / "memory" / "me.md").exists() and (store / "memory" / "journal" / "log.md").exists()
    assert P.memory_dir() == store / "memory" / "editassist" and res["editing_memory"]["created"]
    # re-running refreshes the system files and never touches what the user wrote
    (store / "memory" / "me.md").write_text("me\n", encoding="utf-8")
    P.install_memory_os(run_installer=False)
    assert (store / "memory" / "me.md").read_text(encoding="utf-8") == "me\n"


def test_launch_scaffold_audit_and_music_tools(project, media_dir):
    from editassist import launch as L

    r = L.new(project, seconds=10, install=False)
    d = project.path(r["launch"])
    assert (d / "src" / "beats.json").exists() and (d / "public" / "fonts" / "Brand-Black.ttf").exists()
    res = L.audit(project)
    assert res["ok"], res["issues"]
    # planted problems are caught
    beats = json.loads((d / "src" / "beats.json").read_text(encoding="utf-8"))
    beats["beats"][0]["title"] = [[{"t": "BOOK A DEMO NOW"}], [{"t": "press ⌘K", "accent": True}, {"t": " now", "accent": True}]]
    beats["beats"][2]["from"] += 5
    (d / "src" / "beats.json").write_text(json.dumps(beats), encoding="utf-8")
    issues = {(i["area"], i["severity"]) for i in L.audit(project)["issues"]}
    assert ("copy", "warn") in issues and ("storyboard", "error") in issues and ("font", "error") in issues
    # music: bars detected, stretch lands on whole bars, two-pass loudness
    music = d / "public" / "audio" / "music.wav"
    shutil.copy(media_dir / "music_120.wav", music)
    L._place_music(project, music, -6, -9)
    out = L.stretch_music(project, 31)
    assert abs(out["duration"] - 31) <= out["bar_seconds"] + 0.1
    norm = L._loudnorm(music, d / "public" / "audio" / "n.mp3")
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(norm), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    import re
    assert abs(float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1]) - L.LUFS) < 1.0


def test_launch_template_typechecks(tmp_path):
    nm = ROOT / "remotion" / "node_modules"
    if not (nm.exists() and shutil.which("npx")):
        pytest.skip("remotion deps not installed")
    dst = tmp_path / "launch"
    shutil.copytree(ROOT / "templates" / "launch", dst)
    try:
        (dst / "node_modules").symlink_to(nm, target_is_directory=True)
    except OSError:
        pytest.skip("cannot symlink node_modules here (Windows without developer mode)")
    r = subprocess.run([shutil.which("npx"), "tsc", "-p", "."], cwd=dst, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_keys_written_masked_and_private(tmp_path, monkeypatch):
    import os
    import platform

    from editassist import keys as K

    env = tmp_path / ".env"
    env.write_text("# my comment\nPEXELS_API_KEY=old\nOTHER=1\n", encoding="utf-8")
    monkeypatch.setattr(K, "ENV", env)
    r = K.set_key("PEXELS_API_KEY", "  sk-test-1234567890  \n")
    assert r["value"] == "…7890" and "1234567890" not in json.dumps(r)
    text = env.read_text(encoding="utf-8")
    assert "# my comment" in text and "OTHER=1" in text and "PEXELS_API_KEY=sk-test-1234567890" in text and "old" not in text
    K.set_key("HF_TOKEN", "hf_abcdefghijkl")
    rows = {x["key"]: x for x in K.status()}
    assert rows["HF_TOKEN"]["set"] and rows["HF_TOKEN"]["source"] == ".env" and rows["HF_TOKEN"]["value"] == "…ijkl"
    if platform.system() != "Windows":
        assert oct(os.stat(env).st_mode)[-3:] == "600"


def _bash() -> str | None:
    # on Windows `bash` on PATH is often WSL's launcher, which can't see Windows paths; Claude Code
    # runs hooks with Git Bash there, so the test does too
    git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
    return (str(git_bash) if git_bash.exists() else None) if os.name == "nt" else shutil.which("bash")


def test_first_run_hook(tmp_path):
    bash = _bash()
    if not bash:
        pytest.skip("bash not available")
    script = ROOT / ".claude" / "first-run-check.sh"
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    r = subprocess.run([bash, str(script)], env=env, capture_output=True, text=True, encoding="utf-8")
    d = json.loads(r.stdout)
    assert "editassist-setup" in d["hookSpecificOutput"]["additionalContext"]
    (tmp_path / ".editassist").mkdir()
    (tmp_path / ".editassist" / "setup.json").write_text('{"status": "done"}')
    assert subprocess.run([bash, str(script)], env=env, capture_output=True, text=True).stdout == ""


def test_bite_padding_stops_at_neighbour_words(project):
    from editassist.cut import resolve_segments

    # "Hoje" starts 3.0; "pessoal." ends 1.5: a 2 s pad must stop at the neighbours, not swallow them
    seg = resolve_segments(project, [{"media": "cam_a", "from": "hoje", "to": "video", "pad": 2.0}])[0]
    assert seg["in"] == pytest.approx(1.52) and seg["out"] == pytest.approx(5.98)  # "Hum" starts at 6.0


def test_ntsc_export_writes_fcpx_and_bakes_ducking(project):
    import re

    from editassist.export import exact_fps, export

    assert exact_fps(23.976) == pytest.approx(24000 / 1001) and exact_fps(30) == 30
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.4, "out": 4.9}])
    tl["fps"] = 23.976
    T.track(tl, "Music", "audio")["clips"] = [{"media": "input/music_120.wav", "in": 0, "out": 4.5, "start": 0,
                                                "gain_db": -6, "duck": True}]
    T.save(project, tl)
    res = export(project, ["resolve", "fcpx"])
    assert "fcpx" in res["written"], res["warnings"]  # NTSC rates used to crash the fcpx adapter
    xml = project.path(res["written"]["fcpx"]).read_text(encoding="utf-8")
    assert 'frameDuration="1001/24000s"' in xml
    num, den = re.search(r'<sequence duration="(\d+)/(\d+)s"', xml).groups()
    assert int(num) / int(den) == pytest.approx(T.length(tl), abs=1 / 23.976)
    stem = project.path(res["written"]["music_stem"])  # NLEs don't duck: the bed comes pre-ducked
    assert duration(stem) == pytest.approx(T.length(tl), abs=0.05)
    assert T.load(project)["tracks"][-1]["clips"][0]["duck"]  # timeline.json itself is untouched


def _fake_resolve():
    """Just enough of Resolve's scripting API (media pool, bins, AppendToTimeline) for resolve_native."""

    class Item:
        def __init__(self, path, fps):
            self.props = {"File Path": str(path), "FPS": fps}

        def GetClipProperty(self, k=None):
            return self.props.get(k)

        def SetClipProperty(self, k, v):
            self.props[k] = float(v)
            return True

    class Folder:
        def __init__(self, name):
            self.name, self.clips, self.subs = name, [], []

        def GetName(self):
            return self.name

        def GetClipList(self):
            return self.clips

        def GetSubFolderList(self):
            return self.subs

    class TlItem:
        def __init__(self, info):
            self.info = info

        def SetLUT(self, node, path):
            return True

        def SetProperty(self, k, v):
            if k in ("ZoomX", "ZoomY"):
                self.info[k] = v
                return True
            return False  # Resolve 21.0: no audio volume

    class Tl:
        def __init__(self):
            self.tracks = {"video": 1, "audio": 1, "subtitle": 0}
            self.items = []

        def SetSetting(self, k, v):
            return True

        def GetStartFrame(self):
            return 86400

        def GetEndFrame(self):
            return max(i["recordFrame"] + (i["endFrame"] - i["startFrame"]) * 30 / i["_fps"] for i in self.items)

        def GetTrackCount(self, kind):
            return self.tracks[kind]

        def AddTrack(self, kind, *a):
            self.tracks[kind] += 1
            return True

        def SetTrackName(self, *a):
            return True

    class MP:
        def __init__(self):
            self.root = Folder("Master")
            self.cur = self.root
            self.tl = None

        def GetRootFolder(self):
            return self.root

        def AddSubFolder(self, parent, name):
            f = Folder(name)
            parent.subs.append(f)
            return f

        def SetCurrentFolder(self, f):
            self.cur = f
            return True

        def ImportMedia(self, paths):
            items = [Item(p, 30.0) for p in paths]
            self.cur.clips += items
            return items

        def CreateEmptyTimeline(self, name):
            self.tl = Tl()
            return self.tl

        def AppendToTimeline(self, infos):
            info = dict(infos[0]) if isinstance(infos[0], dict) else {"srt": True}
            if "mediaPoolItem" in info:
                info["_fps"] = info["mediaPoolItem"].GetClipProperty("FPS")
                self.tl.items.append(info)
            return [TlItem(info)]

    class RP:
        def __init__(self):
            self.mp = MP()

        def GetMediaPool(self):
            return self.mp

        def SetCurrentTimeline(self, t):
            return True

    return RP()


def test_resolve_native_build_with_fake_api(project):
    from editassist import resolve_native

    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.5, "out": 1.5},
                                   {"media": "input/cam_a.mp4", "in": 3.0, "out": 4.8}])
    tl["fps"] = 15  # cam_a is 30 fps: speed 0.5 at a 15 fps timeline = conform (S&Q)
    v = T.track(tl, "V1")["clips"]
    v[1]["speed"] = 0.5
    v[1]["out"] = v[1]["in"] + 0.9
    T.track(tl, "A1")["clips"][0]["gain_db"] = -3
    rp = _fake_resolve()
    rep = resolve_native.build(project, tl, rp, "x v1")
    items = rp.mp.tl.items
    assert rep["placed"] == len(items) == 4 and not rep["failed"]
    assert rep["speed_conformed"] == 1
    slow = [i for i in items if i["mediaType"] == 1][1]
    assert slow["mediaPoolItem"].GetClipProperty("FPS") == 15  # its own conformed pool copy
    assert slow["startFrame"] == 90 and slow["endFrame"] == 117  # frames of the 30 fps file
    assert slow["recordFrame"] == 86400 + round(1.0 * 15)
    # Resolve 21.0 can't set clip volume: the -3 dB clip plays a rendered copy at that level
    assert rep["gain_baked"] == 1 and not any("dB" in n for n in rep["notes"])
    quiet = [i for i in items if i["mediaType"] == 2][0]
    wav = Path(quiet["mediaPoolItem"].GetClipProperty("File Path"))
    assert wav.name.startswith("gain_") and wav.exists()
    assert quiet["startFrame"] == 0 and T.track(tl, "A1")["clips"][0]["media"] == "input/cam_a.mp4"


def test_resolve_native_speed_up_and_zoom(project, monkeypatch):
    """2x in a 30 fps timeline = a copy conformed to 60 fps (no bake), in its own bin; slow-motion and
    fast copies of one file don't share a pool item; a centred punch-in sets ZoomX/ZoomY."""
    from editassist import resolve_native

    assert resolve_native.conform_rate(59.94, 2.0) == 119.88
    assert resolve_native.conform_rate(59.94, 0.4) == 23.976
    assert resolve_native.conform_rate(59.94, 1.5) is None  # 89.91 is no conform rate
    rp = _fake_resolve()
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.0, "out": 1.0},
                                   {"media": "input/cam_a.mp4", "in": 2.0, "out": 4.0},
                                   {"media": "input/cam_a.mp4", "in": 5.0, "out": 6.0}])
    v = T.track(tl, "V1")["clips"]
    v[0]["zoom"] = {"scale": 1.2, "x": 0.5, "y": 0.5, "ramp": 0}
    v[1]["speed"] = 2.0
    v[1]["start"] = 1.0
    v[2]["speed"] = 0.8  # 24 fps
    v[2]["start"] = 2.0
    rep = resolve_native.build(project, tl, rp, "fast v1")
    vids = [i for i in rp.mp.tl.items if i["mediaType"] == 1]
    assert rep["speed_conformed"] == 2 and rep["zooms"] == 1 and not rep["failed"]
    assert [i["mediaPoolItem"].GetClipProperty("FPS") for i in vids] == [30.0, 60.0, 24.0]
    assert vids[0]["ZoomX"] == vids[0]["ZoomY"] == 1.2
    assert vids[1]["startFrame"] == 60 and vids[1]["endFrame"] == 120  # frames of the 30 fps file
    bins = {f.GetName() for f in rp.mp.root.subs[0].subs}
    assert bins == {"speed 60", "speed 24"}
    tl["tracks"][0]["clips"][1]["speed"] = 1.5  # 45 fps: no conform rate, must ask for a bake
    with pytest.raises(SystemExit, match="bake"):
        resolve_native.build(project, tl, _fake_resolve(), "fast v2")


def test_scene_overview_sheets(project):
    from PIL import Image

    from editassist.scenes import detect

    detect(project, frames=3)
    sheet = Image.open(project.path("work", "frames", "overview_00.jpg"))
    assert sheet.height == 2 * 320 and sheet.width == 3 * 568  # cam_a + cam_b, 3 moments each at 16:9


def test_camera_log_metadata(tmp_path):
    from editassist.ingest import camera_meta

    f = tmp_path / "C0001.MP4"
    f.write_bytes(b"\0" * 2048 + b'<VideoFrame captureFps="59.94p" formatFps="59.94p"/>'
                  b'<Item name="CaptureGammaEquation" value="s-log3-cine"/>'
                  b'<Item name="CaptureColorPrimaries" value="s-gamut3-cine"/>')
    assert camera_meta(f) == {"gamma": "s-log3-cine", "primaries": "s-gamut3-cine", "capture_fps": 59.94, "log": True}
    (tmp_path / "plain.mp4").write_bytes(b"\0" * 64)
    assert camera_meta(tmp_path / "plain.mp4") == {}


def test_ducked_music_runs_past_the_last_word(project):
    import numpy as np

    from editassist.beats import load_audio
    from editassist.render import render

    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.4, "out": 1.6}])
    T.track(tl, "V1")["clips"][0]["out"] = 6.4  # picture runs on 4.8 s after the dialogue
    T.track(tl, "Music", "audio")["clips"] = [{"media": "input/music_120.wav", "in": 0, "out": 6.0, "start": 0,
                                                "duck": True}]
    T.save(project, tl)
    out = render(project, "preview")
    y = load_audio(str(out))
    tail = y[int(4 * 22050):int(5.5 * 22050)]
    assert len(y) / 22050 == pytest.approx(6.0, abs=0.15)
    assert 20 * np.log10(np.sqrt(np.mean(tail ** 2)) + 1e-9) > -40  # music still playing after the last word


def test_validate_normalizes_symlinked_media_paths(project, tmp_path):
    """Ingest catalogues a symlink in input/ by its target; a timeline written with the input/ path
    silently lost its transcript (empty captions), grade and duration checks."""
    from editassist.ingest import ingest

    outside = tmp_path / "card" / "clip.mp4"
    outside.parent.mkdir()
    shutil.copy(project.path("input", "cam_a.mp4"), outside)
    (project.path("input", "linked.mp4")).symlink_to(outside)
    ingest(project)
    tl = T.from_segments(project, [{"media": "input/linked.mp4", "in": 0, "out": 1}])
    assert T.normalize_media(project, tl) == 2  # V1 + A1
    assert T.track(tl, "V1")["clips"][0]["media"] == outside.resolve().as_posix()
    assert T.normalize_media(project, tl) == 0


def test_color_unknown_media_id_is_an_error(project):
    from editassist import color

    with pytest.raises(SystemExit, match="no video media with id"):
        color.grade(project, ["cam_a cam_b"], look="warm")  # zsh: unquoted $ids is one word


def test_resolve_native_clips_butt_without_frame_holes(project):
    """Source and record frames were rounded separately: a 4.90 s clip from 2.08-6.98 of a 59.94 file
    took 293 source frames but the next clip started 294 frames later, a black frame at 10 cuts of
    the first client reel (2026-10-06). The source span now follows the record span."""
    from editassist import resolve_native
    from editassist.ingest import ingest

    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=60000/1001:d=11",
                    "-f", "lavfi", "-i", "sine=f=220:d=11", "-c:v", "libx264", "-shortest",
                    str(project.path("input", "cam60.mp4"))], check=True)
    ingest(project)
    tl = T.from_segments(project, [{"media": "input/cam60.mp4", "in": 2.08, "out": 6.98},
                                   {"media": "input/cam60.mp4", "in": 7.50, "out": 9.98},
                                   {"media": "input/cam60.mp4", "in": 0.37, "out": 1.55}])
    tl["fps"] = 59.94
    rp = _fake_resolve()
    resolve_native.build(project, tl, rp, "holes v1")
    vids = [i for i in rp.mp.tl.items if i["mediaType"] == 1]
    for a, b in zip(vids, vids[1:]):
        assert a["endFrame"] - a["startFrame"] == b["recordFrame"] - a["recordFrame"]


def test_level_sets_gains_from_measured_loudness(project):
    """Fixed dB guesses left a mastered music bed louder than a raw lav voice (first client reel):
    each clip is measured and brought to its role's target."""
    from editassist.ingest import ingest
    from editassist.levels import level, segment_lufs

    ingest(project)
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.0, "out": 6.0}])
    music = next(m["path"] for m in json.loads(project.path("work", "media.json").read_text()).values()
                 if m["path"].endswith("music_120.wav"))
    T.track(tl, "Music", "audio")["clips"].append({"media": music, "in": 0, "out": 6, "start": 0, "duck": True,
                                                   "gain_db": -12})
    T.save(project, tl)
    rep = level(project)
    tl = T.load(project)
    voice, bed = T.track(tl, "A1")["clips"][0], T.track(tl, "Music")["clips"][0]
    assert {c["role"] for c in rep["clips"]} == {"dialogue", "bed"}
    assert segment_lufs(project, voice) + voice["gain_db"] == pytest.approx(-16, abs=0.2)
    assert segment_lufs(project, bed) + bed["gain_db"] == pytest.approx(-30, abs=0.2)


def test_shake_marks_only_handheld_clips(project):
    from editassist.ingest import ingest
    from editassist.render import build_cmd
    from editassist.shake import mark

    still = "testsrc2=s=480x300:r=30,trim=end_frame=1,loop=loop=200:size=1,setpts=N/30/TB"
    for name, crop in (("pan.mp4", "x='t*20':y=40"),  # smooth camera move: not shake
                       ("shaky.mp4", "x='40+30*random(1)':y='30+25*random(2)'")):
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", still, "-t", "4",
                        "-vf", f"crop=320:180:{crop}", "-c:v", "libx264", str(project.path("input", name))], check=True)
    ingest(project)
    tl = T.from_segments(project, [{"media": "input/pan.mp4", "in": 0, "out": 3},
                                   {"media": "input/shaky.mp4", "in": 0, "out": 3}], with_video=True)
    T.save(project, tl)
    rep = mark(project)
    by = {c["media"]: c for c in rep["clips"]}
    assert by["shaky.mp4"]["stabilize"] and not by["pan.mp4"]["stabilize"]
    clips = T.track(T.load(project), "V1")["clips"]
    assert [c.get("stabilize", False) for c in clips] == [False, True]
    tl = T.load(project)
    T.track(tl, "V1")["clips"][1]["stabilize"] = False  # a motion graphic: user says leave it
    T.save(project, tl)
    assert mark(project)["marked"] == 0 and T.track(T.load(project), "V1")["clips"][1]["stabilize"] is False
    tl["tracks"][0]["clips"][1]["stabilize"] = True
    T.save(project, tl)
    fc = project.path("work", "render_filter.txt")
    build_cmd(project, T.load(project), project.path("output", "x.mp4"))
    assert fc.read_text().count("deshake") == 1


def test_resolve_native_builds_inside_template_timeline(project):
    """Subtitle style can't be set through Resolve's API but lives on the track: building inside an
    emptied copy of the user's styled timeline keeps it. Each build also imports a fresh .srt copy
    (a pool .srt keeps the text of its first import)."""
    from editassist import resolve_native

    rp = _fake_resolve()
    styled = type(rp.mp.CreateEmptyTimeline("x"))()
    styled.name, styled.items = "Reel v1", [{"old": True}]
    styled.tracks["subtitle"] = 1
    copies = []

    def dup(self, name):
        t = type(self)()
        t.name, t.items, t.tracks = name, list(self.items), dict(self.tracks)
        copies.append(t)
        return t
    cls = type(styled)
    cls.GetName = lambda self: self.name
    cls.DuplicateTimeline = dup
    cls.GetItemListInTrack = lambda self, kind, i: [x for x in self.items if x.get("old")] if kind == "video" else []
    cls.DeleteClips = lambda self, items, ripple: [self.items.remove(x) for x in items] or True
    rp.GetTimelineCount = lambda: 1
    rp.GetTimelineByIndex = lambda i: styled
    rp.GetName = lambda: "proj"
    real_append = type(rp.mp).AppendToTimeline

    def append(self, infos):
        self.tl = copies[-1]
        return real_append(self, infos)
    type(rp.mp).AppendToTimeline = append
    srt = project.path("output", "t.srt")
    srt.parent.mkdir(exist_ok=True)
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nOi\n", encoding="utf-8")
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0, "out": 1}])
    try:
        rep = resolve_native.build(project, tl, rp, "Reel v2", srt=srt, template="Reel v1")
    finally:
        type(rp.mp).AppendToTimeline = real_append
    built = copies[-1]
    assert built.name == "Reel v2" and not any(x.get("old") for x in built.items)
    assert styled.items == [{"old": True}]  # the user's timeline is untouched
    assert rep["placed"] == 2 and rep["subtitles"]
    assert list(project.path("work", "baked").glob("t *.srt"))


def test_level_uses_the_voice_side_of_a_dual_mic_recording(project):
    """In-car take: lavalier on L, car mic on R. Measured as stereo the road noise counted as voice
    (voice turned down under the noise) and played as stereo the voice sat in one ear. `ea level` must
    pick the voice side, measure only it, and bake / render must play it on both sides."""
    from editassist.bake import gain_copies
    from editassist.ingest import ingest
    from editassist.levels import level, segment_lufs

    words = "0.3*sin(2*PI*300*t)*gt(sin(2*PI*1.2*t)\\,0)"
    for name, expr in (("car.wav", f"{words}|1.2*(random(0)-0.5)"),  # voice L, louder steady noise R
                       ("both.wav", f"{words}|{words}")):              # real stereo: leave it
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc={expr}:s=48000:d=6",
                        str(project.path("input", name))], check=True)
    ingest(project)
    tl = T.from_segments(project, [{"media": "input/car.wav", "in": 0, "out": 6},
                                   {"media": "input/both.wav", "in": 0, "out": 6}], with_video=False)
    T.save(project, tl)
    level(project)
    car, both = T.track(T.load(project), "A1")["clips"]
    assert car["channel"] == "L" and "channel" not in both
    assert segment_lufs(project, car) + car["gain_db"] == pytest.approx(-16, abs=0.3)
    assert segment_lufs(project, {**car, "channel": "stereo"}) > segment_lufs(project, car) + 3  # noise excluded

    baked, _ = gain_copies(project, T.load(project))
    out = project.abs(T.track(baked, "A1")["clips"][0]["media"])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "f32le", "-"], capture_output=True).stdout
    import numpy as np
    x = np.frombuffer(raw, np.float32).reshape(-1, 2)
    assert np.allclose(x[:, 0], x[:, 1])  # the voice on both sides, no car noise in one ear
