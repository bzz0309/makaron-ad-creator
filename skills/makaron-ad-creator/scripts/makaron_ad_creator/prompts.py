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


def final_prompt(config: dict[str, Any], locale: str, scripts: dict[str, list[str]], model_preference: str = "seedance-fast") -> str:
    output = config["output"]
    offer = config["offer"]
    lines = scripts[locale]
    tts_voice = config["audio"]["tts_voice"]
    cta_seconds = float(config["assets"]["logo_cta_excerpt_seconds"])
    body_min = float(output["minimum_duration_seconds"]) - cta_seconds
    body_preferred = float(output["preferred_duration_seconds"]) - cta_seconds
    body_max = float(output["duration_seconds"]) - cta_seconds
    return f"""Create one finished vertical social ad from the attached owned/licensed assets.
TARGET LOCALE: {locale}
MODEL ROUTING PREFERENCE FOR THIS ATTEMPT: {model_preference}
LOCALIZATION RULE: {LOCALE_RULES[locale]}
VOICEOVER SCRIPT: {json.dumps(lines, ensure_ascii=False)}
Read exactly those five lines, once, in order, using this target-locale TTS voice profile: {tts_voice}. Do not read UI text or production instructions. Finish voiceover and subtitles by the end of this body video.
ATTACHED ASSET ROLES: image 1 is the simultaneous Before/After comparison; video 1 is the target-Skill effect/result; video 2 is the locale-correct Makaron workflow.
LOCKED BODY ORDER: Hook video; comparison image; localized workflow video; effect/result video. Use adaptive timing within these bounds: Hook 2.5-5.0s; comparison exactly 2.5s; workflow 3.5-4.5s; effect/result at least 3.0s. Use the 5-second Hook only when the Skill's physical action or transformation mechanism would be unclear in 2.5 seconds; otherwise keep the Hook at 2.5 seconds. Extend the result segment only long enough to show one complete payoff without repetition.
Return a {body_min:.1f}-{body_max:.1f} second four-part body, aiming for {body_preferred:.1f} seconds but choosing the shortest duration that keeps the mechanism and spoken lines clear. Do not generate a Logo CTA, end card, extra title card, or black tail; the CLI appends the fixed {cta_seconds:.1f}-second Logo CTA locally as the fifth part.
Mute source audio from videos 1 and 2. Add licensed or newly generated light upbeat instrumental BGM at least 8dB below voiceover, with a clean ending at the body endpoint. Burn one subtitle set timed to every spoken line: white text, black outline, no background bar, upper safe area, maximum two lines. English subtitles are uppercase; Japanese and Cantonese retain natural case. The final spoken word must not be truncated.
SUPPORTED OFFER: {offer['value_proposition']}
Do not invent prices, ratings, endorsements, urgency, or capabilities. No black frames. Exact {output['width']}x{output['height']}, 30fps, H.264/AAC, within {body_min:.1f}-{body_max:.1f} seconds.
Return the body MP4 and a concise QC summary."""
