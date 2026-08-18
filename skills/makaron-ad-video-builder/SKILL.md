---
name: makaron-ad-video-builder
description: Assemble one locale of a Makaron vertical ad from a comparison image, target-Skill effect video, localized workflow video, five voiceover lines, and optional CTA. Use as the final en, ja, or yue assembly node called by makaron-ad-creator.
---

# Makaron Ad Video Builder

Run only inside the persistent project already bound to the target Skill. Never use `--project auto`, a hard-coded shared project, standalone generation, or a separate TTS project.

Create exact 1080×1920, 30fps, H.264/AAC, 15–18 second MP4 with this locked order: 0–2.5s strongest result hook; 2.5–5s simultaneous comparison; 5–9s locale-correct synthetic workflow; 9–15s full result; remaining time CTA. Generate one continuous natural-locale voiceover from the exact five lines, one synchronized upper-safe subtitle set, and licensed/new instrumental BGM at least 8dB under voiceover. Mute source audio. Do not truncate the final word, add duplicate title cards, or invent claims.

Use `seedance-fast`, then `kling`, then `grok` only for a failed final node. Return one MP4 plus concise QC. Missing audio, wrong dimensions, duration over 18s, black frames, wrong locale, or subtitle collision is `REROLL`; identity/product loss, policy risk, project isolation failure, or three failed attempts is `BLOCKED`.

