---
name: preferences-quiz
description: Short questionnaire that learns how this user edits (editor, platform, pacing, captions, audio, look, b-roll, vocabulary, brand) and writes the answers to their private editing memory. Use for "questionário de preferências", "me pergunta como eu edito", "set up my style", "learn my preferences", a new teammate's first edit, or when preferences.md is still the empty template. Re-runnable per section ("change my caption preferences").
---
# preferences-quiz

Goal: in about 3-5 minutes the user's `<memory>/preferences.md` holds real defaults, so the first
edit already looks like theirs. `<memory>` = the folder `uv run ea memory` prints (private memory-os
global tier, or the gitignored `memory/` fallback). Write rules come from the style-profile skill.

Talk in the user's language. Ask with AskUserQuestion: at most 4 questions per call, 2-4 options each
(the tool adds "Other" for free text), most common option first. Never a wall of questions in chat.
API keys are NOT part of this quiz (editassist-setup does that).

## 0. Start
1. `uv run ea memory` (missing files: `uv run ea memory --init`), then read `preferences.md` and `styles/`.
2. Summarise in 2-3 lines what is already set (lines without `<...>` placeholders) and what is empty.
3. Ask the mode:
   - **Quick** (3 questions: editor, platform + frame, cut tightness): first-run or "I'm busy".
   - **Full** (rounds 1-6, ~5 min): the default when preferences are mostly empty.
   - **One section**: when they asked to change something specific, or most is already set.
   In Full mode skip questions whose answer is already in the file, unless they asked to redo it.

## 1. Delivery
- Editor: DaVinci Resolve Studio / Resolve (free) / Premiere Pro / render mp4 only (Other: After Effects, Final Cut).
- Main platform: YouTube / Reels-TikTok-Shorts / podcast / several (ask which first).
- Default frame: 16:9 1920x1080 / 9:16 1080x1920 / both (vertical cut of every video).
- Language spoken in their videos: Portuguese / English / Spanish (Other).

## 2. Pacing
- Silence cuts: relaxed / normal / tight / don't cut silences.
- Fillers ("tipo", "né", "ãh", "like"): remove all / only when repeated / keep.
- Zooms: none / punch-ins to hide jump cuts / also emphasis zooms on key phrases.
- Transitions: hard cuts only / dissolve at chapter breaks / fade in-out at start and end.

## 3. Captions
- Style: clean / bold / boxed / no captions by default.
- Words per line: 2-3 (shorts) / 4 / 6+ (long form).
- Position: bottom / centre / top.
- Accent colour: yellow #FFE500 / white only / brand colour (Other: hex).

## 4. Audio
- Music: never / subtle bed under dialogue / energetic / they bring their own tracks.
- Music level under dialogue: low / medium / present.
- Sound effects: none / subtle (whooshes on b-roll) / punchy (hits on text, risers).
- If they use ElevenLabs and no voice is set: offer `uv run ea voices` and store the voice NAME (never a key).

## 5. Look and b-roll
- Colour: natural (auto balance only) / warm / film / punchy (Other: cool, bw, their own .cube LUT path).
- B-roll source, in order of preference: own footage only / stock (Pexels) OK / AI-generated OK.
  If AI is OK, ask their per-generation cap in USD (→ `EA_HF_MAX_USD` in `.env`, not in memory).
- Thumbnails: big face + 2-4 word text / text only / they make their own.

## 6. Free text (plain chat message, one at a time, each skippable)
- Names, brands and jargon Whisper gets wrong ("DaVinte → DaVinci"). → `## Vocabulary`
- Brand: colours (hex), font, logo file path, things to always include (intro, CTA, end card). → `## Brand`
  (the user's own channel; a client's brand goes to `clients/<client>/preferences.md`, `ea client new`)
- Anything they hate seeing in edits (e.g. "no emoji in captions", "never cut mid-breath"). → `## Never`

## Mapping (answer → what to write)
| Answer | Line in preferences.md |
|---|---|
| relaxed / normal / tight | `Silence cut: min silence 0.7s pad 0.12s` / `0.45s pad 0.08s` / `0.3s pad 0.06s` (`ea silence-cut --min-silence --pad`) |
| don't cut silences | `Silence cut: off (only remove fillers if asked)` |
| frame | `Default frame: 1920x1080 @ 30` / `1080x1920 @ 30`; "both" adds `Also deliver a 9:16 version (reformat skill)` |
| platform | `Default platform: youtube` etc. (`ea render --preset`; Reels/TikTok → `instagram`/`tiktok`) |
| caption style / words | `Captions: bold, 3 words per line, centre, accent #FFE500` (`ea subtitles --style`) |
| music level low / medium / present | `Music gain around -22 / -18 / -14 dB under dialogue, ducked` |
| colour | `Look: auto balance + warm` (`ea color --auto --look warm`); a LUT path is stored as given |
| zooms | `Zoom: punch every 2 cuts` (`ea zoom --punch --every 2`), or `+ emphasis zooms on key phrases` |

## Writing
- Edit lines in place in `<memory>/preferences.md`; don't append a second line that contradicts one.
  Sections missing from an older file (Look, Brand, Never...): add them, matching the template in
  `memory.template/preferences.md`.
- Format: `- <preference> (<YYYY-MM-DD>, quiz: "<their answer>")`. Free-text answers: quote them.
- Leave untouched any line the quiz didn't ask about. Remove `<...>` placeholders you filled.
- Never write keys, client names they didn't offer, or anything about third parties. Never write
  taste to `.claude/_memory/` (that tier is shared with the whole team).
- Different defaults for different kinds of video (e.g. YouTube long form vs shorts): offer to save
  the second set as a named style `<memory>/styles/<name>.md` (copy `styles/example-shorts.md`'s shape).

## Finish
Show a short before → after of what changed (only changed lines), say where the file lives, and that
they can change anything later by just telling the editor ("captions maiores", "corta mais seco").
If this ran from editassist-setup, return to its next step.
