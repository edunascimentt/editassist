---
name: metadata
description: Publishing package. Title options, description, YouTube chapters with timestamps, tags, pinned comment. Use for "write the title/description", "chapters", "capítulos", "metadata", when delivering a YouTube video.
---
# metadata

1. `uv run ea transcript <p>` writes `output/<name>_transcript.txt`, the transcript of the EDITED video
   with timeline timestamps. Read all of it.
2. Chapters: write `work/chapters.json` `[{"time": 0, "title": "..."}]` (timeline seconds) at real topic
   changes, then `uv run ea chapters <p> work/chapters.json`. Fix every listed problem: first chapter
   at 0, at least 3 chapters, each at least 10 s. Chapters also become timeline markers in the NLE.
3. Write `output/<name>_metadata.md`:
   - 3-5 title options (under 60 characters, the main promise first, no clickbait the video
     doesn't deliver)
   - description: two hook lines (visible before "more"), a summary, the chapter block from
     `output/<name>_chapters.txt`, links and credits (Pexels credits are in media.json `generated.credit`)
   - 10-15 tags, and a pinned comment
4. Use the language and tone from `memory/preferences.md`; mention the channel's recurring CTA if
   one is stored there.
