---
name: higgsfield
description: Generate video shots and images with the Higgsfield API (Kling, Seedance, Wan, MiniMax, Soul, Cinema Studio...): b-roll that doesn't exist in the footage, image-to-video from a frame of the user's clip, first/last-frame transitions, extending or restyling a shot. Use when b-roll must be generated, or the user asks for AI-generated shots/images.
---
# higgsfield

Needs `HF_API_KEY_ID` + `HF_API_KEY_SECRET` in `.env` (console.higgsfield.ai). Every generation
costs credits.

1. **Pick a model**: `uv run ea hf models [--kind video|image] [--search kling]`. Defaults when the
   user has no preference (check `<memory>/preferences.md` first):
   - realistic b-roll from text: a `kling-video/v3.0/...text-to-video` or `bytedance/seedance-2.5/text-to-video`
   - animate a still or a frame of the user's footage: an `...image-to-video` workflow
   - stills (thumbnails, inserts): `higgsfield-ai/soul/v2/standard`
   The catalog comes from the docs and changes; don't assume an endpoint exists, look it up.
2. **Read the schema** before writing arguments: `uv run ea hf schema <endpoint>`. Field names,
   durations, aspect ratios and required fields differ per model. Match `aspect_ratio` to the
   timeline (`9:16` for vertical) and duration to the slot you're filling.
3. **Write the prompt** like a shot list: subject, action, camera move, lens, light, mood, style
   matching the footage ("handheld, 35mm, warm tungsten, shallow depth of field").
4. **Estimate and confirm**: `uv run ea hf estimate <endpoint> --args args.json`. Tell the user the
   credits/USD before generating; for batches, give the total.
5. **Generate**: `uv run ea hf generate <p> <endpoint> --args args.json [--file image_url=work/frames/cam_a/s003.jpg] [--name coffee]`
   - `--file field=path` uploads a local file into that field (repeat for list fields like `image_urls`).
     Grab a frame first when needed: `ffmpeg -ss <t> -i input/<clip> -frames:v 1 work/frames/hf_<t>.png`.
   - It estimates, refuses above `EA_HF_MAX_USD` (default $2) unless `--yes`, submits with an
     idempotency key, waits, downloads to `work/higgsfield/` and registers the file in media.json.
   - Timed out or terminal closed: `uv run ea hf fetch <p> <request_id>` (ids are in `work/higgsfield/requests.jsonl`).
6. **Use it**: place on V2 per the b-roll skill. Look at a frame of the result before placing it;
   regenerate only with a changed prompt, and say why.

`failed` / `nsfw` results are not charged. Outputs expire on Higgsfield after ~7 days, which is why
files are downloaded immediately.
