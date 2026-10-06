---
name: highlight
description: Find the best self-contained moments in long footage (podcast, stream, interview) and turn them into short clips for Reels/TikTok/Shorts. Use for "find clips", "make shorts from this", "best moments". One highlights/recap video of an event cut to music: recap skill.
---
# highlight

1. Ingest + transcribe (+ speakers skill for multi-person footage). Read the full transcript(s).
2. Pick 3-10 moments that stand alone: a strong first line (no "so, as I said"), one idea, a payoff
   or punchline, 20-60 s (or the user's target). Score each 1-10 for hook, clarity, payoff.
3. Present the list (timestamps, first line, score, why) and let the user choose before building.
4. For each chosen clip, make a separate project so timelines don't collide:
   `uv run ea new <p>-short-01 --width 1080 --height 1920`, copy or symlink the source into its
   `input/` (copy on Windows), ingest, transcribe (fast: reuse language), `ea cut` with that one segment +
   `--tighten`, then reformat (9:16) and subtitles (style from memory, default `bold`).
