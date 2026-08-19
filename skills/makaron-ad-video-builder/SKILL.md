---
name: makaron-ad-video-builder
description: Assemble the first four parts of one localized Makaron vertical ad from a comparison image, target-Skill effect video, localized workflow video, and five voiceover lines. Use as the en, ja, or yue body node before makaron-ad-creator appends its fixed Logo CTA locally.
---

# Makaron Ad Video Builder

Run only inside the persistent project already bound to the target Skill. Never use `--project auto`, a hard-coded shared project, standalone generation, or a separate TTS project.

Create the 1080×1920, 30fps, H.264/AAC body with this locked order: strongest-result Hook video; simultaneous comparison image; locale-correct synthetic workflow video; full effect/result video. Keep the body between 12 and 17 seconds, aiming for 15. Use a 2.5–5 second Hook, exactly 2.5 seconds of comparison, 3.5–4.5 seconds of workflow, and at least 3 seconds of result. Use the longer Hook only when the Skill action is not legible in 2.5 seconds, and extend the result only long enough for one complete payoff. Generate one continuous natural-locale voiceover from the exact five lines using the configured TTS voice, defaulting to a natural energetic young-adult female voice, plus one synchronized upper-safe subtitle set and licensed/new instrumental BGM at least 8dB under voiceover.

Do not generate a CTA, end card, duplicate title card, or black tail. The CLI appends a fixed 2–3 second Makaron Logo CTA excerpt after this body with local FFmpeg, preserving its content and audio without model involvement. Finish TTS, subtitles, and BGM cleanly at the body endpoint. Mute source audio from the effect and workflow videos. Do not truncate the final spoken word or invent claims.

Use `seedance-fast`, then `kling`, then `grok` only for a failed final node. Return one MP4 plus concise QC. Missing audio, wrong dimensions, body outside 12–17 seconds, black frames, wrong locale, or subtitle collision is `REROLL`; identity/product loss, policy risk, project isolation failure, or three failed attempts is `BLOCKED`.
