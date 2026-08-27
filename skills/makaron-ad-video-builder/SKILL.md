---
name: makaron-ad-video-builder
description: Assemble one complete localized Makaron vertical ad through a single project-bound chat-driven Remotion run using a comparison image, effect video, localized workflow video, fixed Logo CTA, one campaign BGM, and five voiceover lines.
---

# Makaron Ad Video Builder

Run only inside the persistent project already bound to the target Skill. Never use `--project auto`, a hard-coded shared project, standalone generation, or a separate TTS project.

Create the complete 9:16, 30fps, H.264/AAC final with this locked order: independently generated target-Skill Hook video; simultaneous comparison image; locale-correct synthetic workflow video; independently generated full effect/result video; fixed Logo CTA. Target 1080×1920 and never accept below 720×1280. Keep the complete video between 15 and 20 seconds, aiming for 18. Use a 2.5–5 second Hook, exactly 2.5 seconds of comparison, 3.5–4.5 seconds of workflow, at least 3 seconds of result, and exactly 2–3 seconds of the configured CTA excerpt. Hook and result must not reuse the same shot, action, camera path, or source frames.

Use one project-bound `makaron chat` request with the built-in `tiktok-video` builder and direct the Makaron Agent to compose/export through its Remotion runtime. Generate one continuous Seed Audio voiceover first, then derive five Caption JSON objects with real `startMs`/`endMs` timing and make scene boundaries contain the assigned speech: line 1 Hook, line 2 comparison, lines 3–4 workflow, line 5 result. No line crosses a scene or CTA. Burn exactly one subtitle set: white with black outline, no background bar, horizontally centered inside the safe content region with centered text/flex alignment and never left-aligned, maximum two lines and 20 visible characters per line. Do not place literal `\n` or hard-coded newline characters in caption text/display; use measured automatic wrapping. For Meta Reels derive the safe insets from ratios equivalent to top and caption top 250/1920, bottom 340/1920, left 90/1080, and right 180/1080; do not use the old 140px or superseded 270px top offset. English is uppercase while Japanese and Cantonese retain natural case. Finish TTS before CTA and never truncate the final word.

Mute original audio from the effect, workflow, and fixed CTA videos. Use the supplied campaign BGM only, loop that same track from 0.0 seconds through the final CTA frame at relative volume 0.22 under TTS, never switch tracks, and apply only a gentle final fade. Do not use CTA source audio, local edge-tts, FFmpeg concat/amix, ASS subtitles, or PIL final composition.

Use `seedance-2-0`, then `kling`, then `grok` only after the current node fails. Return one complete MP4 plus a timing/safe-zone QC summary. Missing/ending BGM, CTA source audio, missing TTS, below-720p output, final outside 15–20 seconds, black frames, wrong locale, caption/scene spill, repeated Hook/result, or safe-zone collision is `REROLL`; identity/product loss, policy risk, project isolation failure, or three failed attempts is `BLOCKED`.
