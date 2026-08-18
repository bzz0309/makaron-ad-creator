from __future__ import annotations

from pathlib import Path
from typing import Any

from .util import AdCreatorError, resolve_path


DEFAULT_LOCALES = [
    {"ad_locale": "en", "ui_locale": "en"},
    {"ad_locale": "ja", "ui_locale": "ja"},
    {"ad_locale": "yue", "ui_locale": "zh-Hant"},
]


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
    locales = config.setdefault("locales", DEFAULT_LOCALES)
    locale_pairs = {(item.get("ad_locale"), item.get("ui_locale")) for item in locales}
    expected = {("en", "en"), ("ja", "ja"), ("yue", "zh-Hant")}
    if locale_pairs != expected:
        errors.append("locales must map en->en, ja->ja, and yue->zh-Hant")
    output = config["output"]
    if int(output.get("width", 0)) != 1080 or int(output.get("height", 0)) != 1920:
        errors.append("output must be 1080x1920")
    duration = float(output.get("duration_seconds", 0))
    if not 15 <= duration <= 18:
        errors.append("output.duration_seconds must be between 15 and 18")
    if config.get("catalog_json"):
        catalog = resolve_path(base, config["catalog_json"])
        if not catalog.is_file():
            errors.append(f"catalog_json not found: {catalog}")
        config["catalog_json"] = str(catalog)
    if config.get("assets", {}).get("logo_cta"):
        logo = resolve_path(base, config["assets"]["logo_cta"])
        if not logo.is_file():
            errors.append(f"assets.logo_cta not found: {logo}")
        config["assets"]["logo_cta"] = str(logo)
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
        "locales": DEFAULT_LOCALES,
        "style_constraints": ["brand-safe", "identity-stable", "no unsupported claims"],
        "automation": {
            "executor": "agent",
            "makaron_binary": "makaron",
            "max_attempts": 3,
            "builder_skill_id": "",
        },
        "assets": {"logo_cta": ""},
        "output": {"width": 1080, "height": 1920, "duration_seconds": 18.0, "format": "mp4"},
    }
