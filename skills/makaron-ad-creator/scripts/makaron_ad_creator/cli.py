from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .pipeline import Pipeline, plan_for
from .schema import DEFAULT_AD_LOCALES, DEFAULT_LOGO_CTA, campaign_template, locale_config, validate_config
from .util import AdCreatorError, json_candidates, project_binding_key, read_json, run, sha256, slug, write_json


PROJECT_ROOT = Path(__file__).resolve().parents[4]
PROJECT_MEDIA_ROTATION_THRESHOLD = 60


def _workspace_root() -> Path:
    return Path(os.environ.get("MAKARON_AD_WORKSPACE", str(PROJECT_ROOT))).expanduser().resolve()


def _makaron_binary() -> str:
    return os.environ.get("MAKARON_AD_MAKARON_BIN", "makaron")


def _parse_ad_locales(raw: str | None) -> list[str]:
    if not raw or raw.strip().lower() == "all":
        return list(DEFAULT_AD_LOCALES)
    selected = [value.strip().lower() for value in raw.split(",") if value.strip()]
    locale_config(selected)
    return selected


def resolve_campaign_path(reference: str) -> Path:
    """Resolve a campaign.json path from a file, directory, or campaign id."""
    raw = Path(reference).expanduser()
    candidates: list[Path] = []
    if raw.is_absolute() or raw.exists() or len(raw.parts) > 1:
        candidates.extend([raw, raw / "campaign.json"])
    else:
        candidates.extend([
            _workspace_root() / "campaigns" / reference / "campaign.json",
            PROJECT_ROOT / "campaigns" / reference / "campaign.json",
            raw,
            raw / "campaign.json",
        ])
    checked: list[str] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if str(resolved) in checked:
            continue
        checked.append(str(resolved))
        if resolved.is_dir():
            resolved = resolved / "campaign.json"
        if resolved.is_file() and resolved.name == "campaign.json":
            return resolved
    raise AdCreatorError(
        f"Campaign not found: {reference}. Pass a campaign ID, campaign directory, or full campaign.json path."
    )


def _resolve_marketplace_skill(skill_name: str, binary: str) -> dict:
    result = run([binary, "skills", "show", skill_name, "--json"], timeout=120)
    candidates = [value for value in json_candidates(result.stdout) if isinstance(value, dict)]
    if not candidates:
        raise AdCreatorError(f"Makaron Marketplace returned no metadata for Skill name: {skill_name}")
    skill = candidates[-1]
    if not skill.get("id"):
        raise AdCreatorError(f"Resolved Marketplace Skill has no stable id: {skill_name}")
    return skill


def _skill_display_name(skill: dict, requested_name: str) -> str:
    if skill.get("label"):
        return str(skill["label"])
    labels = skill.get("labels")
    if isinstance(labels, dict):
        for locale in ("en", "zh-Hant", "zh", "ja"):
            if labels.get(locale):
                return str(labels[locale])
    return requested_name


def _skill_core(skill: dict, display_name: str) -> str:
    for key in ("description", "summary", "core", "prompt"):
        if isinstance(skill.get(key), str) and skill[key].strip():
            return skill[key].strip()
    prompts = skill.get("prompts")
    if isinstance(prompts, dict):
        for locale in ("en", "zh-Hant", "zh", "ja"):
            if isinstance(prompts.get(locale), str) and prompts[locale].strip():
                return prompts[locale].strip()
    return f"apply the Marketplace Skill named {display_name} to the authorized input image"


def _project_media_count(binary: str, project_id: str) -> int | None:
    """Read the current project timeline size without turning a probe failure into a rotation."""
    try:
        result = run([binary, "project", "media", project_id, "--json"], timeout=60)
    except AdCreatorError:
        return None
    for candidate in reversed(list(json_candidates(result.stdout))):
        if isinstance(candidate, dict):
            media = candidate.get("media")
            if not isinstance(media, list) and isinstance(candidate.get("result"), dict):
                media = candidate["result"].get("media")
            if isinstance(media, list):
                return len(media)
        elif isinstance(candidate, list):
            return len(candidate)
    return None


def _create_bound_project(binary: str, skill_name: str, image: Path) -> str:
    result = run([binary, "create", "--image", str(image), "--title", f"makaron-ad · {skill_name}"], timeout=300)
    match = re.search(r"^\s*ID:\s*(\S+)\s*$", result.stdout, re.MULTILINE)
    if not match:
        candidates = [value for value in json_candidates(result.stdout) if isinstance(value, dict)]
        project_id = next((str(value.get("projectId") or value.get("project_id")) for value in reversed(candidates) if value.get("projectId") or value.get("project_id")), "")
    else:
        project_id = match.group(1)
    if not project_id or project_id == "auto":
        raise AdCreatorError("Makaron created a project but returned no persistent project ID")
    return project_id


def _project_for_skill(workspace: Path, binary: str, skill_id: str, skill_name: str, image: Path) -> str:
    registry_path = workspace / "project-registry.json"
    registry = read_json(registry_path) if registry_path.exists() else {"version": 2, "bindings": {}, "history": {}}
    registry["version"] = 2
    bindings = registry.setdefault("bindings", {})
    history = registry.setdefault("history", {})
    binding_key = project_binding_key(skill_id, image)
    existing = str(bindings.get(binding_key) or "")
    if existing:
        media_count = _project_media_count(binary, existing)
        if media_count is None or media_count < PROJECT_MEDIA_ROTATION_THRESHOLD:
            registry.setdefault("metadata", {})[binding_key] = {
                "skill_id": skill_id,
                "input_sha256": sha256(image),
                "active_project_id": existing,
                "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            write_json(registry_path, registry)
            return existing
    project_id = _create_bound_project(binary, skill_name, image)
    if existing:
        history.setdefault(binding_key, []).append({
            "project_id": existing,
            "reason": "media-capacity",
            "media_count": media_count,
            "rotated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
    bindings[binding_key] = project_id
    registry.setdefault("metadata", {})[binding_key] = {
        "skill_id": skill_id,
        "input_sha256": sha256(image),
        "active_project_id": project_id,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    write_json(registry_path, registry)
    return project_id


def command_make(args: argparse.Namespace) -> int:
    """Public two-input entrypoint: image + Marketplace Skill name."""
    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        raise AdCreatorError(f"Input image not found: {image}")
    locales = _parse_ad_locales(args.locales)
    workspace = _workspace_root()
    binary = _makaron_binary()
    skill = _resolve_marketplace_skill(args.skill_name, binary)
    skill_id = str(skill["id"])
    display_name = _skill_display_name(skill, args.skill_name)
    core = _skill_core(skill, display_name)
    project_id = _project_for_skill(workspace, binary, skill_id, display_name, image)
    fingerprint = sha256(image)[:8]
    campaign_id = slug(f"{display_name}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{fingerprint}")
    campaign_dir = workspace / "campaigns" / campaign_id
    config_path = campaign_dir / "campaign.json"
    config = campaign_template(
        campaign_id=campaign_id,
        image=image,
        skill_id=skill_id,
        skill_name=display_name,
        skill_core=core,
        project_id=project_id,
        subject_description="authorized adult, fictional character, or owned product in the supplied input image",
        locales=locales,
    )
    config["automation"]["executor"] = "makaron"
    config["automation"]["makaron_binary"] = binary
    config["offer"]["value_proposition"] = f"Create the {display_name} result from one photo"
    config["resolved_marketplace_skill"] = skill
    campaign_dir.mkdir(parents=True, exist_ok=True)
    write_json(config_path, config)
    write_json(campaign_dir / "plan.json", {"version": 1, "campaign_id": campaign_id, "nodes": plan_for(config)})
    pipeline = Pipeline(config_path, executor="makaron")
    status = pipeline.run()
    payload = {
        "status": status,
        "campaign": str(config_path),
        "project_id": project_id,
        "deliverables": str(campaign_dir / "deliverables"),
        "locales": locales,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 2


def command_init(args: argparse.Namespace) -> int:
    if not args.confirm_rights:
        raise AdCreatorError("Use --confirm-rights only after confirming ownership/consent, adult-or-nonperson status, and substantiated claims")
    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        raise AdCreatorError(f"Input image not found: {image}")
    if not args.project_id or args.project_id == "auto":
        raise AdCreatorError("--project-id must be the persistent non-auto Makaron project bound to this Skill")
    campaign_id = args.campaign_id or slug(f"{args.skill_name}-{image.stem}")
    campaign_dir = (Path(args.output_dir).expanduser().resolve() if args.output_dir else PROJECT_ROOT / "campaigns" / campaign_id)
    config_path = campaign_dir / "campaign.json"
    if config_path.exists() and not args.force:
        raise AdCreatorError(f"Campaign already exists: {config_path}; use --force only to replace the config")
    config = campaign_template(
        campaign_id=campaign_id,
        image=image,
        skill_id=args.skill,
        skill_name=args.skill_name,
        skill_core=args.skill_core,
        project_id=args.project_id,
        subject_description=args.subject_description,
        locales=_parse_ad_locales(args.locales),
    )
    if args.executor:
        config["automation"]["executor"] = args.executor
    if args.catalog_json:
        config["catalog_json"] = str(Path(args.catalog_json).expanduser().resolve())
    if args.logo_cta:
        config["assets"]["logo_cta"] = str(Path(args.logo_cta).expanduser().resolve())
        config["assets"]["logo_cta_start_seconds"] = float(args.logo_cta_start_seconds or 0)
    elif args.logo_cta_start_seconds is not None:
        config["assets"]["logo_cta_start_seconds"] = float(args.logo_cta_start_seconds)
    if args.logo_cta_excerpt_seconds is not None:
        config["assets"]["logo_cta_excerpt_seconds"] = float(args.logo_cta_excerpt_seconds)
    campaign_dir.mkdir(parents=True, exist_ok=True)
    write_json(config_path, config)
    validate_config(read_json(config_path), config_path)
    write_json(campaign_dir / "plan.json", {"version": 1, "campaign_id": campaign_id, "nodes": plan_for(config)})
    print(config_path)
    return 0


def command_plan(args: argparse.Namespace) -> int:
    config_path = resolve_campaign_path(args.campaign)
    config = validate_config(read_json(config_path), config_path)
    plan = {"version": 1, "campaign_id": config["campaign_id"], "nodes": plan_for(config)}
    destination = config_path.parent / "plan.json"
    write_json(destination, plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def command_run(args: argparse.Namespace) -> int:
    pipeline = Pipeline(resolve_campaign_path(args.campaign), executor=args.executor)
    status = pipeline.run()
    payload = {"status": status, "state": str(pipeline.state_path)}
    waiting = next((value for value in pipeline.state["nodes"].values() if value.get("status") == "WAITING_FOR_AGENT"), None)
    if waiting:
        payload["request"] = waiting.get("request")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 3


def command_status(args: argparse.Namespace) -> int:
    config_path = resolve_campaign_path(args.campaign)
    state_path = config_path.parent / "state.json"
    if not state_path.exists():
        print(json.dumps({"status": "NOT_STARTED", "state": str(state_path)}, indent=2))
        return 0
    print(json.dumps(read_json(state_path), ensure_ascii=False, indent=2))
    return 0


def command_complete(args: argparse.Namespace) -> int:
    pipeline = Pipeline(resolve_campaign_path(args.campaign), executor="agent")
    pipeline.complete_agent_node(
        args.node,
        Path(args.artifact),
        args.response_id,
        args.source_url,
        Path(args.timing_manifest) if args.timing_manifest else None,
    )
    print(json.dumps({"status": "PASS", "node": args.node, "state": str(pipeline.state_path)}, indent=2))
    return 0


def command_fail(args: argparse.Namespace) -> int:
    pipeline = Pipeline(resolve_campaign_path(args.campaign), executor="agent")
    pipeline.fail_agent_node(args.node, args.error)
    status = pipeline.state["nodes"][args.node]["status"]
    print(json.dumps({"status": status, "node": args.node, "state": str(pipeline.state_path)}, indent=2))
    return 3 if status == "PENDING" else 2


def command_retry(args: argparse.Namespace) -> int:
    pipeline = Pipeline(resolve_campaign_path(args.campaign))
    node_ids = [item["id"] for item in pipeline.plan]
    if args.node not in node_ids:
        raise AdCreatorError(f"Unknown node: {args.node}")
    reset = {args.node}
    changed = True
    while changed:
        changed = False
        for node in pipeline.plan:
            if node["id"] not in reset and any(dep in reset for dep in node["depends_on"]):
                reset.add(node["id"])
                changed = True
    for node_id in reset:
        pipeline.state["nodes"][node_id] = {"status": "PENDING", "attempts": 0, "artifacts": []}
    pipeline.state["status"] = "PENDING"
    pipeline.save()
    print(json.dumps({"reset": [node for node in node_ids if node in reset]}, indent=2))
    return 0


def command_doctor(_: argparse.Namespace) -> int:
    checks = {
        "python": sys.version.split()[0],
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "makaron": shutil.which("makaron"),
        "pillow": None,
        "workflow_skill": str(PROJECT_ROOT / "skills" / "edit-makaron-app-workflow-recording" / "SKILL.md"),
        "fixed_logo_cta": str(DEFAULT_LOGO_CTA),
    }
    try:
        import PIL
        checks["pillow"] = PIL.__version__
    except ImportError:
        pass
    required = (
        checks["ffmpeg"], checks["ffprobe"], checks["makaron"], checks["pillow"],
        Path(checks["workflow_skill"]).is_file(), Path(checks["fixed_logo_cta"]).is_file(),
    )
    checks["pass"] = all(required)
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if checks["pass"] else 2


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="makaron-ad", description="One-image to selected-locale Makaron ad orchestration")
    sub = root.add_subparsers(dest="command", required=True)

    make = sub.add_parser("make", help="One-command production: INPUT_IMAGE + MARKETPLACE_SKILL_NAME")
    make.add_argument("image")
    make.add_argument("skill_name")
    make.add_argument("--locale", "--locales", dest="locales", default="all", help="en, ja, yue, a comma-separated subset, or all")
    make.set_defaults(func=command_make)

    init = sub.add_parser("init", help="Create a campaign config and deterministic asset plan")
    init.add_argument("--image", required=True)
    init.add_argument("--skill", required=True, help="Marketplace Skill ID")
    init.add_argument("--skill-name", required=True)
    init.add_argument("--skill-core", required=True)
    init.add_argument("--project-id", required=True, help="Persistent project already authorized for this Skill")
    init.add_argument("--subject-description", default="authorized adult subject or owned product in the supplied image")
    init.add_argument("--campaign-id")
    init.add_argument("--output-dir")
    init.add_argument("--catalog-json")
    init.add_argument("--logo-cta")
    init.add_argument("--logo-cta-start-seconds", type=float)
    init.add_argument("--logo-cta-excerpt-seconds", type=float)
    init.add_argument("--executor", choices=("agent", "makaron"), default="agent")
    init.add_argument("--locale", "--locales", dest="locales", default="all", help="en, ja, yue, a comma-separated subset, or all")
    init.add_argument("--confirm-rights", action="store_true")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=command_init)

    plan = sub.add_parser("plan", help="Print and save the campaign DAG")
    plan.add_argument("campaign", help="Campaign ID, campaign directory, or full campaign.json path")
    plan.set_defaults(func=command_plan)

    execute = sub.add_parser("run", help="Run or resume a campaign")
    execute.add_argument("campaign", help="Campaign ID, campaign directory, or full campaign.json path")
    execute.add_argument("--executor", choices=("agent", "makaron"))
    execute.set_defaults(func=command_run)

    status = sub.add_parser("status", help="Print resumable pipeline state")
    status.add_argument("campaign", help="Campaign ID, campaign directory, or full campaign.json path")
    status.set_defaults(func=command_status)

    complete = sub.add_parser("complete", help="Attach an artifact produced by another Agent")
    complete.add_argument("campaign", help="Campaign ID, campaign directory, or full campaign.json path")
    complete.add_argument("--node", required=True)
    complete.add_argument("--artifact", required=True)
    complete.add_argument("--response-id")
    complete.add_argument("--source-url", help="Original HTTP(S) media URL; recommended for BGM longer than local chat upload limits")
    complete.add_argument("--timing-manifest", help="Required for final-* nodes: Remotion Caption/scene contract v2 JSON sidecar")
    complete.set_defaults(func=command_complete)

    fail = sub.add_parser("fail", help="Report a failed Agent request and advance its retry budget")
    fail.add_argument("campaign", help="Campaign ID, campaign directory, or full campaign.json path")
    fail.add_argument("--node", required=True)
    fail.add_argument("--error", required=True)
    fail.set_defaults(func=command_fail)

    retry = sub.add_parser("retry", help="Reset one node and all downstream nodes")
    retry.add_argument("campaign", help="Campaign ID, campaign directory, or full campaign.json path")
    retry.add_argument("--node", required=True)
    retry.set_defaults(func=command_retry)

    doctor = sub.add_parser("doctor", help="Check local runtime dependencies")
    doctor.set_defaults(func=command_doctor)
    return root


def main(argv: list[str] | None = None) -> int:
    try:
        raw = list(sys.argv[1:] if argv is None else argv)
        commands = {"make", "init", "plan", "run", "status", "complete", "fail", "retry", "doctor"}
        if len(raw) >= 2 and raw[0] not in commands and not raw[0].startswith("-"):
            raw.insert(0, "make")
        args = parser().parse_args(raw)
        return int(args.func(args))
    except AdCreatorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
