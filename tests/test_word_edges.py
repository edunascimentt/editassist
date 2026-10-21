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
