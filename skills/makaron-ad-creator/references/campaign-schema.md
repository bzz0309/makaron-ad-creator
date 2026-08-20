# Campaign schema

## Stable fields

- `version`: `1`.
- `campaign_id`: stable filesystem-safe label.
- `input_image`: absolute path after validation.
- `target_skill`: exact `id`, human `name`, factual `core`, and optional `transformation_type`.
- `project_binding`: `strategy=one_skill_one_persistent_project`, matching `skill_id`, and explicit non-`auto` `project_id`.
- `rights`: all three booleans must be true before generation.
- `offer`: substantiated value proposition, CTA, and optional destination URL.
- `locales`: one or more selected mappings from the fixed set `en→en`, `ja→ja`, `yue→zh-Hant`; defaults to all three.
- `automation.executor`: `makaron` for direct unattended execution or `agent` for request handoff.
- `automation.max_attempts`: maximum `3`.
- `automation.builder_skill_id`: defaults to Makaron's built-in `tiktok-video` Remotion builder; an explicit compatible builder can override it.
- `audio.tts_voice`: defaults to `natural energetic young-adult female`.
- `audio.bgm_prompt`: original instrumental direction for the campaign's one `makaron music create` node; defaults to at least 20 seconds, no vocals, no early fade-out, and loop-friendly.
- `audio.bgm_style`: `--style` value for `makaron music create`.
- `audio.bgm_volume`: Remotion relative mix volume under TTS, default `0.22` and maximum `0.5`.
- `audio.mute_source_audio`: forced to `true`.
- `audio.cta_source_audio`: forced to `false`.
- `assets.logo_cta`: defaults to portable URI `bundled://makaron-logo-cta.mp4`, resolved to the fixed source inside the currently installed CLI; an explicit path overrides it.
- `assets.logo_cta_start_seconds`: deterministic excerpt start, default `0`, matching the supplied finished-ad references.
- `assets.logo_cta_excerpt_seconds`: final CTA excerpt duration from `2` through `3`, default `3`.
- `output.minimum_duration_seconds`: final minimum, default `15`.
- `output.preferred_duration_seconds`: pacing target, default `18`.
- `output.duration_seconds`: final maximum retained for backward compatibility, default `20`.
- `output.width` / `output.height`: preferred export target `1080×1920`.
- `output.minimum_width` / `output.minimum_height`: hard acceptance floor `720×1280` at 9:16.
- `output.safe_zone`: default `meta-reels` overlay protection: top `250`, bottom `340`, left `90`, right `180`, caption top `270`, maximum `20` visible characters per line.

`catalog_json` is optional. When supplied, synthetic workflow generation is offline and reproducible. Without it, the workflow renderer reads the live Marketplace catalog with `makaron skills list --json`.

The final assembly order is fixed: distinct Hook video → comparison image → localized workflow video → effect/result video → bundled Logo CTA video. Hook and result are separate target-Skill generations and cannot reuse the same shot or frames. Voiceover defaults to a natural energetic young-adult female Seed Audio voice and must finish before the CTA excerpt. One BGM is generated separately with `makaron music create`, then passed with every visual asset to one project-bound `makaron chat` request using the built-in `tiktok-video` Remotion builder. The runtime derives Caption JSON and scene boundaries from measured narration timings, mutes all video source audio, loops that BGM through CTA, burns one Meta-safe subtitle set, and directly exports the MP4. There is no local final concat/amix/ASS/PIL stage.

Timing is adaptive within measured bounds: Hook 2.5–5 seconds, comparison about 2.5 seconds, workflow about 4 seconds, result at least 3 seconds, and final duration 15–20 seconds. See [reference-editing-rhythm.md](reference-editing-rhythm.md) when modifying those bounds.

Do not store API keys, tokens, passwords, or private URLs in campaign JSON.
