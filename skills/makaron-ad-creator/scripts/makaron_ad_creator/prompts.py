from __future__ import annotations

import json
from typing import Any

from .schema import ad_locales


LOCALE_RULES = {
    "en": "Natural conversational US English in the user's first-person I/my voice. Keep every spoken line short and idiomatic.",
    "ja": "Natural conversational Japanese for Japan as a first-person personal experience. Establish the speaker once with 私, わたし, 僕, ぼく, うち, or 自分; then omit the pronoun when natural. Adapt the emotional register; do not translate literally.",
    "yue": "Natural spoken Hong Kong Cantonese in Traditional Chinese in the user's first-person 我/我嘅 voice. Use native Hong Kong pronunciation, never a Mandarin reading, and prefer unambiguous colloquial Cantonese wording.",
}

LOCALE_NAMES = {"en": "English", "ja": "Japanese", "yue": "Hong Kong Cantonese"}
LOCKED_ACTION_LINES = {
    # These are short action statements within a first-person testimonial, not
    # calls to action aimed at the viewer.  Keep their meaning stable so the
    # localized v5 workflow always matches the spoken steps.
    "en": ("Open Makaron.", "Use the template."),
    "ja": ("Makaronを開いた。", "テンプレートを選んだ。"),
    "yue": ("我打開 Makaron。", "我揀咗個模板。"),
}
SCRIPT_ANCHORS = {
    locale: ["...", "...", *LOCKED_ACTION_LINES[locale], "..."]
    for locale in LOCALE_NAMES
}


def script_prompt(config: dict[str, Any]) -> str:
    skill = config["target_skill"]
    selected = ad_locales(config)
    locale_names = ", ".join(LOCALE_NAMES[locale] for locale in selected)
    exact_shape = {locale: SCRIPT_ANCHORS[locale] for locale in selected}
    locale_rules = "\n".join(f"- {locale}: {LOCALE_RULES[locale]}" for locale in selected)
    return f"""Return ONLY valid JSON for a five-line ad voiceover in these target locales: {locale_names}.
TARGET SKILL NAME: {skill['name']}
TARGET SKILL CORE: {skill['core']}
TRANSFORMATION TYPE: {skill.get('transformation_type', 'identity')}
Use exactly these beats: 1 surprising hook; 2 say it started from one ordinary photo; 3 open Makaron; 4 choose a template; 5 emotional result.
Write the complete script as one personal first-person testimonial from the user or creator who supplied the photo. The speaker describes their own input, actions, and result; never switch to a detached narrator or call the depicted subject he, she, they, her, him, 佢, 彼, or 彼女. Lines 3 and 4 describe actions the speaker took, not commands addressed to the viewer. English uses I/my naturally; Cantonese uses 我/我嘅 naturally; Japanese must establish an explicit first-person speaker at least once and may then omit the pronoun where natural. Do not mechanically repeat the pronoun when the language normally drops it.
Apply these locale rules:
{locale_rules}
Lines 3 and 4 are locked literal action lines. Do not paraphrase, conjugate, reorder, or replace them: {json.dumps({locale: list(LOCKED_ACTION_LINES[locale]) for locale in selected}, ensure_ascii=False)}
Line 1 must be a genuine curiosity or surprising-result Hook, must not say or repeat the exact Skill name, and must fit under 1.8 seconds when spoken. Keep line 2 under 2.3 seconds when spoken. Do not invent features, prices, ratings, urgency, or claims. Return only the selected locale keys and no others, with five strings per locale in this structural order: {json.dumps(exact_shape, ensure_ascii=False)}"""


def before_prompt(config: dict[str, Any]) -> str:
    return f"""Use the existing bound-project image 1 (<<<media_1>>>) as the owned identity and geometry source. It is the exact input image uploaded when this isolated project was created; do not ask for or upload another copy.
Create one realistic, ordinary, unpolished starting-state vertical phone photo for an advertising comparison.
SUBJECT: {config['subject_description']}
Keep the overall scene naturally bright and normally exposed: not dark, underexposed, grey, or low-key graded.
For an authorized adult person, preserve the source skin tone and undertone exactly while showing realistic unretouched detail: natural pores around the nose and inner cheeks, mild unevenness, subtle redness only where plausible, a small amount of ordinary post-blemish texture, soft under-eye tiredness, dehydrated microtexture, and very low oil shine. Do not invent severe acne, scars, injury, disease, or a different complexion. Use no visible makeup or glamour retouching. Hair may look plainly unstyled with flat roots, loose strands, and mild bed-hair, but not filthy or degrading. Keep brows natural, lips unpolished, remove non-identity-critical eyewear or jewelry only when doing so does not change recognition, use a plain faded wrinkled t-shirt or oversized hoodie, a tired unposed expression, and an ordinary lived-in bedroom or bathroom corner. Use a close handheld front-camera selfie with slightly awkward everyday framing.
For a product, fictional nonhuman character, landscape, food, or other nonperson, do not apply human skin, hair, clothing, or fatigue instructions; instead create a truthful ordinary starting presentation with natural phone-camera lighting and no premium styling.
Keep the same person or product recognizable and factual. Do not humiliate, body-shame, add defects, change age, skin tone, facial structure, body proportions, product geometry, label, or capabilities. No text, logo, watermark, celebrity likeness, or private information. Exact aspect ratio 9:16.
Return one image only."""


def effect_prompt(config: dict[str, Any], model_preference: str = "seedance-2-0") -> str:
    constraints = "; ".join(config.get("style_constraints", [])) or "preserve identity and product facts"
    skill = config["target_skill"]
    return f"""Run the currently active Makaron Marketplace Skill exactly as written against the existing bound-project image 1 (<<<media_1>>>). It is the exact owned input uploaded when this isolated project was created; do not ask for or upload another copy.
ACTIVE TARGET SKILL: {skill['name']} ({skill['id']})
SUPPORTED TRANSFORMATION: {skill['core']}
The active Skill's own SKILL.md is the creative source of truth. Execute its native workflow, fill and use its locked video prompt template, honor its scene defaults, signature visuals, action rules, negative constraints, duration guidance, and QC. Do not replace, summarize, rewrite, or override that template with a generic ad-effect concept.
Use <<<media_1>>> only as the primary identity/reference input. Do not add a source-photo studio introduction, before-state build-up, app UI, tutorial, comparison, or separate advertising scene. Begin directly in the active Skill's native visual world and deliver one uninterrupted native Skill result video. The CLI will later derive non-overlapping Hook and Result ranges from this same source without changing the Skill output.
USER MODEL OVERRIDE FOR THIS ATTEMPT: {model_preference}. This model choice may override only the active Skill's default model routing; it must not alter the Skill's creative template. Use a fallback only on a later failed-node attempt.
ADDITIONAL COMPATIBLE CONSTRAINTS: {constraints}. Apply these only when they do not conflict with the active Skill. When any wrapper constraint conflicts with the active Skill, the active Skill wins.
Preserve identity, age, skin tone, facial structure, body proportions, product geometry, labels, and factual capabilities. No added text, logo, UI, watermark, fake endorsement, or unsupported claim. Exact aspect ratio 9:16; target 1080x1920 and never below 720x1280. No source audio.
Return one MP4 only."""


def after_prompt(config: dict[str, Any]) -> str:
    return f"""Use attached video 1 as the exact target-Skill effect source for {config['target_skill']['name']}.
Analyze the complete video, not only its final seconds. Select the single strongest truthful keyframe that most clearly shows the completed supported effect: {config['target_skill']['core']}.
Evaluate stable candidate frames across the whole clip. Reject transition, motion-blurred, black, obstructed, malformed, identity-drifted, incomplete-effect, text, UI, and watermark frames. Prefer the clearest complete payoff, stable face/body or product geometry, readable action, strong composition, and maximum contrast with an ordinary Before image.
Export the exact decoded source-video frame at the chosen timestamp. Do not redraw, regenerate, beautify, retouch, extend, replace, or reinterpret any pixel. Preserve the source frame's identity and effect exactly. Record the selected timestamp and concise selection reason in response metadata, but return one PNG image as the generated media output.
Target 1080x1920; minimum 720x1280; exact 9:16."""


def bgm_prompt(config: dict[str, Any]) -> str:
    audio = config["audio"]
    return f"""Create one original instrumental background-music track for this vertical social ad.
TARGET SKILL NAME: {config['target_skill']['name']}
TARGET SKILL CORE: {config['target_skill']['core']}
MUSIC DIRECTION: {audio['bgm_prompt']}
The track must be at least 20 seconds and instrumental only: no vocals, speech, chants, recognizable copyrighted melody, or abrupt ending. Start with an immediate hook, maintain useful edit rhythm, stay at full musical energy through the required duration with no early fade-out, and remain loop-friendly for a 15-20 second ad. Return one audio track only."""


def final_prompt(config: dict[str, Any], locale: str, scripts: dict[str, list[str]], model_preference: str = "seedance-2-0") -> str:
    output = config["output"]
    offer = config["offer"]
    lines = scripts[locale]
    tts_voice = config["audio"]["tts_voice"]
    cta_seconds = float(config["assets"]["logo_cta_excerpt_seconds"])
    final_min = float(output["minimum_duration_seconds"])
    final_preferred = float(output["preferred_duration_seconds"])
    final_max = float(output["duration_seconds"])
    bgm_volume = float(config["audio"]["bgm_volume"])
    voiceover_volume = float(config["audio"].get("tts_volume_by_locale", {}).get(locale, 1.35))
    ducking = config["audio"]["bgm_ducking"]
    ducked_bgm_volume = float(ducking["ducked_volume"])
    duck_attack_ms = int(ducking["attack_ms"])
    duck_release_ms = int(ducking["release_ms"])
    configured_segments = config.get("effect_segments", {})
    if configured_segments:
        hook_segment = configured_segments["hook"]
        result_segment = configured_segments["result"]
        hook_seconds = (
            float(hook_segment["end_seconds"]) - float(hook_segment["start_seconds"])
        ) / float(hook_segment.get("playback_speed", 1.0))
        result_seconds = (
            float(result_segment["end_seconds"]) - float(result_segment["start_seconds"])
        ) / float(result_segment.get("playback_speed", 1.0))
        effect_scene_rule = (
            f"Use the entire attached video 1 for Hook for exactly {hook_seconds:.3f}s and the entire attached "
            f"video 2 for Result for exactly {result_seconds:.3f}s. These user-selected durations override the "
            "builder's default 2.5-second Hook and any cached scene template."
        )
    else:
        effect_scene_rule = (
            "Use the full duration of attached video 1 for Hook (normally 2.5s, shorter only when the source "
            "effect was too short), and use the shortest complete 3-7 second payoff from attached video 2."
        )
    safe = output["safe_zone"]
    safe_ratios = {
        "top": float(safe["top_ratio"]),
        "bottom": float(safe["bottom_ratio"]),
        "left": float(safe["left_ratio"]),
        "right": float(safe["right_ratio"]),
        "caption_top": float(safe["caption_top_ratio"]),
    }
    return f"""Use the Makaron Agent's internal Remotion workflow to create and export one finished vertical social ad from the attached owned/licensed assets in this single project-bound chat run.
TARGET LOCALE: {locale}
MODEL ROUTING PREFERENCE FOR THIS ATTEMPT: {model_preference}
LOCALIZATION RULE: {LOCALE_RULES[locale]}
VOICEOVER SCRIPT: {json.dumps(lines, ensure_ascii=False)}
Generate one continuous Seed Audio voiceover and read exactly those five lines, once, in order, using this target-locale voice profile: {tts_voice}. Serialize the generated narration asset as props.voiceoverUrl and consume that prop in the Remotion Composition. Do not read Skill descriptions, UI text, filenames, or production instructions. Complete every line before the Logo CTA begins; the CTA has no voiceover. The final spoken word must not be truncated.
VOICEOVER MIX LEVEL: serialize props.voiceoverVolume={voiceover_volume:.2f} and apply that gain to the voiceover track only. This is foreground narration and must remain clearly intelligible over music for every word. Never use this gain on BGM or source video audio.
If measured narration still exceeds its assigned scene, automatically shorten that line while preserving its meaning, regenerate the matching voice and subtitle text, and continue to export. Never extend, loop, freeze, or slow a source clip to fit narration, and never pause to ask the user a timing question.
ATTACHED ASSET ROLES: image 1 is the simultaneous Before/After comparison; video 1 is the opening Hook segment extracted from the target-Skill effect source; video 2 is the later non-overlapping Result segment from that exact same effect source; video 3 is the locale-correct v5 Makaron workflow; video 4 is the fixed Makaron Logo CTA source; audio 1 is the separately generated instrumental BGM.
ASSET BINDING: this persistent project may contain media from older campaigns. The Remotion props must use the exact current attachments with these keys: comparisonImage=image 1 URL, hookVideo=video 1 URL, resultVideo=video 2 URL, workflowVideo=video 3 URL, ctaVideo=video 4 URL, bgmUrl=audio 1 URL. Never select an older project image, video, voice, or music asset by recency, filename, or visual similarity. Set the Remotion Composition itself to width={output['width']}, height={output['height']}, fps=30; never infer the composition size from the first attached video.
LOCKED FINAL ORDER: Hook video; comparison image; localized workflow video; effect/result video; fixed Logo CTA video. {effect_scene_rule} Comparison exactly 2.5s; workflow 3.5-4.5s; Logo CTA exactly {cta_seconds:.1f}s using the source from {float(config['assets']['logo_cta_start_seconds']):.1f}s.
Use video 1 only for Hook and video 2 only for Result. They are exact, non-overlapping time ranges from one target-Skill effect source. Never reuse, loop, reverse, freeze, or speed-ramp source frames across those two sections, and never request or invent a separately generated Hook.
Mute the original audio from every attached video, including the Hook, effect video, workflow video, and Logo CTA. Loop audio 1 as the same continuous BGM from 0.0 seconds through the final frame, including throughout the Logo CTA. Serialize props.bgmVolume={bgm_volume:.2f} and props.audioDucking={{enabled:true, duckedVolume:{ducked_bgm_volume:.2f}, attackMs:{duck_attack_ms}, releaseMs:{duck_release_ms}, trigger:"caption-timed-seed-audio"}}. Outside spoken Seed Audio intervals, keep BGM at {bgm_volume:.2f}; from {duck_attack_ms}ms before a measured voice/caption interval through {duck_release_ms}ms after it, sidechain-duck BGM to {ducked_bgm_volume:.2f}, then restore it smoothly. Do not switch tracks, restart with different music, use CTA source audio, add sound effects, or allow a silent tail. Apply a gentle music fade only at the very end of the complete ad.
REMOTION TIMING CONTRACT: create the Seed Audio narration first, obtain real word/line timings, and represent the five lines as Caption JSON objects with text, startMs, endMs, timestampMs, and confidence. Derive scene boundaries from those measured timings; never guess subtitle frames independently from the audio. Line 1 must start and end inside Hook, line 2 entirely inside comparison, lines 3 and 4 entirely inside workflow, and line 5 entirely inside effect/result. No voice or subtitle may cross a scene boundary or enter CTA. Keep each caption start/end within 150ms of its spoken audio. Return the timing manifest with scene startMs/endMs and every caption's assigned scene in the QC summary.
If the runtime returns an editable Remotion design, its props must include compositionContractVersion: 2, captions: Caption[], scenes either as an object keyed by hook/comparison/workflow/result/cta or as an array of {{id,startMs,endMs}} objects, lineSceneMap: ["hook", "comparison", "workflow", "workflow", "result"], and safeZone with the exact Meta inset values below. Regardless of representation, set result.startMs no later than caption 5 startMs so line 5 never begins over workflow.
META SAFE ZONE: treat the insets as canvas-relative ratios, not fixed 1080p pixel coordinates. On the required {output['width']}x{output['height']} composition they resolve to x={safe['left_px']}..{output['width'] - safe['right_px']} and y={safe['top_px']}..{output['height'] - safe['bottom_px']}. Set the subtitle container's CSS top to exactly y={safe['caption_top_px']}; do not add an extra top offset, padding, Math.max(... + offset), or vertical centering. If any runtime preview uses another 9:16 size, recompute every pixel inset from the ratios before layout so captions and faces never drift or clip. The Meta profile overrides the older 140px top-caption convention because 140px lies under account UI.
Serialize props.safeZone with topRatio={safe_ratios['top']:.6f}, bottomRatio={safe_ratios['bottom']:.6f}, leftRatio={safe_ratios['left']:.6f}, rightRatio={safe_ratios['right']:.6f}, captionTopRatio={safe_ratios['caption_top']:.6f}, plus topPx/bottomPx/leftPx/rightPx/captionTopPx dynamically calculated from the actual composition dimensions, and maxCharactersPerLine={safe['max_characters_per_line']}.
Burn exactly one synchronized subtitle set for every spoken line: white text with black stroke/outline, no black box or background bar, horizontally centered inside the full safe content width with textAlign:'center' and centered flex alignment, never left-aligned or shifted toward either rail. Prefer one physical line for every caption. First measure text width and responsively reduce font size within 42-56px so a line of at most {safe['max_characters_per_line']} visible characters fits between the safe insets. If a longer localized caption still requires two lines at 42px, use a measured balanced wrap at the word or phrase boundary closest to half of the rendered width. For English captions of six or more words, each wrapped line must contain at least three words; never leave an orphan line of only one or two words. For Japanese and Cantonese, keep the two rendered line widths visually balanced rather than leaving one very short fragment. Use CSS text-wrap:balance when supported and an equivalent measured split otherwise. Caption text values must not contain literal backslash-n or hard-coded newline characters; line layout belongs to the renderer. English subtitles are uppercase; Japanese and Cantonese retain natural case. Do not add duplicate subtitles, title-card captions, or overlapping text layers.
Return a {final_min:.1f}-{final_max:.1f} second five-part final video, aiming for {final_preferred:.1f} seconds but choosing the shortest duration that keeps the mechanism and spoken lines clear. Build, time-align, subtitle, mix, and export the complete video through Remotion inside this one chat run; do not ask the CLI to perform local FFmpeg concat, amix, ASS subtitle rendering, edge-tts, or PIL final composition. Publishing an editable draft, design, snapshot, contact sheet, source file, or QC note is not completion. The response must contain a newly exported final MP4 in its generated video outputs/result.videos. If materialization reports a stale timeline pointer or Forbidden error, repair the published snapshot/design path and retry export inside this run; never return one of the attached source videos as the final result.
SUPPORTED OFFER: {offer['value_proposition']}
Do not invent prices, ratings, endorsements, urgency, or capabilities. No black frames. Target {output['width']}x{output['height']}, minimum {output['minimum_width']}x{output['minimum_height']}, 9:16, 30fps, H.264/AAC, within {final_min:.1f}-{final_max:.1f} seconds.
Return the final MP4 and a concise QC summary."""
