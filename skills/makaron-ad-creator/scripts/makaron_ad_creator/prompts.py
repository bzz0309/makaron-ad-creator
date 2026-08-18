from __future__ import annotations

import json
from typing import Any


LOCALE_RULES = {
    "en": "Natural conversational US English. Keep every spoken line short and idiomatic.",
    "ja": "Natural conversational Japanese for Japan. Adapt the emotional register; do not translate literally.",
    "yue": "Natural spoken Hong Kong Cantonese in Traditional Chinese. Avoid Mandarin-only phrasing.",
}


def script_prompt(config: dict[str, Any]) -> str:
    skill = config["target_skill"]
    return f"""Return ONLY valid JSON for a five-line ad voiceover in English, Japanese, and Cantonese.
TARGET SKILL NAME: {skill['name']}
TARGET SKILL CORE: {skill['core']}
TRANSFORMATION TYPE: {skill.get('transformation_type', 'identity')}
Use exactly these beats: 1 surprising hook; 2 say it started from one ordinary photo; 3 Open Makaron; 4 Use the template; 5 emotional result.
The English, Japanese, and Cantonese must be culturally natural, not literal translations. Keep line 2 under 2.3 seconds when spoken. Do not invent features, prices, ratings, urgency, or claims.
Return this exact shape: {{"en":["...","...","Open Makaron.","Use the template.","..."],"ja":["...","...","Makaronを開いて。","テンプレートを使って。","..."],"yue":["...","...","打開 Makaron。","使用模版。","..."]}}"""


def before_prompt(config: dict[str, Any]) -> str:
    return f"""Use the attached owned input image as the identity and geometry source.
Create one realistic, ordinary starting-state vertical phone photo for an advertising comparison.
SUBJECT: {config['subject_description']}
Keep the same person or product recognizable and factual. Use neutral presentation, everyday setting, natural unpolished phone-camera lighting, and no glamour styling. Do not humiliate, body-shame, add defects, change age, skin tone, facial structure, body proportions, product geometry, label, or capabilities. No text, logo, watermark, celebrity likeness, or private information. Exact aspect ratio 9:16.
Return one image only."""


def effect_prompt(config: dict[str, Any], model_preference: str = "seedance-fast") -> str:
    constraints = "; ".join(config.get("style_constraints", [])) or "preserve identity and product facts"
    return f"""Use the attached owned input image with the selected Makaron Skill.
Create one 5-second vertical result video that demonstrates only this supported transformation: {config['target_skill']['core']}.
MODEL ROUTING PREFERENCE FOR THIS ATTEMPT: {model_preference}
STYLE CONSTRAINTS: {constraints}
Preserve identity, age, skin tone, facial structure, body proportions, product geometry, labels, and factual capabilities. Use one readable action and restrained camera motion. No text, logo, UI, watermark, fake endorsement, unsupported claim, morphing, or extra objects. Exact aspect ratio 9:16. No source audio.
Return one MP4 only."""


def final_prompt(config: dict[str, Any], locale: str, scripts: dict[str, list[str]], model_preference: str = "seedance-fast") -> str:
    output = config["output"]
    offer = config["offer"]
    lines = scripts[locale]
    return f"""Create one finished vertical social ad from the attached owned/licensed assets.
TARGET LOCALE: {locale}
MODEL ROUTING PREFERENCE FOR THIS ATTEMPT: {model_preference}
LOCALIZATION RULE: {LOCALE_RULES[locale]}
VOICEOVER SCRIPT: {json.dumps(lines, ensure_ascii=False)}
Read exactly those five lines, once, in order, using an energetic natural young-adult voice in the target locale. Do not read UI text or production instructions.
TIMELINE: 0-2.5s strongest result hook; 2.5-5.0s simultaneous Before/After comparison; 5.0-9.0s localized Makaron workflow demo; 9.0-15.0s full result; 15.0-{output['duration_seconds']:.1f}s CTA.
Mute all attached source audio. Add licensed or newly generated light upbeat instrumental BGM, at least 8dB below voiceover, with no early fade. Burn one subtitle set timed to every spoken line: white text, black outline, no background bar, upper safe area, maximum two lines. English subtitles are uppercase; Japanese and Cantonese retain natural case. The final word must not be truncated.
SUPPORTED OFFER: {offer['value_proposition']}
CTA: {offer['cta']}
DESTINATION: {offer.get('destination_url', '')}
Do not invent prices, ratings, endorsements, urgency, or capabilities. No black frames. Exact {output['width']}x{output['height']}, 30fps, H.264/AAC, maximum {output['duration_seconds']:.1f} seconds.
Return the finished MP4 and a concise QC summary."""
