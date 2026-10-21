"""Word-edge regressions from podcast cortes (2026-10-20): Portuguese words dropped
as hesitations, and captions for words Whisper stretched over the pause before a cut."""
from __future__ import annotations

import pytest

from editassist import subtitles
from editassist.cut import is_filler
from editassist.transcribe import heard_start


def test_article_a_and_portuguese_um_are_not_fillers():
    assert not is_filler("A", "pt")  # was matched as "ã" after accent folding
    assert not is_filler("a,", "pt")
    assert not is_filler("um", "pt")  # "em um ano e meio"
    assert not is_filler("Um", "pt-BR")
    assert is_filler("um", "en") and is_filler("um")
    for w in ("ãh", "Ãh,", "hum", "Hmm...", "éé"):
        assert is_filler(w, "pt"), w


def test_heard_start_trims_a_stretched_span_only():
    assert heard_start({"word": "A", "start": 3790.70, "end": 3791.56}) == pytest.approx(3791.29)
    assert heard_start({"word": "Segue", "start": 3840.46, "end": 3842.12}) == pytest.approx(3841.37)
    normal = {"word": "pessoal,", "start": 1.0, "end": 1.32}
    assert heard_start(normal) == 1.0


def test_caption_skips_a_word_whose_voice_falls_after_the_cut(monkeypatch):
    # "...o aluguel." kept, cut at 3840.74; Whisper puts "Segue" at 3840.46-3842.12 but the voice
    # only starts after 3840.8, so it must not be captioned
    media = "/m/ep.mp4"
    ws = [{"word": "o", "start": 3840.16, "end": 3840.26}, {"word": "aluguel.", "start": 3840.26, "end": 3840.46},
          {"word": "Segue", "start": 3840.46, "end": 3842.12},
          {"word": "A", "start": 3790.70, "end": 3791.56}, {"word": "gente", "start": 3791.56, "end": 3791.72}]
    monkeypatch.setattr(subtitles, "media_by_id", lambda p: {"ep": {"path": media}})
    monkeypatch.setattr(subtitles, "words", lambda p, sid: ws)
    tl = {"tracks": [{"name": "A1", "kind": "audio", "clips": [
        {"media": media, "in": 3840.0, "out": 3840.74, "start": 0.0},
        {"media": media, "in": 3791.38, "out": 3791.80, "start": 0.74}]}]}
    out = [w["word"] for w in subtitles.timeline_words(None, tl)]
    assert out == ["o", "aluguel.", "A", "gente"]


def test_same_length_vocab_fix_replaces_word_for_word():
    # a fix written with context words must not merge them into one 18-char caption token
    ws = [{"word": "mantém,", "start": 1.0, "end": 1.4}, {"word": "por", "start": 1.4, "end": 2.1},
          {"word": "menos,", "start": 2.1, "end": 3.4}, {"word": "por", "start": 3.4, "end": 3.6}]
    out = subtitles.apply_fixes(ws, ["mantém, por menos,=mantém, pelo menos,"])
    assert [(w["word"], w["start"]) for w in out] == [("mantém,", 1.0), ("pelo", 1.4), ("menos,", 2.1), ("por", 3.4)]
    assert subtitles.apply_fixes(out, ["mantém, por menos,=mantém, pelo menos,"]) == out
    # different length still makes one token (names)
    merged = subtitles.apply_fixes([{"word": "loud", "start": 0, "end": 1}, {"word": "control.", "start": 1, "end": 2}],
                                   ["loud control=launch control"])
    assert [w["word"] for w in merged] == ["launch control."]


def test_vocab_fix_spans_two_whisper_segments():
    from editassist.vocab import fix_transcript

    t = {"segments": [
        {"start": 0, "end": 2, "text": "No apartamento...", "words": [
            {"word": "No", "start": 0.0, "end": 0.5}, {"word": "apartamento...", "start": 0.5, "end": 0.9}]},
        {"start": 0.9, "end": 3, "text": "Apartamento, você", "words": [
            {"word": "Apartamento,", "start": 0.9, "end": 1.3}, {"word": "você", "start": 1.3, "end": 1.8}]}]}
    assert fix_transcript(t, ["apartamento... Apartamento,=apartamento,"]) == 1
    assert [w["word"] for w in t["segments"][0]["words"]] == ["No", "apartamento,"]
    assert t["segments"][0]["words"][1]["end"] == 1.3
    assert [w["word"] for w in t["segments"][1]["words"]] == ["você"]
    assert "_seg" not in t["segments"][1]["words"][0]


def test_qa_ignores_a_split_in_silence_but_not_in_the_voice(project):
    """Whisper stretched "Hum" back over the pause before it: a cut in that silent stretch is not a
    mid-word cut (qa warned on clean cuts before "A gente", 2026-10-21); a cut in the tone still is."""
    import json

    from editassist import timeline as T
    from editassist.qa import check

    f = project.path("work", "transcripts", "cam_a.json")
    t = json.loads(f.read_text(encoding="utf-8"))
    for sg in t["segments"]:
        for w in sg["words"]:
            if w["word"] == "Hum":
                w["start"] = 5.0  # tone only plays 6.0-6.4
    f.write_text(json.dumps(t), encoding="utf-8")
    media = "input/cam_a.mp4"

    def splits(cut_in):
        tl = T.new(project)
        T.track(tl, "A1")["clips"] = [{"media": media, "in": 0.4, "out": 1.6, "start": 0.0},
                                      {"media": media, "in": cut_in, "out": 6.5, "start": 1.2}]
        T.save(project, tl)
        return [i for i in check(project)["issues"] if "splits the word 'Hum'" in i["issue"]]

    assert not splits(5.85)  # silent frame before the tone
    assert splits(6.2)  # inside the tone


def test_zoom_focus_keeps_the_face_the_crop_frames(monkeypatch):
    """A podcast wide: the host nearer the camera has the biggest face, the vertical crop frames the
    guest on the left. The punch-in must centre on the guest, not slide towards the host."""
    from editassist import reformat, zoom

    guest, host = (0.28, 0.45, 0.010), (0.72, 0.42, 0.016)
    assert reformat.pick_face([[guest, host]] * 4, prefer=0.30)[0] == pytest.approx(0.28)
    seen = {}

    def fake_face_center(path, t0, t1, samples=8, prefer=None):
        seen["prefer"] = prefer
        return reformat.pick_face([[guest, host]] * 4, prefer)

    monkeypatch.setattr(zoom, "face_center", fake_face_center)

    class P:
        def abs(self, p):
            return p

    c = {"media": "ep.mp4", "in": 0, "out": 2, "crop": {"x": 300, "y": 0, "w": 606, "h": 1080}}
    x, _ = zoom._focus(P(), c, {"width": 1920, "height": 1080})
    assert seen["prefer"] == pytest.approx((300 + 303) / 1920)
    assert x == pytest.approx((0.28 * 1920 - 300) / 606, abs=1e-3)


def test_captions_change_exactly_at_cuts():
    """The user's rule (2026-10-21): a caption ends when its clip ends. The 0.25 s hold ran "de milhões."
    5 frames into the next shot; zoom cuts and camera switches fell inside captions."""
    w = lambda t, a, b: {"word": t, "start": a, "end": b}
    lines = [
        {"start": 1.5, "end": 2.15, "words": [w("de", 1.5, 1.6), w("milhões.", 1.6, 2.05)]},     # hold over 2.1
        {"start": 2.15, "end": 3.3, "words": [w("Agora", 2.15, 2.5), w("você", 2.5, 2.9), w("tem,", 2.9, 3.3)]},
        {"start": 4.76, "end": 5.6, "words": [w("do", 4.76, 4.9), w("filho", 4.9, 5.6)]},          # starts 0.04 early
        {"start": 7.0, "end": 7.9, "words": [w("vaidade.", 7.0, 7.85)]},                           # 0.05 s tail
    ]
    out = subtitles.fit_to_cuts(lines, [2.1, 2.8, 4.8, 7.85])
    spans = [(l["start"], l["end"], " ".join(x["word"] for x in l["words"])) for l in out]
    assert spans == [(1.5, 2.1, "de milhões."), (2.15, 2.8, "Agora você"), (2.8, 3.3, "tem,"),
                     (4.8, 5.6, "do filho"), (7.0, 7.85, "vaidade.")]
    assert all(l["start"] <= x["start"] <= x["end"] <= l["end"] for l in out for x in l["words"])
    for k in [2.1, 2.8, 4.8, 7.85]:
        assert not any(l["start"] + 1e-3 < k < l["end"] - 1e-3 for l in out)
