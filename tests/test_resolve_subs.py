from editassist.resolve_subs import chunks, hyphenate, reflow, srt, too_long, wrap


def test_wrap_never_exceeds_and_breaks_at_comma():
    for text in ["A submissão, eu estou junto", "é sobre eu estar junto na mesma missão.",
                 "a gente tem essas questões distorcidas"]:
        assert all(len(l) <= 15 for l in wrap(text, 15))
    # the voice pauses at the comma: "A submissão," / "eu estou junto", not "A submissão, eu"
    assert wrap("A submissão, eu estou junto", 15) == ["A submissão,", "eu estou junto"]


def test_wrap_does_not_end_line_on_function_word():
    for l in wrap("ele precisa estar à frente de alguém no sentido de ser melhor", 15)[:-1]:
        assert l.split()[-1].lower() not in {"de", "a", "o", "no", "que", "à"}


def test_long_words_are_hyphenated_to_fit():
    assert hyphenate("pré-adolescência,", 15) == ["pré-", "adolescência,"]
    parts = hyphenate("responsabilidade.", 15)
    assert len(parts) == 2 and parts[0].endswith("-") and all(len(p) <= 15 for p in parts)
    assert "".join(parts).replace("-", "") == "responsabilidade."


def test_chunks_avoid_lone_short_word_cue():
    # greedy filling gave ["E essa palavra,", "o significado"] + ["dela"] (0.4 s flash)
    assert chunks("E essa palavra, o significado dela", 15, 2) == [["E essa palavra,"], ["o significado", "dela"]]


def test_reflow_keeps_text_times_split_on_words_and_limits():
    cue = {"start": 10.0, "end": 14.0, "text": "e nós caminhamos juntos, lado a lado."}
    words = [{"word": w, "start": 10.0 + i * 0.5} for i, w in
             enumerate(["e", "nós", "caminhamos", "juntos,", "lado", "a", "lado."])]
    out = reflow([cue], words, 15, 2)
    assert " ".join(c["text"].replace("\n", " ") for c in out) == cue["text"]
    assert not too_long(out, 15) and all(c["text"].count("\n") <= 1 for c in out)
    assert out[0]["start"] == 10.0 and out[-1]["end"] == 14.0
    assert all(a["end"] == b["start"] for a, b in zip(out, out[1:]))  # contiguous, like the original
    assert out[1]["start"] == 11.5  # second cue starts on "juntos," as spoken


def test_reflow_without_words_and_minimum_duration():
    cue = {"start": 0.0, "end": 1.2, "text": "Ai, porque depois que eu fui mãe,"}
    out = reflow([cue], None, 15, 2)
    assert all(c["end"] - c["start"] >= 0.5 - 1e-9 for c in out)
    assert "1\n00:00:00,000 --> " in srt(out)


def test_short_cue_untouched():
    out = reflow([{"start": 1.0, "end": 2.0, "text": "Eu tenho que vencer."}], None, 15, 2)
    assert out == [{"start": 1.0, "end": 2.0, "text": "Eu tenho\nque vencer."}]  # not ending on "que"


def test_resolve_line_separator_counts_as_line_break():
    # Resolve hands back "estar junto na mesma missão.": two lines of <= 15, already done
    from editassist.resolve_subs import _cue_lines
    assert _cue_lines("estar junto na mesma missão.") == ["estar junto na", "mesma missão."]


def test_hyphenated_word_never_split_across_cues():
    # "responsa-" alone for 0.5 s, then "bilidade / pra alguém." (EP23 CORTE 4, 2026-10-13)
    fast = lambda a, b: 0.3 if (a, b) == (0, 2) else 1.0  # noqa: E731  "responsa- bilidade" spoken fast
    for text in ["responsabilidade pra alguém.", "ter transferido responsabilidade pra alguém."]:
        for cue in chunks(text, 15, 2, fast):
            assert not cue[-1].endswith("-")


def test_one_line_captions_short_cue_never_negative():
    # 0.9 s cue cut into several one-line pieces gave a -0.07 s piece (2026-10-13)
    cue = {"start": 5.0, "end": 5.9, "text": "mas eles sempre falam isso pra mim"}
    words = [{"word": w, "start": 5.0 + i * 0.02} for i, w in enumerate(cue["text"].split())]
    out = reflow([cue], words, 15, 1)
    assert all("\n" not in c["text"] for c in out)
    assert all(c["end"] - c["start"] > 0.1 for c in out)
    assert out[-1]["end"] == 5.9


def test_one_line_hyphenated_word():
    out = reflow([{"start": 0.0, "end": 2.0, "text": "é a nossa responsabilidade."}], None, 15, 1)
    assert all("\n" not in c["text"] and len(c["text"]) <= 15 for c in out)
