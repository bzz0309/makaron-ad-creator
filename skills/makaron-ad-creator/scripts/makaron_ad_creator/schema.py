from __future__ import annotations

from pathlib import Path
from typing import Any

from .util import AdCreatorError, resolve_path


LOCALE_TO_UI = {"en": "en", "ja": "ja", "yue": "zh-Hant"}
DEFAULT_AD_LOCALES = ("en", "ja", "yue")
DEFAULT_LOGO_CTA = Path(__file__).resolve().parents[2] / "assets" / "makaron-logo-cta.mp4"
BUNDLED_LOGO_CTA_URI = "bundled://makaron-logo-cta.mp4"
DEFAULT_LOGO_CTA_EXCERPT_SECONDS = 3.0
DEFAULT_LOGO_CTA_START_SECONDS = 0.0
DEFAULT_LOCALES = [
    {"ad_locale": locale, "ui_locale": LOCALE_TO_UI[locale]}
    for locale in DEFAULT_AD_LOCALES
]


def locale_config(ad_locales: list[str] | tuple[str, ...] | None = None) -> list[dict[str, str]]:
    selected = list(ad_locales or DEFAULT_AD_LOCALES)
    if not selected:
        raise AdCreatorError("At least one locale is required")
    unknown = [locale for locale in selected if locale not in LOCALE_TO_UI]
    if unknown:
        raise AdCreatorError(f"Unsupported locale(s): {', '.join(unknown)}; choose en, ja, or yue")
    if len(selected) != len(set(selected)):
        raise AdCreatorError("Locales must not contain duplicates")
    return [{"ad_locale": locale, "ui_locale": LOCALE_TO_UI[locale]} for locale in selected]


def ad_locales(config: dict[str, Any]) -> list[str]:
    return [str(item["ad_locale"]) for item in config["locales"]]


def ui_locales(config: dict[str, Any]) -> list[str]:
    return [str(item["ui_locale"]) for item in config["locales"]]


def validate_config(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    required = ["campaign_id", "input_image", "target_skill", "project_binding", "rights", "offer", "output"]
    for key in required:
        if key not in config:
            errors.append(f"missing {key}")
    if errors:
        raise AdCreatorError("Invalid campaign config: " + ", ".join(errors))
    base = config_path.parent.resolve()
    image = resolve_path(base, config["input_image"])
    if not image.is_file():
        errors.append(f"input_image not found: {image}")
    config["input_image"] = str(image)
    skill = config.get("target_skill", {})
    for key in ("id", "name", "core"):
        if not str(skill.get(key, "")).strip():
            errors.append(f"target_skill.{key} is required")
    project = config.get("project_binding", {})
    if project.get("strategy") != "one_skill_one_persistent_project":
        errors.append("project_binding.strategy must be one_skill_one_persistent_project")
    if not project.get("project_id") or project.get("project_id") == "auto":
        errors.append("project_binding.project_id must be a persistent non-auto ID")
    if project.get("skill_id") != skill.get("id"):
        errors.append("project_binding.skill_id must equal target_skill.id")
    rights = config.get("rights", {})
    if rights.get("owned_or_licensed") is not True:
        errors.append("rights.owned_or_licensed must be true")
    if rights.get("claims_substantiated") is not True:
        errors.append("rights.claims_substantiated must be true")
    if rights.get("adult_or_nonperson") is not True:
        errors.append("rights.adult_or_nonperson must be true")
    locales = config.setdefault("locales", locale_config())
    if not isinstance(locales, list) or not locales:
        errors.append("locales must contain at least one locale mapping")
    else:
        seen: set[str] = set()
        for item in locales:
            if not isinstance(item, dict):
                errors.append("each locales item must be an object")
                continue
            ad_locale = item.get("ad_locale")
            ui_locale = item.get("ui_locale")
            if ad_locale not in LOCALE_TO_UI:
                errors.append(f"unsupported ad locale: {ad_locale}; choose en, ja, or yue")
                continue
            if ad_locale in seen:
                errors.append(f"duplicate ad locale: {ad_locale}")
            seen.add(ad_locale)
            expected_ui = LOCALE_TO_UI[ad_locale]
            if ui_locale != expected_ui:
                errors.append(f"locales must map {ad_locale}->{expected_ui}")
    output = config["output"]
    if int(output.get("width", 0)) != 1080 or int(output.get("height", 0)) != 1920:
        errors.append("output must be 1080x1920")
    maximum_duration = float(output.get("duration_seconds", 0))
    minimum_duration = float(output.get("minimum_duration_seconds", 15.0))
    preferred_duration = float(output.get("preferred_duration_seconds", min(18.0, maximum_duration)))
    if not 15 <= maximum_duration <= 20:
        errors.append("output.duration_seconds must be between 15 and 20")
    if not 15 <= minimum_duration <= preferred_duration <= maximum_duration:
        errors.append("output durations must satisfy 15 <= minimum <= preferred <= maximum")
    output["minimum_duration_seconds"] = minimum_duration
    output["preferred_duration_seconds"] = preferred_duration
    if config.get("catalog_json"):
        catalog = resolve_path(base, config["catalog_json"])
        if not catalog.is_file():
            errors.append(f"catalog_json not found: {catalog}")
        config["catalog_json"] = str(catalog)
    assets = config.setdefault("assets", {})
    if not assets.get("logo_cta"):
        assets["logo_cta"] = BUNDLED_LOGO_CTA_URI
    logo = DEFAULT_LOGO_CTA if assets["logo_cta"] == BUNDLED_LOGO_CTA_URI else resolve_path(base, assets["logo_cta"])
    if not logo.is_file():
        errors.append(f"assets.logo_cta not found: {logo}")
    assets["logo_cta"] = str(logo)
    try:
        cta_seconds = float(assets.get("logo_cta_excerpt_seconds", DEFAULT_LOGO_CTA_EXCERPT_SECONDS))
    except (TypeError, ValueError):
        cta_seconds = 0
    if not 2 <= cta_seconds <= 3:
        errors.append("assets.logo_cta_excerpt_seconds must be between 2 and 3")
    assets["logo_cta_excerpt_seconds"] = cta_seconds
    try:
        cta_start = float(assets.get("logo_cta_start_seconds", DEFAULT_LOGO_CTA_START_SECONDS))
    except (TypeError, ValueError):
        cta_start = -1
    if cta_start < 0:
        errors.append("assets.logo_cta_start_seconds must be zero or greater")
    assets["logo_cta_start_seconds"] = cta_start
    audio = config.setdefault("audio", {})
    if not str(audio.get("tts_voice", "")).strip():
        audio["tts_voice"] = "natural energetic young-adult female"
    if not str(audio.get("bgm_prompt", "")).strip():
        audio["bgm_prompt"] = (
            "at least 20 seconds of polished vertical social-ad background music matching the target Skill: "
            "immediate hook, clear rhythmic edit points, energetic but refined, instrumental only, "
            "no vocals, no spoken words, no copyrighted melody, full volume through the end, "
            "no early fade-out, loop-friendly ending"
        )
    if not str(audio.get("bgm_style", "")).strip():
        audio["bgm_style"] = "cinematic electronic social ad"
    try:
        bgm_volume = float(audio.get("bgm_volume", 0.22))
    except (TypeError, ValueError):
        bgm_volume = -1
    if not 0 < bgm_volume <= 0.5:
        errors.append("audio.bgm_volume must be greater than 0 and at most 0.5")
    audio["bgm_volume"] = bgm_volume
    audio["mute_source_audio"] = True
    audio["cta_source_audio"] = False
    if errors:
        raise AdCreatorError("Invalid campaign config:\n- " + "\n- ".join(errors))
    return config


def campaign_template(
    *,
    campaign_id: str,
    image: Path,
    skill_id: str,
    skill_name: str,
    skill_core: str,
    project_id: str,
    subject_description: str,
    locales: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "campaign_id": campaign_id,
        "input_image": str(image.resolve()),
        "subject_description": subject_description,
        "target_skill": {
            "id": skill_id,
            "name": skill_name,
            "core": skill_core,
            "transformation_type": "identity",
        },
        "project_binding": {
            "strategy": "one_skill_one_persistent_project",
            "skill_id": skill_id,
            "project_id": project_id,
        },
        "rights": {
            "owned_or_licensed": True,
            "adult_or_nonperson": True,
            "claims_substantiated": True,
            "basis": "user supplied the image for the requested advertising-material generation",
        },
        "offer": {
            "value_proposition": "Create a new visual direction from one photo",
            "cta": "TRY MAKARON",
            "destination_url": "",
        },
        "locales": locale_config(locales),
        "style_constraints": ["brand-safe", "identity-stable", "no unsupported claims"],
        "audio": {
            "tts_voice": "natural energetic young-adult female",
            "bgm_prompt": (
                "at least 20 seconds of polished vertical social-ad background music matching the target Skill: "
                "immediate hook, clear rhythmic edit points, energetic but refined, instrumental only, "
                "no vocals, no spoken words, no copyrighted melody, full volume through the end, "
                "no early fade-out, loop-friendly ending"
            ),
            "bgm_style": "cinematic electronic social ad",
            "bgm_volume": 0.22,
            "mute_source_audio": True,
            "cta_source_audio": False,
        },
        "automation": {
            "executor": "agent",
            "makaron_binary": "makaron",
            "max_attempts": 3,
            "builder_skill_id": "",
        },
        "assets": {
            "logo_cta": BUNDLED_LOGO_CTA_URI,
            "logo_cta_excerpt_seconds": DEFAULT_LOGO_CTA_EXCERPT_SECONDS,
            "logo_cta_start_seconds": DEFAULT_LOGO_CTA_START_SECONDS,
        },
        "output": {
            "width": 1080,
            "height": 1920,
            "minimum_duration_seconds": 15.0,
            "preferred_duration_seconds": 18.0,
            "duration_seconds": 20.0,
            "format": "mp4",
        },
    }
