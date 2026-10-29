"""End-to-end checks of the `ea` tools on synthetic media. Run: uv run pytest -q"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
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


def test_resolve_native_keeps_the_lut_on_baked_clips(project, tmp_path, monkeypatch):
    """`ea bake` repoints a zoomed clip at work/baked/<file>.mp4 (ungraded unless --color); the native
    build looked the grade up by that new path and placed 43 of 48 clips of a recap WITHOUT their LUT
    (2026-10-13). The grade follows the clip's original media; a clip baked with --color gets none."""
    from editassist import bake, color, resolve_native

    lut_root = tmp_path / "ResolveLUT"
    creative = lut_root / "Custom" / "look.cube"
    creative.parent.mkdir(parents=True)
    creative.write_text("LUT_3D_SIZE 2\n" + "\n".join(f"{r} {g} {b}" for b in (0, 1) for g in (0, 1) for r in (0, 1)))
    monkeypatch.setattr(resolve_native, "resolve_lut_dirs", lambda: [lut_root])
    color.grade(project, ["cam_a"], lut=str(creative))
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0, "out": 1}])
    T.track(tl, "V1")["clips"][0]["zoom"] = {"scale": 1.1, "x": 0.5, "y": 0.5, "ramp": 1.0}
    T.save(project, tl)
    bake.bake(project)
    tl = T.load(project)
    assert T.track(tl, "V1")["clips"][0]["media"].startswith("work/baked/")
    rp = _fake_resolve()
    applied = []
    monkeypatch.setattr(type(rp.mp.AppendToTimeline([{"srt": 1}])[0]), "SetLUT",
                        lambda self, node, path: applied.append(Path(path)) or True, raising=False)
    rep = resolve_native.build(project, tl, rp, "baked v1")
    assert rep["luts"] == 1 and applied == [creative]

    tl2 = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 1, "out": 2}])
    T.track(tl2, "V1")["clips"][0]["zoom"] = {"scale": 1.1, "x": 0.5, "y": 0.5, "ramp": 1.0}
    T.save(project, tl2)
    bake.bake(project, color=True)  # grade burned in: no LUT on top
    applied.clear()
    rep = resolve_native.build(project, T.load(project), _fake_resolve(), "graded v1")
    assert rep["luts"] == 0


def test_resolve_export_always_builds_natively(project, monkeypatch, tmp_path):
    """Resolve 21.0 suddenly ACCEPTED our OTIO (2026-10-13) and that route was worse than the native
    build: it imported every clip again into whatever bin the user had selected (duplicates of clips
    already in their bins), applied no LUT (work/color cubes are outside Resolve's LUT folders) and
    dropped every clip gain (dialogue 8-12 dB too quiet). `--open` now always builds natively."""
    import types

    from editassist import export

    rp = _fake_resolve()
    calls = []
    rp.mp.ImportTimelineFromFile = lambda *a, **k: calls.append(a) or object()
    rp.GetName = lambda: "client"
    rp.GetTimelineByIndex = lambda i: None

    class PM:
        def SaveProject(self):
            return True

        def GetCurrentProject(self):
            return rp

    app = types.SimpleNamespace(GetProjectManager=lambda: PM())
    monkeypatch.setitem(sys.modules, "DaVinciResolveScript", types.SimpleNamespace(scriptapp=lambda n: app))
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0, "out": 1}])
    T.track(tl, "A1")["clips"][0]["gain_db"] = 9
    otio = tmp_path / "x.otio"
    otio.write_text("{}")
    res = export.resolve_import(project, tl, otio, into_current=True)
    assert not calls
    assert res.startswith("ok (built natively"), res


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


def test_beats_takes_a_library_file_path(project, tmp_path):
    """`ea beats <p> <file>` on a track from the music library crashed with a bare KeyError: it only took
    media ids. A file path is now registered as music and analysed."""
    import shutil
    from editassist.beats import detect
    from editassist.ingest import media_by_id

    lib = tmp_path / "Library Track.wav"
    shutil.copy(project.abs(media_by_id(project)["music_120"]["path"]), lib)
    r = detect(project, str(lib))
    assert r["bpm"] == pytest.approx(120, abs=1.5)
    assert r["media"] in media_by_id(project)
    with pytest.raises(SystemExit, match="unknown media"):
        detect(project, "no_such_id")


def test_beats_report_the_natural_end_before_trailing_silence(tmp_path):
    """A track whose file ran 3 s of digital silence past its last note left a silent end card when the
    builder lined the file's end up with the video's end (2026-10-09)."""
    from editassist.beats import detect_file

    f = tmp_path / "song.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "sine=f=220:d=6,volume='if(lt(t,4),1,exp(-(t-4)*12))':eval=frame,apad=pad_dur=3",
                    str(f)], check=True)
    assert detect_file(str(f))["end"] == pytest.approx(4.5, abs=0.3)  # rung out ~0.4 s after 4 s, not 9 s


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
        n = 0

        def __init__(self, path, fps, kind="Video"):
            self.props = {"File Path": str(path), "FPS": fps, "Type": kind}
            Item.n += 1
            self.uid = f"id{Item.n}"

        def GetName(self):
            return Path(self.props["File Path"]).name

        def GetUniqueId(self):
            return self.uid

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
            if k in ("ZoomX", "ZoomY", "Pan", "Tilt"):
                self.info[k] = v
                return True
            return False  # Resolve 21.0: no audio volume

    class Tl:
        def __init__(self, rate="30", name="x"):
            self.name, self.pool_item = name, Item(name, None, "Timeline")
            self.tracks = {"video": 1, "audio": 1, "subtitle": 0}
            self.items = []
            self.settings = {"timelineFrameRate": rate}
            self.playhead, self.subs = 86400 + 3960, []  # a frame grab left the playhead at 01:06

        def GetStartTimecode(self):
            return "01:00:00:00"

        def SetCurrentTimecode(self, tc):
            if getattr(self, "stale", 0):  # live 21.0: the first move after a template copy did not take
                self.stale -= 1
                return True
            self.playhead = 86400 if tc == "01:00:00:00" else self.playhead
            return True

        def DeleteClips(self, items, ripple=False):
            self.subs = [f for f in self.subs if f not in [i.GetStart() for i in items]]
            return True

        def GetItemListInTrack(self, kind, i):
            class Sub:
                def __init__(self, f):
                    self.f = f

                def GetStart(self):
                    return self.f
            return [Sub(f) for f in self.subs] if kind == "subtitle" else []

        def SetSetting(self, k, v):
            if k == "timelineFrameRate":
                return False  # ~ strict case: the timeline keeps the rate it was created with
            self.settings[k] = v
            return True

        def GetSetting(self, k):
            return self.settings.get(k)

        def GetStartFrame(self):
            return 86400

        def GetName(self):
            return self.name

        def GetMediaPoolItem(self):
            return self.pool_item

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

        def GetCurrentFolder(self):
            return self.cur

        def ImportMedia(self, paths):
            items = [Item(p, 30.0) for p in paths]
            self.cur.clips += items
            return items

        def CreateEmptyTimeline(self, name):
            self.tl = Tl(self.rp.settings["timelineFrameRate"], name)
            self.cur.clips.append(self.tl.pool_item)  # a new timeline lands in the current bin
            self.rp.count += 1
            return self.tl

        def MoveClips(self, items, folder):
            def walk(f):
                f.clips = [c for c in f.clips if c not in items]
                for sub in f.subs:
                    walk(sub)
            walk(self.root)
            folder.clips += items
            return True

        def AppendToTimeline(self, infos):
            info = dict(infos[0]) if isinstance(infos[0], dict) else {"srt": True}
            if "srt" in info and self.tl:  # Resolve drops an .srt's cues at the playhead
                self.tl.subs.append(self.tl.playhead)
            if "mediaPoolItem" in info:
                info["_fps"] = info["mediaPoolItem"].GetClipProperty("FPS")
                self.tl.items.append(info)
            return [TlItem(info)]

    class RP:
        def __init__(self):
            self.mp = MP()
            self.mp.rp = self
            self.settings = {"timelineFrameRate": "30"}
            self.count = 0

        def GetSetting(self, k):
            return self.settings.get(k)

        def SetSetting(self, k, v):
            if k == "timelineFrameRate" and self.count:
                return False  # locked once the project has a timeline
            self.settings[k] = v
            return True

        def GetTimelineCount(self):
            return self.count

        def GetMediaPool(self):
            return self.mp

        def SetCurrentTimeline(self, t):
            self.current = t
            return True

        def GetCurrentTimeline(self):
            return self.current

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
    assert vids[0]["ZoomX"] == vids[0]["ZoomY"] == 1.2 and "Pan" not in vids[0]
    # off-centre: the same window as the render's crop (a speaker at the left of a wide stays in frame)
    from editassist.resolve_native import zoom_offset
    assert zoom_offset({"scale": 1.5, "x": 0.3, "y": 0.45}, 1080, 1920) == (108.0, -48.0)
    assert zoom_offset({"scale": 2.0, "x": 0.0, "y": 1.0}, 1000, 1000) == (500.0, 500.0)  # edge, no border
    v[0]["zoom"] = {"scale": 1.5, "x": 0.3, "y": 0.45, "ramp": 0}
    rp2 = _fake_resolve()
    resolve_native.build(project, tl, rp2, "fast off")
    first = [i for i in rp2.mp.tl.items if i["mediaType"] == 1][0]
    assert (first["Pan"], first["Tilt"]) == (pytest.approx(0.5 * tl["width"] * 0.2), pytest.approx(-0.5 * tl["height"] * 0.05))
    v[0]["zoom"] = {"scale": 1.2, "x": 0.5, "y": 0.5, "ramp": 0}
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


def test_validate_rejects_folder_as_media(project):
    """A clip whose media is a folder (an empty filename in a scripted swap) passed validate and qa,
    then ffmpeg failed at render with "Is a directory"."""
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0, "out": 1}])
    T.track(tl, "V1")["clips"][0]["media"] = "input"
    assert any("folder" in p for p in T.validate(project, tl))


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
    # cut times a fraction of a frame apart (a builder snapped starts but not ends): still butt
    # (3 one-frame holes in the inauguração timeline, 2026-10-08)
    tl = T.from_segments(project, [{"media": "input/cam60.mp4", "in": 0.0, "out": 3.0}] * 3)
    tl["fps"] = 24000 / 1001
    v = T.track(tl, "V1")["clips"]
    v[0]["out"], v[1]["start"] = 3.0 - 0.02, 3.0 + 0.0    # ends 0.5 frame before the next start
    v[1]["out"], v[2]["start"] = 3.07, 6.05               # 73 frames: 182.5 source frames of 59.94
    rp = _fake_resolve()
    resolve_native.build(project, tl, rp, "holes v2")
    vids = [i for i in rp.mp.tl.items if i["mediaType"] == 1]
    for a, b in zip(vids, vids[1:]):
        # Resolve truncates a source span that isn't a whole number of timeline frames
        placed = int((a["endFrame"] - a["startFrame"]) * (24000 / 1001) / (60000 / 1001) + 1e-9)
        assert placed == b["recordFrame"] - a["recordFrame"], (a, b)


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
    for name, crop in (("pan.mp4", "x='n':y=40"),  # smooth camera move (crop x snaps to even px, 2 px per sampled frame): not shake
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
    # rendered titles/lower thirds (work/motion) animate: they were all marked shaky (2026-10-08)
    mo = project.path("work", "motion", "Title_1.mov")
    mo.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(project.path("input", "shaky.mp4"), mo)
    tl = T.load(project)
    tl["tracks"].append({"kind": "video", "name": "V2", "clips": [
        {"media": "work/motion/Title_1.mov", "in": 0, "out": 3, "start": 0, "stabilize": True}]})
    T.save(project, tl)
    mark(project)
    assert "stabilize" not in T.track(T.load(project), "V2")["clips"][0]


def test_shake_marks_gentle_handheld_sway(project):
    """Hand-held slow motion sways slowly with a little tremor: the old 0.6 jitter threshold left 33 of 38
    such clips unstabilised and the client saw every one (2026-10-09). A tripod shot stays unmarked."""
    from editassist.ingest import ingest
    from editassist.shake import THRESHOLD, mark

    still = "testsrc2=s=960x600:r=30,trim=end_frame=1,loop=loop=200:size=1,setpts=N/30/TB"
    for name, crop in (("tripod.mp4", "x=80:y=60"),
                       ("sway.mp4", "x='80+20*sin(t*2.2)':y='60+14*sin(t*1.6+1)'"),  # slow drift only
                       ("tremor.mp4", "x='80+3*random(1)':y='60+3*random(2)'")):  # 0-2 px of 640 (crop x is even)
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", still, "-t", "4",
                        "-vf", f"crop=640:360:{crop}", "-c:v", "libx264", str(project.path("input", name))], check=True)
    ingest(project)
    tl = T.from_segments(project, [{"media": f"input/{n}.mp4", "in": 0, "out": 3}
                                   for n in ("tripod", "sway", "tremor")], with_video=True)
    T.save(project, tl)
    rep = mark(project)
    by = {c["media"]: c for c in rep["clips"]}
    assert not by["tripod.mp4"]["stabilize"]
    assert by["sway.mp4"]["stabilize"] and by["sway.mp4"]["jitter_pct"] < 0.6  # caught by wobble
    assert by["tremor.mp4"]["stabilize"] and by["tremor.mp4"]["jitter_pct"] < 0.6 and THRESHOLD < 0.6
    # a 0.25 s source span (one beat of 0.4x slow motion) is judged on the take around it, not skipped
    tl = T.from_segments(project, [{"media": "input/tremor.mp4", "in": 1.0, "out": 1.25},
                                   {"media": "input/tripod.mp4", "in": 1.0, "out": 1.25}], with_video=True)
    T.save(project, tl)
    rep = mark(project)
    assert [c["stabilize"] for c in rep["clips"]] == [True, False]
    assert [c.get("stabilize", False) for c in T.track(T.load(project), "V1")["clips"]] == [True, False]


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


def test_gain_copies_never_clip_a_lifted_quiet_voice(project):
    """A quiet podcast raw (peaks -10 dBFS, voice ~-32 LUFS) leveled to -16 LUFS gets +16 dB: the wav
    placed in Resolve hard-clipped every peak at 0 dBFS (2026-10-20). Gain copies are limited to -1 dBFS."""
    from editassist.bake import gain_copies
    from editassist.ingest import ingest

    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "aevalsrc=0.3*sin(2*PI*220*t)*(0.15+0.85*gt(sin(2*PI*3*t)\\,0.95)):s=48000:d=4",
                    str(project.path("input", "quiet.wav"))], check=True)
    ingest(project)
    tl = T.from_segments(project, [{"media": "input/quiet.wav", "in": 0, "out": 4}], with_video=False)
    T.track(tl, "A1")["clips"][0]["gain_db"] = 16.0
    T.save(project, tl)
    baked, n = gain_copies(project, T.load(project))
    assert n == 1
    out = project.abs(T.track(baked, "A1")["clips"][0]["media"])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-f", "f32le", "-"], capture_output=True).stdout
    import numpy as np
    x = np.abs(np.frombuffer(raw, np.float32))
    assert x.max() <= 0.9  # under -1 dBFS, nothing clipped
    assert x.max() > 0.5   # still lifted (the quiet parts got their +16 dB)
    # and under -1 dB TRUE peak: -1 dBFS samples rendered at -0.1 dBTP from Resolve (2026-10-21)
    log = subprocess.run(["ffmpeg", "-nostats", "-i", str(out), "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    assert float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", log)[-1]) <= -1.0


def test_ingest_proxies_never_reuse_a_truncated_file(project, monkeypatch):
    """An interrupted ingest left a half-written proxy that the next run took as done (72 GB of 4K
    S-Log3, 2026-10-08). Proxies now go to a .part file and are renamed when complete; the catalog
    is written before any proxy so transcription can start."""
    from editassist import ingest as I

    calls = []

    def boom(src, px):
        calls.append(px)
        part = px.with_name(px.stem + ".part.mp4")
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_bytes(b"half")
        assert I.read_json(project.path("work", "media.json"))  # catalog already on disk
        raise SystemExit("killed")

    monkeypatch.setattr(I, "make_proxy", boom)
    with pytest.raises(SystemExit):
        I.ingest(project, proxies=True)
    assert calls and not any(p.exists() for p in calls)
    monkeypatch.undo()
    cat = I.ingest(project, proxies=True)
    px = project.dir / cat["cam_a"]["proxy"]
    assert px.exists() and px.stat().st_size > 1000


def test_vocabulary_dictionary_fixes_transcripts_and_captions(project, tmp_path, monkeypatch):
    """The user asked for one dictionary of words Whisper gets wrong, applied to every transcript from
    then on (2026-10-08, "Camoriú" for Camboriú). Scoped fixes only apply to matching projects."""
    from editassist import vocab
    from editassist.transcribe import load_transcript

    monkeypatch.setenv("EA_MEMORY_DIR", str(tmp_path / "mem"))
    vocab.add(["olá=Oi", "material bruto=footage"], ["Balneário Camboriú"], note="test")
    vocab.add(["hoje=amanhã"], scope="otherclient")
    assert vocab.load(project.dir.name)["fixes"] == ["olá=Oi", "material bruto=footage"]
    assert "Balneário Camboriú" in vocab.hotwords(project.dir.name)
    vocab.add(["olá=Olá!"])  # same heard word replaces, never stacks
    assert [f for f in vocab.load()["fixes"] if f.startswith("olá=")] == ["olá=Olá!"]
    res = vocab.apply_project(project)
    assert res["changed"]["cam_a"] == 2
    words = [w["word"] for s in load_transcript(project, "cam_a")["segments"] for w in s["words"]]
    assert "Olá!" in words and "footage." in words and "Hoje" in words
    assert "footage." in project.path("work", "transcripts", "cam_a.txt").read_text(encoding="utf-8")
    assert vocab.apply_project(project)["changed"] == {}  # idempotent


def test_vocab_cli_add_is_repeatable(tmp_path, monkeypatch, capsys):
    """`ea vocab --add "a=b" --add "c=d"` kept only the last fix (argparse nargs without extend), so
    "Tom Bonário Camboriú=Balneário Camboriú" was silently lost (2026-10-09)."""
    from editassist import vocab
    from editassist.cli import main

    monkeypatch.setenv("EA_MEMORY_DIR", str(tmp_path / "mem"))
    main(["vocab", "--add", "Tom Bonário Camboriú=Balneário Camboriú", "--add", "Ravá=Vavá",
          "--term", "Conanda", "--term", "Yacht Club"])
    d = vocab.load()
    assert d["fixes"] == ["Tom Bonário Camboriú=Balneário Camboriú", "Ravá=Vavá"]
    assert "Conanda" in vocab.hotwords() and "Yacht Club" in vocab.hotwords()


def test_captions_join_split_thousands():
    """Whisper wrote "1" ".217." and "3" ".500": captions read "AOS 1 .217." (2026-10-09)."""
    from editassist.subtitles import join_numbers

    w = lambda word, a: {"word": word, "start": a, "end": a + 0.3}
    out = join_numbers([w("aos", 0), w("1", 1), w(".217.", 1.3), w("mais", 2), w("de", 2.3), w("3", 2.6),
                        w(".500", 2.9), w("Tutelar.", 3.5), w(".", 4)])
    assert [x["word"] for x in out] == ["aos", "1.217.", "mais", "de", "3.500", "Tutelar.", "."]
    assert out[1]["start"] == 1 and out[1]["end"] == 1.6


def test_captions_break_where_sentences_were_cut_out():
    """"...votar na gente" + (31 s of speech dropped) + "Vavá, Nádia" made one caption "NA GENTE VAVÁ,"
    (2026-10-09). A pause closed by a silence cut (< 3 s of source) still keeps one line."""
    from editassist.subtitles import group

    def w(word, a, src, f="talk.mp4"):
        return {"word": word, "start": a, "end": a + 0.3, "_src": (f, src, src + 0.3)}

    cut = [w("votar", 0, 105.0), w("na", 0.3, 105.3), w("gente", 0.6, 105.6), w("Vavá,", 0.9, 137.8)]
    assert [[x["word"] for x in l["words"]] for l in group(cut)] == [["votar", "na", "gente"], ["Vavá,"]]
    assert all("_src" not in x for l in group(cut) for x in l["words"])
    pause = [w("votar", 0, 105.0), w("na", 0.3, 105.3), w("gente", 0.6, 107.0)]  # 1.4 s pause removed
    assert len(group(pause)) == 1
    other = [w("tamo", 0, 5.0), w("junto", 0.3, 5.3, "b.mp4")]
    assert len(group(other)) == 2


def test_captions_max_chars_gives_one_short_line_each():
    """The user's rule (2026-10-13): one-line captions of at most 15 characters, long words hyphenated
    across two captions. `group` used to carry a clingy word onto the next line past the limit
    ("que esse dia" -> "esse dia acontecesse.") and `ea subtitles` had no length limit at all."""
    from editassist.subtitles import group, split_long

    text = "Tudo o que você fez para que esse dia acontecesse. Uma responsabilidade inconstitucionalmente"
    ws = [{"word": w, "start": i * 0.4, "end": i * 0.4 + 0.35} for i, w in enumerate(text.split())]
    lines = group(split_long(ws, 15), max_words=4, max_chars=15)
    texts = [" ".join(x["word"] for x in l["words"]) for l in lines]
    assert all(len(t) <= 15 for t in texts), texts
    assert "".join(texts).replace("-", "").replace(" ", "") == text.replace(" ", "")
    pieces = [x for l in lines for x in l["words"] if x["word"].endswith("-")]
    assert pieces and all(p["end"] > p["start"] for p in pieces)


def test_captions_never_break_inside_a_dictionary_term():
    """"do Conselho | Tutelar." split a name over two caption lines (2026-10-08)."""
    from editassist.vocab import keep_terms

    ws = [{"word": w, "start": i, "end": i + 0.5} for i, w in enumerate("a comunidade do Conselho Tutelar.".split())]
    out = keep_terms(ws, ["Conselho Tutelar", "Balneário Camboriú", "CRAS"])
    assert [w["word"] for w in out] == ["a", "comunidade", "do", "Conselho Tutelar."]
    assert out[-1]["start"] == 3 and out[-1]["end"] == 4.5


def test_qa_accepts_intended_fades_and_preview_loudness(project):
    """A fade in from black at 0 s was reported as a "black flash at the cut", and a 540p preview
    (mixed to -16 LUFS) was judged against the -14 delivery target (2026-10-08)."""
    from editassist.qa import check
    from editassist.render import render

    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.4, "out": 4.9},
                                   {"media": "input/cam_a.mp4", "in": 7.4, "out": 9.5}], with_video=True)
    v = T.track(tl, "V1")["clips"]
    v[0]["transition_in"] = {"type": "fade", "dur": 0.5}
    v[-1]["transition_out"] = {"type": "fade", "dur": 0.8}
    T.save(project, tl)
    render(project, preset="preview", out="output/p.mp4")
    rep = check(project, "output/p.mp4")
    assert not [i for i in rep["issues"] if "black flash" in i["issue"]], rep["issues"]
    assert not [i for i in rep["issues"] if "target for youtube" in i["issue"]], rep["issues"]


def test_resolve_native_sets_the_timeline_frame_rate(project):
    """The open project ran at 24 fps and the edit at 23.976: the native build never set a frame rate,
    so every frame position would drift (2026-10-08). An empty project is switched; a project whose
    rate is locked by an existing timeline is refused with an explanation."""
    from editassist import resolve_native

    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.5, "out": 1.5}])
    tl["fps"] = 24000 / 1001
    rp = _fake_resolve()
    rp.settings["timelineFrameRate"] = "24"
    resolve_native.build(project, tl, rp, "x v1")
    assert rp.mp.tl.GetSetting("timelineFrameRate") == "23.976"
    rp.settings["timelineFrameRate"] = "24"  # now locked: the project has a timeline
    with pytest.raises(SystemExit, match="drift"):
        resolve_native.build(project, tl, rp, "x v2")


def test_qa_flags_sub_frame_cuts(project):
    from editassist.qa import check

    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.0, "out": 2.0},
                                   {"media": "input/cam_a.mp4", "in": 3.0, "out": 4.0}], with_video=True)
    T.track(tl, "V1")["clips"][1]["start"] += 0.025  # 0.75 frame at 30 fps: rounds to a 1-frame hole
    T.save(project, tl)
    assert any("off by" in i["issue"] for i in check(project)["issues"])


def test_next_timeline_name_never_doubles_the_version():
    from editassist.export import next_timeline_name

    assert next_timeline_name("Inauguração v1", set()) == "Inauguração v1"  # was "Inauguração v1 v1"
    assert next_timeline_name("Inauguração v1", {"Inauguração v1"}) == "Inauguração v2"
    assert next_timeline_name("reel", {"reel v1", "reel v2"}) == "reel v3"


def test_qa_flags_picture_out_of_sync_with_its_own_sound(project):
    """Two sound pieces from one take (a pause cut out) under ONE continuous picture clip: the lips
    were 2.3 s behind the voice (2026-10-08)."""
    from editassist.qa import check

    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.4, "out": 1.6},
                                   {"media": "input/cam_a.mp4", "in": 2.9, "out": 4.9}], with_video=True)
    v = T.track(tl, "V1")["clips"]
    v[0]["out"] = v[0]["in"] + T.length(tl)  # picture keeps running through the jump
    del v[1:]
    T.save(project, tl)
    assert any("out of sync" in i["issue"] for i in check(project)["issues"])
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.4, "out": 1.6},
                                   {"media": "input/cam_a.mp4", "in": 2.9, "out": 4.9}], with_video=True)
    T.save(project, tl)
    assert not any("out of sync" in i["issue"] for i in check(project)["issues"])


def test_cut_follows_the_voice_when_whisper_squeezes_the_last_word(project):
    """Whisper gave "habitantes" 0.16 s and put the next speaker's word right after it: padding clamped
    to that word and cut the prefeita mid-word (2026-10-08). The out point now follows the audio."""
    from editassist.cut import resolve_segments

    f = project.path("work", "transcripts", "cam_a.json")
    t = json.loads(f.read_text(encoding="utf-8"))
    w = t["segments"][0]["words"]  # Olá 0.5-0.9, pessoal. 0.95-1.5 (tone until 1.5)
    w[1]["end"] = 1.0  # squeezed: 7 letters in 0.05 s
    t["segments"][1]["words"][0].update(start=1.02, end=1.1)  # "Hoje" glued to it
    f.write_text(json.dumps(t), encoding="utf-8")
    seg = resolve_segments(project, [{"media": "cam_a", "in": 0.5, "out": 1.0}])[0]
    assert 1.5 <= seg["out"] <= 1.7, seg


def test_timeline_slots_keep_each_videos_captions(project):
    """Several videos in one project: a builder rewrote timeline.json while work/captions.json still held
    the recap's captions; they leaked into the new video's slot, its qa and its NLE export."""
    from editassist.cut import speech_segments
    from editassist.subtitles import build as subs

    tl = T.from_segments(project, speech_segments(project, "cam_a"))
    tl["name"] = "recap"
    T.save(project, tl)
    subs(project)
    assert T.save_slot(project, "recap")["captions"]
    content = T.new(project)
    content["name"] = "content"
    content["tracks"][0]["clips"] = [{"media": "input/cam_b.mp4", "in": 0, "out": 2, "start": 0}]
    T.save(project, content)  # what a builder script does; captions.json is still the recap's
    assert T.captions(project, content) is None
    assert not T.save_slot(project, "content")["captions"]
    assert T.load_slot(project, "recap")["captions"]
    assert T.captions(project, T.load(project))["timeline"] == "recap"
    T.load_slot(project, "content")
    assert not project.path("work", "captions.json").exists()
    content["tracks"][0]["clips"][0]["out"] = 3
    T.save(project, content)  # unsaved change: loading another slot must not drop it
    with pytest.raises(SystemExit):
        T.load_slot(project, "recap")
    assert T.load_slot(project, "recap", force=True)["name"] == "recap"


def test_timeline_slot_save_never_overwrites_another_video(project):
    """A fix meant for corte 2 ran on the timeline left loaded (corte 5) and was saved as corte2, wiping
    corte 2 (2026-10-20). A slot only takes back its own video (or one still carrying the default name)."""
    tl = T.new(project)
    tl["tracks"][0]["clips"] = [{"media": "input/cam_a.mp4", "in": 0, "out": 2, "start": 0}]
    T.save(project, tl)
    T.save_slot(project, "corte2")                    # unnamed draft (project name): fine
    tl["name"] = "CORTE 2"
    T.save(project, tl)
    T.save_slot(project, "corte2")                    # naming the draft in its own slot: fine
    tl["name"] = "CORTE 5"
    T.save(project, tl)
    T.save_slot(project, "corte5")
    with pytest.raises(SystemExit, match="holds 'CORTE 2'"):
        T.save_slot(project, "corte2")
    assert T.load_slot(project, "corte2", force=True)["name"] == "CORTE 2"
    tl["name"] = "CORTE 5"
    T.save(project, tl)
    assert T.save_slot(project, "corte2", force=True)["name"] == "CORTE 5"


def test_qa_overlay_past_the_picture(project):
    """An end title placed 0.3 s into the last shot with the shot's full length ran 0.1 s past the video."""
    from editassist.qa import check

    tl = T.new(project)
    tl["tracks"][0]["clips"] = [{"media": "input/cam_a.mp4", "in": 0, "out": 4, "start": 0}]
    tl["tracks"].insert(1, {"kind": "video", "name": "V2", "clips": [
        {"media": "input/cam_b.mp4", "in": 0, "out": 2, "start": 2.1, "note": "end title"}]})
    T.save(project, tl)
    assert any("end title ends at 4.10s" in i["issue"] for i in check(project)["issues"])
    tl["tracks"][1]["clips"][0]["out"] = 1.9
    T.save(project, tl)
    assert not any("after the last V1 picture" in i["issue"] for i in check(project)["issues"])


def test_render_trims_loudness_to_target(tmp_path):
    """Single-pass loudnorm left a music-only reel (loud montage, soft outro) at -15.7 for -14."""
    from editassist.render import measure, trim_loudness

    f = tmp_path / "quiet.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=24:d=4", "-f", "lavfi",
                    "-i", "sine=f=440:d=4,volume=-30dB", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(f)],
                   check=True)
    before = measure(f)[0]
    gain = trim_loudness(f, -16, -1.0)
    lufs, tp = measure(f)
    assert gain > 5 and lufs > before + 5
    assert lufs == pytest.approx(-16, abs=0.6) and tp <= -1.0 + 0.2


def test_resolve_finished_timelines_get_their_own_bin(project):
    """Finished timelines go to a bin with nothing else in it; a new version moves the one it replaces
    (and the "v1 v1" of an old naming bug) to editassist/versões antigas."""
    from editassist import resolve_native as R

    assert R.version_base("Conteúdo 1 - A nova sede v12") == "Conteúdo 1 - A nova sede"
    assert R.version_base("Inauguração v1 v1") == "Inauguração"
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.5, "out": 1.5}])
    rp = _fake_resolve()
    names = []
    for name in ("Inauguração v1 v1", "Inauguração v2", "Outro v1"):
        R.build(project, tl, rp, name)
        names.append(R.file_timeline(rp, rp.GetCurrentTimeline()))
    assert names[1]["replaced"] == ["Inauguração v1 v1"] and names[2]["replaced"] == []
    bins = {f.GetName(): f for f in rp.mp.root.GetSubFolderList()}
    assert sorted(c.GetName() for c in bins[R.FINALS_BIN].GetClipList()) == ["Inauguração v2", "Outro v1"]
    old = {f.GetName(): f for f in bins["editassist"].GetSubFolderList()}[R.OLD_BIN]
    assert [c.GetName() for c in old.GetClipList()] == ["Inauguração v1 v1"]
    assert not any(c.GetClipProperty("Type") == "Timeline" for c in bins["editassist"].GetClipList())


def test_client_preferences_folder(tmp_path, monkeypatch):
    """The user wants one folder of preferences per client (2026-10-09, "pasta de clientes, com as
    preferências de cada cliente"): a project is tied to its client, the client's file is read after
    the general one, and dictionary fixes scoped to a client apply to all of that client's projects."""
    import editassist.project as P
    from editassist import clients, vocab

    monkeypatch.setattr(P, "PROJECTS", tmp_path / "projects")
    monkeypatch.setenv("EA_MEMORY_DIR", str(tmp_path / "mem"))
    assert clients.client_slug("Ana Souza") == "ana-souza"
    assert clients.client_slug("Ótica São João") == "otica-sao-joao"

    reel = P.Project.create("reel-lancamento")
    res = clients.assign(reel, "Ana Souza")
    assert res["created"] and res["client"] == "ana-souza"
    prefs = tmp_path / "mem" / "clients" / "ana-souza" / "preferences.md"
    assert prefs.read_text(encoding="utf-8").startswith("# Client: Ana Souza")
    prefs.write_text("# Client: Ana Souza\n\n## Never\n- no zooms\n", encoding="utf-8")
    assert clients.assign(reel, "ana souza")["created"] is False  # never overwrites her file
    assert "no zooms" in prefs.read_text(encoding="utf-8")

    shown = clients.show(reel)
    assert shown["read"][0].endswith("preferences.md") and shown["read"][-1] == str(prefs)
    assert shown["matched_by"] == "project.json" and shown["client_name"] == "Ana Souza"

    # no "client" in project.json: a known client's slug in the project name is enough
    clients.create("Acme")
    car = P.Project.create("acme-carro-cinza")
    other = P.Project.create("pod")
    assert clients.client_of(car) == "acme" and clients.show(car)["matched_by"] == "project name"
    assert clients.client_of(other) is None and "hint" in clients.show(other)
    assert {c["client"]: c["projects"] for c in clients.listing()["clients"]} == {
        "ana-souza": ["reel-lancamento"], "acme": ["acme-carro-cinza"]}

    vocab.add(["ana sousa=Ana Souza"], scope="ana-souza")
    assert vocab.load("reel-lancamento")["fixes"] == ["ana sousa=Ana Souza"]  # name has no "ana-souza"
    assert vocab.load("pod")["fixes"] == []


def test_probe_flags_phone_hdr(tmp_path):
    """iPhone clips are HLG (arib-std-b67): ingest recorded nothing, so nobody knew they needed a
    conversion LUT (2026-10-13)."""
    import subprocess

    from editassist.media import probe

    hlg, sdr = tmp_path / "hlg.mp4", tmp_path / "sdr.mp4"
    for out, extra in ((hlg, ["-vf", "setparams=color_trc=arib-std-b67:color_primaries=bt2020:colorspace=bt2020nc"]),
                       (sdr, [])):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=30:d=0.2",
                        "-c:v", "libx264", *extra, str(out)], check=True)
    assert probe(hlg)["hdr"] == "hlg"
    assert "hdr" not in probe(sdr)


def test_transcribe_drops_hotword_and_low_confidence_hallucinations():
    """Party clips with only music came back as "Gael Gael Gael Gael" and "Balneário Camboriú Carvalho
    Agrestes Vavá DOMCast" (the dictionary's hotwords) or "Aero" at p 0.0 (2026-10-13)."""
    from editassist.transcribe import hallucinated

    hot = "Balneário Camboriú Carvalho Agrestes Vavá DOMCast Gael"

    def seg(text, p):
        return {"text": text, "words": [{"word": w, "prob": p} for w in text.split()]}

    assert hallucinated(seg("Gael Gael Gael Gael", 0.42), hot)
    assert hallucinated(seg("Carvalho Balneário Agrestes Vavá DOMCast", 0.07), hot)
    assert hallucinated(seg("Aero", 0.0), hot)
    assert not hallucinated(seg("Bem-vindos ao DOMCast, hoje com o Vavá", 0.9), hot)
    assert not hallucinated(seg("Balneário Camboriú", 0.95), hot)  # said clearly: real
    assert not hallucinated(seg("Ela vai sair de novo pra gente", 0.6), hot)


def test_transcribe_head_tail_windows_keep_source_time(project, monkeypatch):
    """Trimming hour-long podcast recordings only needs their first and last minutes: --head/--tail
    transcribe those windows alone, and every time stays in source seconds."""
    from types import SimpleNamespace as NS

    from editassist import transcribe as TR

    assert TR.windows(100, 30, 20) == [(0.0, 30), (80, 100)]
    assert TR.windows(100, 60, 60) == [(0.0, 100)]  # overlapping windows = the whole clip
    assert TR.windows(100) == [(0.0, 100)]
    assert TR.windows(100, 10, 10, [(40, 60), (55, 70)]) == [(0.0, 10), (40, 70), (90, 100)]
    heard = []

    class FakeWhisper:
        def transcribe(self, audio, **kw):
            heard.append(len(audio) / 16000)
            w = NS(start=1.0, end=1.5, word="oi", probability=0.9)
            return [NS(start=1.0, end=1.5, text="oi", words=[w])], NS(language="pt")

    monkeypatch.setattr(TR, "_model", lambda name: FakeWhisper())
    TR.transcribe(project, only=["cam_a"], force=True, head=2, tail=3)
    t = TR.load_transcript(project, "cam_a")
    dur = t["windows"][1][1]
    assert heard == pytest.approx([2, 3], abs=0.01)
    assert [s["start"] for s in t["segments"]] == pytest.approx([1.0, dur - 3 + 1.0], abs=0.01)
    assert t["windows"][0] == [0.0, 2]
    assert TR.missing([(0, 10), (20, 30)], [(0, 4), (25, 40)]) == [(4, 10), (20, 25)]

    # a later --span only transcribes what the partial transcript lacks, and keeps the rest
    heard.clear()
    TR.transcribe(project, only=["cam_a"], spans=[(1, 4)])
    t = TR.load_transcript(project, "cam_a")
    assert heard == pytest.approx([2], abs=0.01)  # 2-4 s, 1-2 s was already heard
    assert t["windows"][0] == [0.0, 4]
    assert [s["start"] for s in t["segments"]] == pytest.approx([1.0, 3.0, dur - 3 + 1.0], abs=0.01)


def test_resolve_native_crop_as_zoom_and_pan(project):
    """A reformatted (9:16) timeline is framed in Resolve with Zoom + Pan per item, as the user frames
    vertical cuts by hand (Zoom 3.16 on 16:9 in 9:16), instead of needing `ea bake`."""
    from editassist import resolve_native
    from editassist.project import read_json
    from editassist.resolve_native import crop_transform

    # full-height 9:16 window of a 1920x1080 clip, centred: the user's own Zoom 3.1605, no Pan
    assert crop_transform({"w": 608, "h": 1080, "x": 656, "y": 0}, 1920, 1080, 1080, 1920) == (3.1605, 0.0, 0.0)
    # window at the left edge: the image moves right by (960 - 304) source px x 1920/1080
    z, pan, tilt = crop_transform({"w": 608, "h": 1080, "x": 0, "y": 0}, 1920, 1080, 1080, 1920)
    assert pan == pytest.approx(656 * 1920 / 1080, abs=0.1) and tilt == 0
    # a punch-in on top scales the offset too
    assert crop_transform({"w": 608, "h": 1080, "x": 0, "y": 0}, 1920, 1080, 1080, 1920,
                          {"scale": 1.2, "x": .5, "y": .5})[:2] == pytest.approx((3.1605 * 1.2, pan * 1.2), abs=0.2)
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.0, "out": 1.0}])
    cam = next(x for x in read_json(project.path("work", "media.json")).values() if x["path"].endswith("cam_a.mp4"))
    sw, sh = cam["width"], cam["height"]
    tl["width"], tl["height"] = 1080, 1920
    cw = int(sh * 9 / 16) // 2 * 2
    T.track(tl, "V1")["clips"][0]["crop"] = {"w": cw, "h": sh, "x": 0, "y": 0}
    rp = _fake_resolve()
    rep = resolve_native.build(project, tl, rp, "vertical v1")
    vid = [i for i in rp.mp.tl.items if i["mediaType"] == 1][0]
    want = crop_transform({"w": cw, "h": sh, "x": 0, "y": 0}, sw, sh, 1080, 1920)
    assert rep.get("crops") == 1 and not rep["failed"]
    assert (vid["ZoomX"], vid["ZoomY"], vid["Pan"], vid["Tilt"]) == (want[0], want[0], want[1], want[2])
    assert vid["Pan"] > 0  # speaker at the left of the wide: picture shifted right


def test_reformat_splits_clips_at_camera_cuts(project, tmp_path):
    """A bite from a switched podcast feed goes wide -> close-up inside one clip: reformat splits it at
    the camera cut (scene score on just that source stretch, in source seconds) so each shot gets its
    own face crop; one crop for the whole clip framed the wide on the wrong person (2026-10-10)."""
    from editassist.reformat import split_at_cuts
    from editassist.scenes import cut_times

    src = tmp_path / "switched.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=3",
                    "-f", "lavfi", "-i", "smptebars=s=320x180:r=30:d=3", "-filter_complex", "[0][1]concat=n=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    cuts = cut_times(str(src), 0.3, 1.0, 5.0)
    assert len(cuts) == 1 and cuts[0] == pytest.approx(3.0, abs=0.05)
    assert cut_times(str(src), 0.3, 3.5, 5.5) == []  # a stretch inside one shot
    tl = {"tracks": [{"kind": "video", "name": "V1", "clips": [
              {"media": str(src), "in": 1.0, "out": 5.0, "start": 10.0, "transition_in": {"type": "fade"}}]},
          {"kind": "audio", "name": "A1", "clips": [{"media": str(src), "in": 1.0, "out": 5.0, "start": 10.0}]}]}
    assert split_at_cuts(project, tl) == 1
    v = tl["tracks"][0]["clips"]
    assert [(c["in"], c["out"], c["start"]) for c in v] == [(1.0, cuts[0], 10.0), (cuts[0], 5.0, 10.0 + cuts[0] - 1.0)]
    assert "transition_in" in v[0] and "transition_in" not in v[1]
    assert len(tl["tracks"][1]["clips"]) == 1  # the voice stays one clip
    # a cut 0.2 s after the clip's head: no split (too short a shot), but reported as a flash frame
    tl["tracks"][0]["clips"] = [{"media": str(src), "in": 2.8, "out": 5.0, "start": 0.0}]
    flashes = []
    assert split_at_cuts(project, tl, flashes=flashes) == 0
    assert len(flashes) == 1 and "head" in flashes[0]


def test_reformat_keeps_the_project_resolution():
    """A 4K project reformatted to 9:16 came out 1080x1920 (the user wants 4K always, 2026-10-20)."""
    from editassist.reformat import frame_size

    assert frame_size("9:16", 2160, 3840) == (2160, 3840)
    assert frame_size("9:16", 3840, 2160) == (2160, 3840)
    assert frame_size("1:1", 3840, 2160) == (2160, 2160)
    assert frame_size("4:5", 3840, 2160) == (2160, 2700)
    assert frame_size("9:16", 1920, 1080) == (1080, 1920)
    assert frame_size("9:16", 1280, 720) == (1080, 1920)  # never below the 1080 base
    assert frame_size("9:16") == (1080, 1920)


def test_reformat_frames_one_person_in_a_two_shot():
    """In a podcast wide the biggest face flips between guest (left) and host (right): the median of
    those votes framed the empty table between them (2026-10-20). The biggest group of votes wins, and
    `prefer` frames the guest's side whenever several faces are in frame."""
    from editassist.reformat import pick_face

    guest, host = (0.28, 0.4, 100.0), (0.78, 0.4, 104.0)
    flip = [[guest, host] if k % 2 else [host, guest] for k in range(8)]
    flip = [[(x, y, a + (k % 2) * 10 if x < 0.5 else a) for x, y, a in f] for k, f in enumerate(flip)]
    x, _ = pick_face(flip)
    assert abs(x - 0.28) < 0.05 or abs(x - 0.78) < 0.05  # one of the two people, never the table
    assert pick_face(flip, prefer="left")[0] == pytest.approx(0.28)
    assert pick_face(flip, prefer="right")[0] == pytest.approx(0.78)
    close_up = [[(0.55, 0.35, 900.0)]] * 6
    assert pick_face(close_up, prefer="left")[0] == pytest.approx(0.55)  # one face: prefer changes nothing
    assert pick_face([[], []]) is None


def test_subtitles_from_lines_keeps_written_lines(project, tmp_path):
    """Hand-polished caption lines stay as written: from_lines split "eu falo, e é bom," at its comma into
    a 0.2 s flash (2026-10-10). Only lines too long for the screen are chunked."""
    from editassist import subtitles

    T.save(project, T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.0, "out": 6.0}]))
    f = tmp_path / "lines.json"
    f.write_text(json.dumps([
        {"start": 0.0, "end": 1.0, "text": "eu falo, e é bom,"},
        {"start": 1.0, "end": 5.0, "text": "uma frase longa demais pra caber numa só linha da legenda, então quebra"}]))
    subtitles.from_lines(project, str(f), "t")
    lines = read_json_(project.path("work", "captions_t.json"))["lines"]
    assert " ".join(w["word"] for w in lines[0]["words"]) == "eu falo, e é bom,"
    assert len(lines) >= 3 and all(len(l["words"]) <= 7 for l in lines[1:])


def read_json_(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def test_zoom_transition_whips_both_sides_of_the_cut(project):
    """`ea transition --type zoom`: the outgoing clip zooms into the cut, the incoming lands from the zoom
    (blurred), rendered by videofx so bake carries it to NLEs without keyframes; the middle of each clip
    is untouched."""
    from editassist import transitions
    from editassist.videofx import clip_vfilter

    T.save(project, T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.0, "out": 2.0},
                                               {"media": "input/cam_a.mp4", "in": 5.0, "out": 7.0}]))
    rep = transitions.set_at(project, [2.0], kind="zoom", dur=0.25, tracks=("V1",))
    v = T.track(T.load(project), "V1")["clips"]
    assert rep["set"] == 2 and v[0]["whip"] == {"out": 0.25} and v[1]["whip"] == {"in": 0.25}

    def frame(c, t):
        chain = ",".join(clip_vfilter(project, c, 320, 180, 30))
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{c['in']:.3f}", "-t", f"{c['out'] - c['in']:.3f}",
                            "-i", str(project.abs(c["media"])), "-vf", f"{chain},select='gte(t,{t})'",
                            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True, cwd=project.dir, check=True)
        return r.stdout

    import numpy as np

    def diff(c, t):
        plain = {k: x for k, x in c.items() if k != "whip"}
        a, b = (np.frombuffer(frame(x, t), np.uint8).astype(int) for x in (c, plain))
        return float(np.abs(a - b).mean())

    assert diff(v[0], 1.0) < 2  # middle: the same picture (a resample apart)
    assert diff(v[0], 1.95) > 10  # last frames: zoomed and blurred
    assert diff(v[1], 0.0) > 10
    assert transitions.clear(project)["cleared"] == 2


def test_resolve_native_subtitles_start_at_the_timeline_start(project):
    """An .srt appended to a timeline lands at the playhead: one left at 01:06 by a frame grab put every
    caption of a 68 s reel after its end (2026-10-10). The build parks the playhead at the start first."""
    from editassist import resolve_native

    srt = project.path("output", "t.srt")
    srt.parent.mkdir(exist_ok=True)
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nOi\n", encoding="utf-8")
    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0, "out": 1}])
    rp = _fake_resolve()
    rep = resolve_native.build(project, tl, rp, "subs v1", srt=srt)
    assert rep["subtitles"] and not rep["failed"]
    assert rp.mp.tl.subs == [86400]
    # the playhead move ignored once: the misplaced cues are deleted and placed again
    rp = _fake_resolve()
    real = type(rp.mp).CreateEmptyTimeline

    def create(self, name):
        t = real(self, name)
        t.stale = 1
        return t
    type(rp.mp).CreateEmptyTimeline = create
    try:
        rep = resolve_native.build(project, tl, rp, "subs v2", srt=srt)
    finally:
        type(rp.mp).CreateEmptyTimeline = real
    assert rp.mp.tl.subs == [86400] and not rep["failed"]


def test_bake_to_a_folder_outside_the_project(project, tmp_path):
    """`ea bake --to <dir>`: baked clips land next to the client's media (the NLE project must not depend
    on this repo), the timeline and catalog point there with absolute paths."""
    from editassist.bake import bake

    tl = T.from_segments(project, [{"media": "input/cam_a.mp4", "in": 0.0, "out": 1.0}])
    T.track(tl, "V1")["clips"][0]["zoom"] = {"scale": 1.2, "x": .5, "y": .5}
    T.save(project, tl)
    dst = tmp_path / "drive" / "clips"
    assert bake(project, to=str(dst))["baked"] == 1
    c = T.track(T.load(project), "V1")["clips"][0]
    assert Path(c["media"]).parent == dst.resolve() and Path(c["media"]).exists()
    assert not list(project.path("work", "baked").glob("*.mp4")) if project.path("work", "baked").exists() else True


def test_level_measures_sfx_shorter_than_one_loudness_block(project):
    """Flip-clock clicks (0.1-0.25 s) read as silent under R128's 400 ms blocks and kept no gain."""
    from editassist.levels import level, segment_lufs

    click = project.path("input", "click.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=2000:d=0.15", "-af", "volume=-6dB",
                    str(click)], check=True)
    tl = T.new(project)
    T.track(tl, "SFX", "audio")["clips"].append({"media": "input/click.wav", "in": 0, "out": 0.15, "start": 1.0})
    T.save(project, tl)
    rep = level(project)
    c = T.track(T.load(project), "SFX")["clips"][0]
    assert not any(r.get("silent") for r in rep["clips"])
    assert segment_lufs(project, c) + c["gain_db"] == pytest.approx(-22, abs=0.3)


def test_motion_stages_image_props_for_remotion(tmp_path):
    """A logo / symbol prop given as a file path is copied where Remotion can serve it."""
    from editassist.motion import stage_image

    img = tmp_path / "ea_test_logo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    try:
        assert stage_image(str(img)) == "user-media/ea_test_logo.png"
        assert (ROOT / "assets" / "user-media" / "ea_test_logo.png").exists()
        assert stage_image("dias para o novo EP") == "dias para o novo EP"
        assert stage_image(3) == 3
    finally:
        (ROOT / "assets" / "user-media" / "ea_test_logo.png").unlink(missing_ok=True)


def test_remotion_countdown(project):
    from editassist.motion import render_motion

    T.save(project, T.new(project))
    r = render_motion(project, "Countdown", {"from": 5, "to": 3, "lines": ["dias para o _novo EP_", "do (Dom Cast)"],
                                             "width": 360, "height": 640, "fps": 10}, seconds=1)
    assert project.path(r["path"]).exists()


def test_remotion_countdown_holds_number_before_last_flip(project):
    """In the pause before the last flip the card showed the final number, jumped back to the one
    before, then flipped (5, 4, 3, 3, 4, 3): every DOMCast countdown had it (2026-10-19)."""
    import numpy as np
    from editassist.motion import render_motion

    T.save(project, T.new(project))
    r = render_motion(project, "Countdown", {"from": 5, "to": 3, "width": 360, "height": 640, "fps": 50},
                      seconds=2.5)

    def card(t):  # grey crop of the card, flips at 1.00-1.13 (5>4), pause, 1.31-1.73 (4>3)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(project.path(r["path"])),
                              "-frames:v", "1", "-vf", "crop=160:250:100:150,format=gray", "-f", "rawvideo", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(raw, np.uint8).astype(float)

    pause, four, three = card(1.24), card(1.12), card(2.4)
    assert np.abs(pause - four).mean() < np.abs(pause - three).mean()


def test_remotion_save_the_date(project):
    from editassist.motion import render_motion

    T.save(project, T.new(project))
    r = render_motion(project, "SaveTheDate", {"day": 21, "month": 10, "year": 2026,
                                               "width": 360, "height": 640, "fps": 10}, seconds=1)
    assert project.path(r["path"]).exists()


def test_render_keeps_true_peak_after_aac_overshoot(tmp_path):
    """Clicks mixed to -1 dBTP came out of the AAC encoder at +0.7 dBTP (countdown teaser); the loudness
    trim re-measures the encoded file and cuts more until the peak fits."""
    from editassist.render import measure, trim_loudness

    f = tmp_path / "clicks.mp4"
    clicks = "aevalsrc='if(lt(mod(t\\,0.13)\\,0.004)\\,0.5*sgn(sin(2*PI*3000*t))\\,0)':s=48000:d=4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", clicks, "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=4",
                    "-shortest", "-c:a", "aac", "-b:a", "192k", "-c:v", "libx264", str(f)], check=True)
    trim_loudness(f, -14, -1.0)
    assert measure(f)[1] <= -1.0


def test_projects_dir_from_env(tmp_path, monkeypatch):
    """The user wants projects saved on the Desktop (2026-10-23, "salvar os projetos no desktop,
    sempre"): EA_PROJECTS_DIR (environment or .env) is where `ea new` creates them, and projects
    made before it was set are still found in <repo>/projects."""
    import editassist.project as P
    from editassist import clients

    legacy = tmp_path / "repo-projects"
    monkeypatch.setattr(P, "PROJECTS", legacy)
    monkeypatch.setenv("EA_MEMORY_DIR", str(tmp_path / "mem"))
    old = P.Project.create("antigo")
    assert old.dir == legacy / "antigo"

    desk = tmp_path / "Desktop" / "editassist"
    monkeypatch.setenv("EA_PROJECTS_DIR", str(desk))
    new = P.Project.create("novo")
    assert new.dir == desk / "novo" and (desk / "novo" / "input").is_dir()
    assert P.Project("novo").dir == desk / "novo"
    assert P.Project("antigo").dir == legacy / "antigo"

    clients.assign(new, "Ana Souza")
    clients.assign(old, "Ana Souza")
    assert clients.client_of("novo") == "ana-souza"
    listed = {c["client"]: c["projects"] for c in clients.listing()["clients"]}
    assert sorted(listed["ana-souza"]) == ["antigo", "novo"]

    (desk / "antigo").parent.mkdir(parents=True, exist_ok=True)  # moved to the Desktop, link left behind
    (legacy / "antigo").rename(desk / "antigo")
    (legacy / "antigo").symlink_to(desk / "antigo", target_is_directory=True)
    assert P.Project("antigo").dir == desk / "antigo"
    listed = {c["client"]: c["projects"] for c in clients.listing()["clients"]}
    assert sorted(listed["ana-souza"]) == ["antigo", "novo"]

    monkeypatch.delenv("EA_PROJECTS_DIR")  # read from the repo's .env when not in the environment
    env = tmp_path / ".env"
    env.write_text(f"EA_PROJECTS_DIR={desk}\n", encoding="utf-8")
    monkeypatch.setattr(P, "ROOT", tmp_path)
    assert P.projects_dir() == desk


def test_sync_map_finds_recorder_dropouts(project):
    """A mixer that drops samples gets shorter instead of silent: one offset only fits until the
    first drop. --map must find each drop (and not be fooled by circular-correlation wraps)."""
    import wave

    import numpy as np

    from editassist.project import read_json, write_json
    from editassist.sync import RATE, drift_map

    rng = np.random.default_rng(7)
    n = 150 * RATE
    env = np.repeat(rng.uniform(0.05, 1, n // 800 + 1), 800)[:n]  # syllable-ish loudness changes
    cam = (rng.standard_normal(n) * env * 0.2).astype(np.float32)
    s = lambda t: int(t * RATE)  # noqa: E731
    mix = np.concatenate([cam[s(10):s(60)], cam[s(62.5):s(100)], cam[s(104):s(140)]])  # 2.5 s, 4 s lost
    cat = read_json(project.path("work", "media.json"))
    for sid, x in (("cam_wide", cam), ("mixer", mix)):
        f = project.path("work", "audio", f"{sid}.wav")
        with wave.open(str(f), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(RATE)
            w.writeframes((x * 32767).astype(np.int16).tobytes())
        cat[sid] = {"path": f"input/{sid}.wav", "analysis_audio": f"work/audio/{sid}.wav", "duration": len(x) / RATE}
    write_json(project.path("work", "media.json"), cat)

    r = drift_map(project, "cam_wide", "mixer")
    assert [round(g["shift"], 2) for g in r["segments"]] == [10.0, 12.5, 16.5]
    assert [g["missing"] for g in r["gaps"]] == pytest.approx([2.5, 4.0], abs=0.01)
    assert [g["ref_from"] for g in r["gaps"]] == pytest.approx([60, 100], abs=0.3)
    assert r["overlaps"] == []


def test_sync_build_from_map_keeps_lips_in_sync_across_drops(project):
    """--build places each kept recorder range on the camera at the same moment, so the picture
    skips the camera time the recorder lost; a range across a drop is refused."""
    from editassist.project import read_json, write_json
    from editassist.sync import build_from_map

    cat = read_json(project.path("work", "media.json"))
    for sid in ("cam_wide", "cam_close", "mixer"):
        cat[sid] = {"path": f"input/{sid}.mp4", "duration": 200.0}
    write_json(project.path("work", "media.json"), cat)
    segs = [{"other_in": 0, "other_out": 50, "shift": 10.0}, {"other_in": 50, "other_out": 90, "shift": 12.5}]
    write_json(project.path("work", "sync_map", "mixer__cam_wide.json"), {"ref": "cam_wide", "other": "mixer", "segments": segs})
    write_json(project.path("work", "sync_map", "cam_close__cam_wide.json"),
               {"ref": "cam_wide", "other": "cam_close", "segments": [{"other_in": 0, "other_out": 200, "shift": -3.0}]})

    r = build_from_map(project, "cam_wide", "mixer", "cam_close", [(5, 48), (52, 80)])
    tl = T.load(project)
    v, a = (T.track(tl, n)["clips"] for n in ("V1", "A1"))
    assert r["duration"] == pytest.approx(71)
    assert [(c["in"], c["start"]) for c in a] == [(5, 0), (52, 43)]
    assert [c["in"] for c in v] == pytest.approx([18, 67.5])  # mixer + shift on wide, + 3 s on close
    with pytest.raises(SystemExit):
        build_from_map(project, "cam_wide", "mixer", "cam_close", [(40, 60)])
