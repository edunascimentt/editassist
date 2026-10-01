---
name: visual-index
description: Understand what is ON SCREEN. Detects shots, extracts keyframes and contact sheets, then you look at them and write work/visual_index.json. Use before choosing b-roll from the user's own footage, picking takes, or any request that depends on visuals ("use the shot of the coffee").
---
# visual-index

1. `uv run ea scenes <p> [--threshold 0.3]` (lower threshold = more cuts).
2. Open every `work/frames/<id>/contact_*.jpg` with your image reading tool. Each tile is labelled
   `#scene start-end`.
3. Write `work/visual_index.json`:
   ```json
   {"<media id>": [{"scene": 0, "start": 0.0, "end": 4.2, "shot": "medium close-up",
     "subject": "host talking to camera", "tags": ["indoor", "desk", "talking-head"],
     "quality": "good | soft focus | shaky | overexposed", "broll_candidate": false}]}
   ```
4. Use it to answer "where is X" questions and to pick b-roll (`broll_candidate: true`).

Keep descriptions short and concrete; they are for searching, not prose.
