---
name: makaron-ad-video-builder
description: Assemble one complete localized Makaron vertical ad through a single project-bound chat-driven Remotion run using a comparison image, effect video, localized workflow video, fixed Logo CTA, one campaign BGM, and five voiceover lines.
---

# Makaron Ad Video Builder

Run only inside the persistent project already bound to the target Skill. Never use `--project auto`, a hard-coded shared project, standalone generation, or a separate TTS project.

Create the complete 1080×1920, 30fps, H.264/AAC final with this locked order: strongest-result Hook video; simultaneous comparison image; locale-correct synthetic workflow video; full effect/result video; fixed Logo CTA. Keep the complete video between 15 and 20 seconds, aiming for 18. Use a 2.5–5 second Hook, exactly 2.5 seconds of comparison, 3.5–4.5 seconds of workflow, at least 3 seconds of result, and exactly 2–3 seconds of the configured CTA excerpt.

Use one project-bound `makaron chat` request and direct the Makaron Agent to compose/export through its internal Remotion workflow. Generate one continuous Seed Audio voiceover from the exact five lines using a natural energetic young-adult female voice. Burn exactly one subtitle set synchronized to all spoken lines, top-aligned 140px from the top, white with black outline, no background bar, and maximum two lines; English is uppercase while Japanese and Cantonese retain natural case. Finish TTS before CTA and never truncate the final word.

Mute original audio from the effect, workflow, and fixed CTA videos. Use the supplied campaign BGM only, loop that same track from 0.0 seconds through the final CTA frame at relative volume 0.22 under TTS, never switch tracks, and apply only a gentle final fade. Do not use CTA source audio, local edge-tts, FFmpeg concat/amix, ASS subtitles, or PIL final composition.

Use `seedance-fast`, then `kling`, then `grok` only for a failed final node. Return one complete MP4 plus concise QC. Missing/ending BGM, CTA source audio, missing TTS, wrong dimensions, final outside 15–20 seconds, black frames, wrong locale, or subtitle collision is `REROLL`; identity/product loss, policy risk, project isolation failure, or three failed attempts is `BLOCKED`.
