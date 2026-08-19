from __future__ import annotations

import json
from typing import Any

from .schema import ad_locales


LOCALE_RULES = {
    "en": "Natural conversational US English. Keep every spoken line short and idiomatic.",
    "ja": "Natural conversational Japanese for Japan. Adapt the emotional register; do not translate literally.",
    "yue": "Natural spoken Hong Kong Cantonese in Traditional Chinese. Avoid Mandarin-only phrasing.",
}

LOCALE_NAMES = {"en": "English", "ja": "Japanese", "yue": "Hong Kong Cantonese"}
SCRIPT_ANCHORS = {
    "en": ["...", "...", "Open Makaron.", "Use the template.", "..."],
    "ja": ["...", "...", "Makaronを開いて。", "テンプレートを使って。", "..."],
    "yue": ["...", "...", "打開 Makaron。", "使用模版。", "..."],
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
Keep line 2 under 2.3 seconds when spoken. Do not invent features, prices, ratings, urgency, or claims. Return only the selected locale keys and no others.
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


def effect_prompt(config: dict[str, Any], model_preference: str = "seedance-fast") -> str:
    constraints = "; ".join(config.get("style_constraints", [])) or "preserve identity and product facts"
    return f"""Use the attached owned input image with the selected Makaron Skill.
Create one 5-second vertical result video that demonstrates only this supported transformation: {config['target_skill']['core']}.
MODEL ROUTING PREFERENCE FOR THIS ATTEMPT: {model_preference}
STYLE CONSTRAINTS: {constraints}
For an authorized, clearly adult fashion subject only, and only when compatible with the source image and target Skill, use elegant glamorous styling such as an open neckline or exposed shoulders and a coordinated midriff silhouette; a fuller shot may show the legs. Keep it non-explicit and non-vulgar. Never apply this direction to minors, age-ambiguous people, products, nonhuman subjects, or unrelated transformations.
Preserve identity, age, skin tone, facial structure, body proportions, product geometry, labels, and factual capabilities. Use one readable action and restrained camera motion. No text, logo, UI, watermark, fake endorsement, unsupported claim, morphing, or extra objects. Exact aspect ratio 9:16. No source audio.
Return one MP4 only."""


def bgm_prompt(config: dict[str, Any]) -> str:
    audio = config["audio"]
    return f"""Create one original instrumental background-music track for this vertical social ad.
TARGET SKILL NAME: {config['target_skill']['name']}
TARGET SKILL CORE: {config['target_skill']['core']}
MUSIC DIRECTION: {audio['bgm_prompt']}
The track must be at least 20 seconds and instrumental only: no vocals, speech, chants, recognizable copyrighted melody, or abrupt ending. Start with an immediate hook, maintain useful edit rhythm, stay at full musical energy through the required duration with no early fade-out, and remain loop-friendly for a 15-20 second ad. Return one audio track only."""


def final_prompt(config: dict[str, Any], locale: str, scripts: dict[str, list[str]], model_preference: str = "seedance-fast") -> str:
    output = config["output"]
    offer = config["offer"]
    lines = scripts[locale]
    tts_voice = config["audio"]["tts_voice"]
    cta_seconds = float(config["assets"]["logo_cta_excerpt_seconds"])
    final_min = float(output["minimum_duration_seconds"])
    final_preferred = float(output["preferred_duration_seconds"])
    final_max = float(output["duration_seconds"])
    bgm_volume = float(config["audio"]["bgm_volume"])
    return f"""Use the Makaron Agent's internal Remotion workflow to create and export one finished vertical social ad from the attached owned/licensed assets in this single project-bound chat run.
TARGET LOCALE: {locale}
MODEL ROUTING PREFERENCE FOR THIS ATTEMPT: {model_preference}
LOCALIZATION RULE: {LOCALE_RULES[locale]}
VOICEOVER SCRIPT: {json.dumps(lines, ensure_ascii=False)}
Generate one continuous Seed Audio voiceover and read exactly those five lines, once, in order, using this target-locale voice profile: {tts_voice}. Do not read Skill descriptions, UI text, filenames, or production instructions. Complete every line before the Logo CTA begins; the CTA has no voiceover. The final spoken word must not be truncated.
ATTACHED ASSET ROLES: image 1 is the simultaneous Before/After comparison; video 1 is the target-Skill effect/result; video 2 is the locale-correct Makaron workflow; video 3 is the fixed Makaron Logo CTA source; audio 1 is the separately generated instrumental BGM.
LOCKED FINAL ORDER: Hook video; comparison image; localized workflow video; effect/result video; fixed Logo CTA video. Use adaptive timing within these bounds: Hook 2.5-5.0s; comparison exactly 2.5s; workflow 3.5-4.5s; effect/result at least 3.0s; Logo CTA exactly {cta_seconds:.1f}s using the source from {float(config['assets']['logo_cta_start_seconds']):.1f}s. Use the 5-second Hook only when the Skill's physical action or transformation mechanism would be unclear in 2.5 seconds; otherwise keep the Hook at 2.5 seconds. Extend the result segment only long enough to show one complete payoff without repetition.
Mute the original audio from every attached video, including the effect video, workflow video, and Logo CTA. Loop audio 1 as the same continuous BGM from 0.0 seconds through the final frame, including throughout the Logo CTA, at relative mix volume {bgm_volume:.2f} under the voiceover. Do not switch tracks, restart with different music, use CTA source audio, add sound effects, or allow a silent tail. Apply a gentle music fade only at the very end of the complete ad.
Burn exactly one synchronized subtitle set for every spoken line: top-aligned 140px from the top, white text with black stroke/outline, no background bar, maximum two lines. English subtitles are uppercase; Japanese and Cantonese retain natural case. Do not add duplicate title-card subtitles.
Return a {final_min:.1f}-{final_max:.1f} second five-part final video, aiming for {final_preferred:.1f} seconds but choosing the shortest duration that keeps the mechanism and spoken lines clear. Build, time-align, subtitle, mix, and export the complete video through Remotion inside this one chat run; do not ask the CLI to perform local FFmpeg concat, amix, ASS subtitle rendering, edge-tts, or PIL final composition.
SUPPORTED OFFER: {offer['value_proposition']}
Do not invent prices, ratings, endorsements, urgency, or capabilities. No black frames. Exact {output['width']}x{output['height']}, 30fps, H.264/AAC, within {final_min:.1f}-{final_max:.1f} seconds.
Return the final MP4 and a concise QC summary."""
