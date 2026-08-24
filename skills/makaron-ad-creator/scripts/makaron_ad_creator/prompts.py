from __future__ import annotations

import json
from typing import Any

from .schema import ad_locales


LOCALE_RULES = {
    "en": "Natural conversational US English. Keep every spoken line short and idiomatic.",
    "ja": "Natural conversational Japanese for Japan. Adapt the emotional register; do not translate literally.",
    "yue": "Natural spoken Hong Kong Cantonese in Traditional Chinese. Use native Hong Kong pronunciation, never a Mandarin reading, and prefer unambiguous colloquial Cantonese wording.",
}

LOCALE_NAMES = {"en": "English", "ja": "Japanese", "yue": "Hong Kong Cantonese"}
SCRIPT_ANCHORS = {
    "en": ["...", "...", "Open Makaron.", "Use the template.", "..."],
    "ja": ["...", "...", "Makaronを開いて。", "テンプレートを使って。", "..."],
    "yue": ["...", "...", "打開 Makaron。", "揀呢個效果。", "..."],
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
Use exactly these beats: 1 surprising hook; 2 say it started from one ordinary photo; 3 Open Makaron; 4 Use the template; 5 emotional result.
Apply these locale rules:
{locale_rules}
Line 1 must be a genuine curiosity or surprising-result Hook, must not say or repeat the exact Skill name, and must fit under 1.8 seconds when spoken. Keep line 2 under 2.3 seconds when spoken. Do not invent features, prices, ratings, urgency, or claims. Return only the selected locale keys and no others.
Return this exact shape: {json.dumps(exact_shape, ensure_ascii=False)}"""


def before_prompt(config: dict[str, Any]) -> str:
    return f"""Use the attached owned input image as the identity and geometry source.
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
    return f"""Run the currently active Makaron Marketplace Skill exactly as written against the attached owned input image.
ACTIVE TARGET SKILL: {skill['name']} ({skill['id']})
SUPPORTED TRANSFORMATION: {skill['core']}
The active Skill's own SKILL.md is the creative source of truth. Execute its native workflow, fill and use its locked video prompt template, honor its scene defaults, signature visuals, action rules, negative constraints, duration guidance, and QC. Do not replace, summarize, rewrite, or override that template with a generic ad-effect concept.
Use the attached image only as the primary identity/reference input. Do not add a source-photo studio introduction, before-state build-up, app UI, tutorial, comparison, or separate advertising scene. Begin directly in the active Skill's native visual world and deliver one uninterrupted native Skill result video. The CLI will later derive non-overlapping Hook and Result ranges from this same source without changing the Skill output.
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


def comparison_prompt(config: dict[str, Any]) -> str:
    return f"""Create one exact vertical Before/After comparison image inside this bound Makaron project.
ATTACHED ROLES: image 1 is the ordinary Before; image 2 is the exact keyframe extracted from the {config['target_skill']['name']} effect video.
Use both attached images as locked source pixels. Do not redraw, regenerate, retouch, relight, restyle, change identity, or invent missing content.
Compose a 1080x1920 black canvas with two equal side-by-side contain-fit panels and a narrow 10px center gap. Preserve every source pixel: keep the complete face, body/product silhouette, and key effect visible; never crop, zoom past an edge, or use cover-fit. Center each source inside its panel and use black letterbox/pillarbox space when its aspect ratio differs. Put BEFORE under the left panel and AFTER under the right panel in bold white text with a black outline. Keep all key content inside the Meta safe center and do not add any other title, logo, watermark, decoration, or claim.
Return one newly exported PNG only."""


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
    voiceover_volume = float(config["audio"].get("tts_volume_by_locale", {}).get(locale, 1.0))
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
Generate one continuous Seed Audio voiceover and read exactly those five lines, once, in order, using this target-locale voice profile: {tts_voice}. Do not read Skill descriptions, UI text, filenames, or production instructions. Complete every line before the Logo CTA begins; the CTA has no voiceover. The final spoken word must not be truncated.
VOICEOVER MIX LEVEL: serialize props.voiceoverVolume={voiceover_volume:.2f} and apply that gain to the voiceover track only. Keep the BGM at its separately specified level; never use this gain on BGM or source video audio.
If measured narration still exceeds its assigned scene, automatically shorten that line while preserving its meaning, regenerate the matching voice and subtitle text, and continue to export. Never extend, loop, freeze, or slow a source clip to fit narration, and never pause to ask the user a timing question.
ATTACHED ASSET ROLES: image 1 is the simultaneous Before/After comparison; video 1 is the opening Hook segment extracted from the target-Skill effect source; video 2 is the later non-overlapping Result segment from that exact same effect source; video 3 is the locale-correct v5 Makaron workflow; video 4 is the fixed Makaron Logo CTA source; audio 1 is the separately generated instrumental BGM.
ASSET BINDING: this persistent project may contain media from older campaigns. The Remotion props must use the exact current attachments with these keys: comparisonImage=image 1 URL, hookVideo=video 1 URL, resultVideo=video 2 URL, workflowVideo=video 3 URL, ctaVideo=video 4 URL, bgmUrl=audio 1 URL. Never select an older project image, video, voice, or music asset by recency, filename, or visual similarity. Set the Remotion Composition itself to width={output['width']}, height={output['height']}, fps=30; never infer the composition size from the first attached video.
LOCKED FINAL ORDER: Hook video; comparison image; localized workflow video; effect/result video; fixed Logo CTA video. Use the full duration of attached video 1 for Hook (normally 2.5s, shorter only when the source effect was too short); comparison exactly 2.5s; workflow 3.5-4.5s; effect/result at least 3.0s; Logo CTA exactly {cta_seconds:.1f}s using the source from {float(config['assets']['logo_cta_start_seconds']):.1f}s. Extend the result segment only long enough to show one complete payoff without repetition.
Use video 1 only for Hook and video 2 only for Result. They are exact, non-overlapping time ranges from one target-Skill effect source. Never reuse, loop, reverse, freeze, or speed-ramp source frames across those two sections, and never request or invent a separately generated Hook.
Mute the original audio from every attached video, including the Hook, effect video, workflow video, and Logo CTA. Loop audio 1 as the same continuous BGM from 0.0 seconds through the final frame, including throughout the Logo CTA, at relative mix volume {bgm_volume:.2f} under the voiceover. Do not switch tracks, restart with different music, use CTA source audio, add sound effects, or allow a silent tail. Apply a gentle music fade only at the very end of the complete ad.
REMOTION TIMING CONTRACT: create the Seed Audio narration first, obtain real word/line timings, and represent the five lines as Caption JSON objects with text, startMs, endMs, timestampMs, and confidence. Derive scene boundaries from those measured timings; never guess subtitle frames independently from the audio. Line 1 must start and end inside Hook, line 2 entirely inside comparison, lines 3 and 4 entirely inside workflow, and line 5 entirely inside effect/result. No voice or subtitle may cross a scene boundary or enter CTA. Keep each caption start/end within 150ms of its spoken audio. Return the timing manifest with scene startMs/endMs and every caption's assigned scene in the QC summary.
If the runtime returns an editable Remotion design, its props must include compositionContractVersion: 2, captions: Caption[], scenes either as an object keyed by hook/comparison/workflow/result/cta or as an array of {{id,startMs,endMs}} objects, lineSceneMap: ["hook", "comparison", "workflow", "workflow", "result"], and safeZone with the exact Meta inset values below. Regardless of representation, set result.startMs no later than caption 5 startMs so line 5 never begins over workflow.
META SAFE ZONE: treat the insets as canvas-relative ratios, not fixed 1080p pixel coordinates. On the required {output['width']}x{output['height']} composition they resolve to x={safe['left_px']}..{output['width'] - safe['right_px']} and y={safe['top_px']}..{output['height'] - safe['bottom_px']}. Set the subtitle container's CSS top to exactly y={safe['caption_top_px']}; do not add an extra top offset, padding, Math.max(... + offset), or vertical centering. If any runtime preview uses another 9:16 size, recompute every pixel inset from the ratios before layout so captions and faces never drift or clip. The Meta profile overrides the older 140px top-caption convention because 140px lies under account UI.
Serialize props.safeZone with topRatio={safe_ratios['top']:.6f}, bottomRatio={safe_ratios['bottom']:.6f}, leftRatio={safe_ratios['left']:.6f}, rightRatio={safe_ratios['right']:.6f}, captionTopRatio={safe_ratios['caption_top']:.6f}, plus topPx/bottomPx/leftPx/rightPx/captionTopPx dynamically calculated from the actual composition dimensions, and maxCharactersPerLine={safe['max_characters_per_line']}.
Burn exactly one synchronized subtitle set for every spoken line: white text with black stroke/outline, no black box or background bar, horizontally centered inside the full safe content width with textAlign:'center' and centered flex alignment, never left-aligned or shifted toward either rail. Prefer one physical line for every caption. Use whiteSpace:'nowrap' and choose a responsive font size in the 42-56px range so any line of at most {safe['max_characters_per_line']} visible characters fits between the left and right safe insets. Only wrap to a maximum of two lines when a longer localized line still cannot fit legibly at 42px. Caption text/display must not contain literal backslash-n or hard-coded newline characters. English subtitles are uppercase; Japanese and Cantonese retain natural case. Do not add duplicate subtitles, title-card captions, or overlapping text layers. Measure text width before rendering and reduce font size before considering a wrap.
Return a {final_min:.1f}-{final_max:.1f} second five-part final video, aiming for {final_preferred:.1f} seconds but choosing the shortest duration that keeps the mechanism and spoken lines clear. Build, time-align, subtitle, mix, and export the complete video through Remotion inside this one chat run; do not ask the CLI to perform local FFmpeg concat, amix, ASS subtitle rendering, edge-tts, or PIL final composition. Publishing an editable draft, design, snapshot, contact sheet, source file, or QC note is not completion. The response must contain a newly exported final MP4 in its generated video outputs/result.videos. If materialization reports a stale timeline pointer or Forbidden error, repair the published snapshot/design path and retry export inside this run; never return one of the attached source videos as the final result.
SUPPORTED OFFER: {offer['value_proposition']}
Do not invent prices, ratings, endorsements, urgency, or capabilities. No black frames. Target {output['width']}x{output['height']}, minimum {output['minimum_width']}x{output['minimum_height']}, 9:16, 30fps, H.264/AAC, within {final_min:.1f}-{final_max:.1f} seconds.
Return the final MP4 and a concise QC summary."""
