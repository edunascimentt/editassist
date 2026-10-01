---
name: thumbnail
description: YouTube/Shorts thumbnail from the best frame (sharp, well exposed, big face) or a generated background, with bold readable text. Use for "make a thumbnail", "capa", "cover image".
---
# thumbnail

1. Candidates: `uv run ea thumbnail <p> [-n 12]`, then open `work/thumbs/candidates.jpg` (tiles labelled
   `#index timeline-time score`). Prefer an expressive face (open mouth, surprise, pointing) over
   the highest score.
2. Headline: 2-5 words, a different hook from the title, never the title repeated. Mark one or two
   words with `*asterisks*` for the accent colour.
3. Compose: `uv run ea thumbnail <p> --pick <index> --text "Edite com *IA*" [--accent "#FFE500"] [--aspect 16:9|9:16]`.
   The face goes on one third and the text on the other half, over a dark gradient. Output:
   `output/<name>_thumb.jpg` (kept under 2 MB).
4. Generated background (higgsfield skill, e.g. a Soul image), then `--image work/higgsfield/<file>.png`.
5. Look at the result at small size (YouTube shows ~320 px): is the text readable, is the face clear?
   Make 2-3 variants (different frame or text) and let the user choose.
