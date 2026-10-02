"""End-to-end checks of the `ea` tools on synthetic media. Run: uv run pytest -q"""
from __future__ import annotations

import json
import shutil
import subprocess

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
    assert ws[0]["start"] == pytest.approx(0.08, abs=0.02)  # remapped to timeline time (pad 0.08)
    res = subs(project, style="bold")
    assert (project.path(res["srt"])).read_text(encoding="utf-8").startswith("1\n00:00:00,0")


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
