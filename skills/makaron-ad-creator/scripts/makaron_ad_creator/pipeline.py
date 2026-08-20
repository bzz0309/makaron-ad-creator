from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapter import MakaronAdapter, bind_ad_remotion_assets, extract_generated_image_urls, extract_generated_video_urls, extract_json_object, extract_remotion_design, validate_ad_remotion_design, validate_timing_manifest
from .media import bgm_similarity_in_cta, effect_segment_plan, extract_video_segment, is_vertical_resolution_acceptable, probe_audio, probe_image, probe_video
from .prompts import after_prompt, before_prompt, bgm_prompt, comparison_prompt, effect_prompt, final_prompt, script_prompt
from .schema import DEFAULT_LOGO_CTA, DEFAULT_LOGO_CTA_MASTER, LOCALE_TO_UI, ad_locales, validate_config
from .util import AdCreatorError, read_json, run as run_command, sha256, write_json


MODELS = ["seedance-2-0", "kling", "grok"]


def cached_final_design_matches_effect_segments(
    design: dict[str, Any],
    *,
    hook_duration: float,
    result_duration: float,
    tolerance_seconds: float = 0.25,
) -> bool:
    """Only reuse a Remotion design when its effect scenes fit the current clips."""
    validate_ad_remotion_design(design)
    scenes = design["props"]["scenes"]

    def scene_duration(scene_id: str) -> float:
        timing = scenes[scene_id]
        return (float(timing["endMs"]) - float(timing["startMs"])) / 1000.0

    return (
        abs(scene_duration("hook") - hook_duration) <= tolerance_seconds
        and scene_duration("result") <= result_duration + tolerance_seconds
    )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def plan_for(config: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [
        {"id": "validate", "kind": "local", "depends_on": []},
        {"id": "scripts", "kind": "generate_json", "depends_on": ["validate"]},
        {"id": "before", "kind": "generate_image", "depends_on": ["validate"]},
        {"id": "effect", "kind": "generate_video", "depends_on": ["validate"]},
        {"id": "hook", "kind": "local", "depends_on": ["effect"]},
        {"id": "result", "kind": "local", "depends_on": ["effect"]},
        {"id": "bgm", "kind": "generate_audio", "depends_on": ["validate"]},
        {"id": "after", "kind": "generate_image", "depends_on": ["effect"]},
        {"id": "comparison", "kind": "generate_image", "depends_on": ["before", "after"]},
    ]
    selected_locales = ad_locales(config)
    for locale in selected_locales:
        nodes.append({
            "id": f"workflow-{locale}",
            "kind": "local",
            "depends_on": ["validate"],
        })
    for locale in selected_locales:
        nodes.append({
            "id": f"final-{locale}",
            "kind": "generate_video",
            "depends_on": ["scripts", "comparison", "hook", "result", f"workflow-{locale}", "bgm"],
        })
    nodes += [
        {"id": "qc", "kind": "local", "depends_on": [f"final-{locale}" for locale in selected_locales]},
        {"id": "deliver", "kind": "local", "depends_on": ["qc"]},
    ]
    return nodes


class Pipeline:
    def __init__(self, config_path: Path, executor: str | None = None) -> None:
        self.config_path = config_path.resolve()
        self.config = validate_config(read_json(self.config_path), self.config_path)
        self.campaign_dir = self.config_path.parent
        self.run_dir = self.campaign_dir / "run"
        self.state_path = self.campaign_dir / "state.json"
        self.executor = executor or self.config.get("automation", {}).get("executor", "agent")
        if self.executor not in {"agent", "makaron"}:
            raise AdCreatorError("executor must be agent or makaron")
        self.plan = plan_for(self.config)
        self.state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            state = read_json(self.state_path)
        else:
            state = {
                "version": 1,
                "campaign_id": self.config["campaign_id"],
                "status": "PENDING",
                "created_at": now(),
                "updated_at": now(),
                "nodes": {},
            }
        for node in self.plan:
            state["nodes"].setdefault(node["id"], {"status": "PENDING", "attempts": 0, "artifacts": []})
        return state

    def save(self) -> None:
        self.state["updated_at"] = now()
        write_json(self.state_path, self.state)

    def artifact(self, node_id: str, suffix: str | None = None) -> Path:
        items = self.state["nodes"][node_id].get("artifacts", [])
        paths = [Path(item["path"]) for item in items if item.get("path")]
        if suffix:
            paths = [path for path in paths if path.suffix.lower() == suffix.lower()]
        if not paths:
            raise AdCreatorError(f"Missing artifact from completed node {node_id}")
        return paths[0]

    def add_artifact(self, node_id: str, path: Path, **metadata: Any) -> dict[str, Any]:
        if not path.is_file():
            raise AdCreatorError(f"Expected artifact was not created: {path}")
        item = {"path": str(path.resolve()), "sha256": sha256(path), "bytes": path.stat().st_size, **metadata}
        self.state["nodes"][node_id]["artifacts"] = [item]
        return item

    def ready(self, node: dict[str, Any]) -> bool:
        return all(self.state["nodes"][dep]["status"] == "PASS" for dep in node["depends_on"])

    def run(self) -> str:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.state["status"] = "RUNNING"
        self.save()
        while True:
            pending = [node for node in self.plan if self.state["nodes"][node["id"]]["status"] != "PASS"]
            if not pending:
                self.state["status"] = "PASS"
                self.save()
                return "PASS"
            progressed = False
            for node in pending:
                node_state = self.state["nodes"][node["id"]]
                if node_state["status"] == "WAITING_FOR_AGENT":
                    self.state["status"] = "WAITING_FOR_AGENT"
                    self.save()
                    return "WAITING_FOR_AGENT"
                if node_state["status"] == "BLOCKED":
                    self.state["status"] = "BLOCKED"
                    self.save()
                    return "BLOCKED"
                if not self.ready(node):
                    continue
                if self.executor == "agent" and node["kind"].startswith("generate_"):
                    self._write_agent_request(node)
                    self.state["status"] = "WAITING_FOR_AGENT"
                    self.save()
                    return "WAITING_FOR_AGENT"
                self._execute_with_budget(node)
                progressed = True
                if self.state["nodes"][node["id"]]["status"] == "BLOCKED":
                    self.state["status"] = "BLOCKED"
                    self.save()
                    return "BLOCKED"
            if not progressed:
                raise AdCreatorError("Pipeline cannot progress; inspect state.json dependencies")

    def _execute_with_budget(self, node: dict[str, Any]) -> None:
        state = self.state["nodes"][node["id"]]
        maximum = int(self.config.get("automation", {}).get("max_attempts", 3)) if node["kind"].startswith("generate_") else 1
        while state["attempts"] < maximum:
            state["attempts"] += 1
            state["status"] = "RUNNING"
            self.save()
            try:
                self._execute(node, state["attempts"])
            except Exception as exc:
                state["last_error"] = str(exc)
                state["status"] = "REROLL" if state["attempts"] < maximum else "BLOCKED"
                self.save()
                if state["status"] == "BLOCKED":
                    return
                continue
            state["status"] = "PASS"
            state["completed_at"] = now()
            state.pop("last_error", None)
            self.save()
            return

    def _execute(self, node: dict[str, Any], attempt: int) -> None:
        node_id = node["id"]
        if node_id == "validate":
            self._validate_binding()
        elif node_id == "scripts":
            self._generate_scripts()
        elif node_id == "before":
            self._generate_before()
        elif node_id == "hook":
            self._derive_effect_segment("hook")
        elif node_id == "result":
            self._derive_effect_segment("result")
        elif node_id == "effect":
            self._generate_effect(attempt)
        elif node_id == "bgm":
            self._generate_bgm()
        elif node_id == "after":
            self._generate_after()
        elif node_id == "comparison":
            self._generate_comparison()
        elif node_id.startswith("workflow-"):
            self._generate_workflow(node_id.split("-", 1)[1])
        elif node_id.startswith("final-"):
            self._generate_final(node_id.split("-", 1)[1], attempt)
        elif node_id == "qc":
            self._qc()
        elif node_id == "deliver":
            self._deliver()
        else:
            raise AdCreatorError(f"Unknown node {node_id}")

    def _adapter(self) -> MakaronAdapter:
        return MakaronAdapter(
            self.config["project_binding"]["project_id"],
            self.run_dir,
            self.config.get("automation", {}).get("makaron_binary", "makaron"),
        )

    def _validate_binding(self) -> None:
        registry_path = self.campaign_dir.parent.parent / "project-registry.json"
        skill_id = self.config["target_skill"]["id"]
        project_id = self.config["project_binding"]["project_id"]
        registry = read_json(registry_path) if registry_path.exists() else {"version": 1, "bindings": {}}
        current = registry["bindings"].get(skill_id)
        if current and current != project_id:
            raise AdCreatorError(f"Skill {skill_id} is already bound to project {current}; migration requires explicit registry edit")
        for existing_skill, existing_project in registry["bindings"].items():
            if existing_project == project_id and existing_skill != skill_id:
                raise AdCreatorError(f"Project {project_id} is already bound to another Skill: {existing_skill}")
        registry["bindings"][skill_id] = project_id
        write_json(registry_path, registry)
        write_json(self.campaign_dir / "project-binding.json", self.config["project_binding"])

    def _generate_scripts(self) -> None:
        result = self._adapter().chat(node_id="scripts", prompt=script_prompt(self.config))
        selected_locales = tuple(ad_locales(self.config))
        scripts = extract_json_object(result["response"], selected_locales)
        self._validate_scripts(scripts)
        output = self.run_dir / "scripts.json"
        write_json(output, scripts)
        self.add_artifact("scripts", output, response_id=result.get("response_id"))

    def _validate_scripts(self, scripts: dict[str, Any]) -> None:
        selected_locales = ad_locales(self.config)
        if set(scripts) != set(selected_locales):
            raise AdCreatorError(f"scripts must contain only selected locale keys: {', '.join(selected_locales)}")
        for locale in selected_locales:
            lines = scripts.get(locale)
            if not isinstance(lines, list) or len(lines) != 5 or not all(isinstance(line, str) and line.strip() for line in lines):
                raise AdCreatorError(f"scripts.{locale} must contain exactly five non-empty strings")

    def _generate_before(self) -> None:
        output = self.run_dir / "assets" / "before.png"
        result = self._adapter().chat(
            node_id="before",
            prompt=before_prompt(self.config),
            images=[Path(self.config["input_image"])],
            destination=output,
            require_generated_image=True,
        )
        self.add_artifact("before", output, response_id=result.get("response_id"), source_url=result.get("source_url"))

    def _generate_effect(self, attempt: int) -> None:
        output = self.run_dir / "assets" / "effect.mp4"
        result = self._adapter().chat(
            node_id="effect",
            prompt=effect_prompt(self.config, MODELS[min(attempt - 1, len(MODELS) - 1)]),
            skill_id=self.config["target_skill"]["id"],
            images=[Path(self.config["input_image"])],
            destination=output,
        )
        info = probe_video(output)
        if not is_vertical_resolution_acceptable(info, self.config["output"]):
            raise AdCreatorError("Effect video must be vertical 9:16 and at least 720x1280")
        self.add_artifact("effect", output, response_id=result.get("response_id"), source_url=result.get("source_url"), model=MODELS[min(attempt - 1, 2)], resolution=f"{info['width']}x{info['height']}")

    def _derive_effect_segment(self, role: str) -> None:
        if role not in {"hook", "result"}:
            raise AdCreatorError(f"Unknown target-Skill segment role: {role}")
        effect = self.artifact("effect", ".mp4")
        plan = effect_segment_plan(effect)
        start = float(plan[f"{role}_start"])
        duration = float(plan[f"{role}_duration"])
        output = self.run_dir / "assets" / f"{role}.mp4"
        extract_video_segment(effect, output, start_seconds=start, duration_seconds=duration)
        info = probe_video(output)
        if not is_vertical_resolution_acceptable(info, self.config["output"]):
            raise AdCreatorError(f"Derived {role} video must be vertical 9:16 and at least 720x1280")
        self.add_artifact(
            role,
            output,
            source="exact-non-overlapping-effect-segment",
            source_effect_sha256=sha256(effect),
            start_seconds=start,
            duration_seconds=duration,
            resolution=f"{info['width']}x{info['height']}",
        )

    def _generate_bgm(self) -> None:
        output = self.run_dir / "assets" / "bgm.mp3"
        result = self._adapter().create_music(
            node_id="bgm",
            prompt=bgm_prompt(self.config),
            style=str(self.config["audio"]["bgm_style"]),
            destination=output,
        )
        info = probe_audio(output)
        self.add_artifact(
            "bgm",
            output,
            response_id=result.get("response_id"),
            source_url=result.get("source_url"),
            audio_policy="instrumental-only; loop across full final ad",
            duration=info["duration"],
        )

    def _generate_after(self) -> None:
        output = self.run_dir / "assets" / "after.png"
        result = self._adapter().chat(
            node_id="after",
            prompt=after_prompt(self.config),
            videos=[self.artifact("effect", ".mp4")],
            destination=output,
            require_generated_image=True,
        )
        info = probe_image(output)
        if not is_vertical_resolution_acceptable(info, self.config["output"]):
            raise AdCreatorError("Makaron After keyframe must be vertical 9:16 and at least 720x1280")
        self.add_artifact("after", output, response_id=result.get("response_id"), source_url=result.get("source_url"), source="makaron-exact-effect-keyframe", resolution=f"{info['width']}x{info['height']}")

    def _generate_comparison(self) -> None:
        output = self.run_dir / "assets" / "comparison.png"
        result = self._adapter().chat(
            node_id="comparison",
            prompt=comparison_prompt(self.config),
            images=[self.artifact("before"), self.artifact("after")],
            destination=output,
            require_generated_image=True,
        )
        info = probe_image(output)
        if not is_vertical_resolution_acceptable(info, self.config["output"]):
            raise AdCreatorError("Makaron comparison must be vertical 9:16 and at least 720x1280")
        self.add_artifact("comparison", output, response_id=result.get("response_id"), source_url=result.get("source_url"), source="makaron-composition", resolution=f"{info['width']}x{info['height']}")

    def _generate_workflow(self, ad_locale: str) -> None:
        node_id = f"workflow-{ad_locale}"
        output = self.run_dir / "workflow" / f"workflow-{ad_locale}.mp4"
        workflow_skill = Path(__file__).resolve().parents[3] / "edit-makaron-app-workflow-recording"
        script = workflow_skill / "scripts" / "workflow_recording.py"
        if not script.is_file():
            raise AdCreatorError(f"Bundled v5 workflow Skill is missing: {script}")
        generated_dir = self.run_dir / "workflow" / f"v5-{ad_locale}"
        command = [
            sys.executable,
            str(script),
            "synthesize",
            "--skill",
            self.config["target_skill"]["id"],
            "--locales",
            LOCALE_TO_UI[ad_locale],
            "--output-dir",
            str(generated_dir),
            "--cache-dir",
            str(self.run_dir / "workflow" / ".v5-cache"),
        ]
        completed = run_command(command, timeout=1200)
        try:
            result = json.loads(completed.stdout)
            generated = result["outputs"][0]
            generated_video = Path(generated["output"])
            qc_path = Path(generated["qc"])
            manifest_path = Path(result["manifest"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AdCreatorError("v5 workflow Skill returned an invalid result manifest") from exc
        if not generated_video.is_file() or not qc_path.is_file() or not manifest_path.is_file():
            raise AdCreatorError("v5 workflow Skill did not create its video, QC, and manifest outputs")
        qc = read_json(qc_path)
        if not qc.get("pass"):
            raise AdCreatorError("v5 workflow Skill failed deterministic visual or technical QC")
        output.parent.mkdir(parents=True, exist_ok=True)
        if generated_video.resolve() != output.resolve():
            shutil.copy2(generated_video, output)
        info = probe_video(output)
        if not is_vertical_resolution_acceptable(info, self.config["output"]):
            raise AdCreatorError("v5 Makaron workflow must be vertical 9:16 and at least 720x1280")
        if not 3.5 <= float(info["duration"]) <= 4.5:
            raise AdCreatorError("v5 Makaron workflow must be 3.5-4.5 seconds")
        self.add_artifact(
            node_id,
            output,
            source="edit-makaron-app-workflow-recording-v5",
            ui_locale=LOCALE_TO_UI[ad_locale],
            resolution=f"{info['width']}x{info['height']}",
            qc_manifest=str(qc_path.resolve()),
            workflow_manifest=str(manifest_path.resolve()),
            keyframes=generated.get("keyframes"),
        )

    def _workflow_for(self, ad_locale: str) -> Path:
        return self.artifact(f"workflow-{ad_locale}", ".mp4")

    def _bgm_input(self) -> str:
        item = self.state["nodes"]["bgm"]["artifacts"][0]
        source_url = str(item.get("source_url") or "")
        if source_url.startswith(("https://", "http://")):
            return source_url
        return str(self.artifact("bgm"))

    def _final_video_input(self, node_id: str, path: Path, *, role: str) -> str:
        if node_id in self.state["nodes"]:
            items = self.state["nodes"][node_id].get("artifacts", [])
            if items:
                source_url = str(items[0].get("source_url") or "")
                if source_url.startswith(("https://", "http://")):
                    return source_url
            response_path = self.run_dir / "responses" / f"{node_id}.json"
            if response_path.is_file():
                generated_urls = extract_generated_video_urls(read_json(response_path))
                if generated_urls:
                    return generated_urls[0]
        return self._adapter().publish_local_media(path, role=role)

    def _final_video_inputs(self, locale: str) -> list[str]:
        return [
            self._final_video_input("hook", self.artifact("hook", ".mp4"), role="hook"),
            self._final_video_input("result", self.artifact("result", ".mp4"), role="result"),
            self._final_video_input(f"workflow-{locale}", self._workflow_for(locale), role=f"workflow-{locale}"),
            self._final_video_input("logo-cta", self._cta_input_path(), role="logo-cta"),
        ]

    def _cta_input_path(self) -> Path:
        configured = Path(self.config["assets"]["logo_cta"]).resolve()
        if (
            configured == DEFAULT_LOGO_CTA_MASTER.resolve()
            and float(self.config["assets"]["logo_cta_start_seconds"]) == 0.0
            and float(self.config["assets"]["logo_cta_excerpt_seconds"]) == 3.0
        ):
            return DEFAULT_LOGO_CTA.resolve()
        return configured

    def _final_image_input(self, node_id: str, path: Path, *, role: str) -> str:
        items = self.state["nodes"][node_id].get("artifacts", [])
        if items:
            source_url = str(items[0].get("source_url") or "")
            if source_url.startswith(("https://", "http://")):
                return source_url
        response_path = self.run_dir / "responses" / f"{node_id}.json"
        if response_path.is_file():
            generated_urls = extract_generated_image_urls(read_json(response_path))
            if generated_urls:
                return generated_urls[0]
        return self._adapter().publish_local_media(path, role=role)

    def _generate_final(self, locale: str, attempt: int) -> None:
        scripts = read_json(self.artifact("scripts"))
        output = self.run_dir / "final" / f"final-artifact-{locale}.mp4"
        videos = self._final_video_inputs(locale)
        comparison_input = self._final_image_input("comparison", self.artifact("comparison"), role="comparison")
        bgm_input = self._bgm_input()
        node_id = f"final-{locale}"
        adapter = self._adapter()
        cached_response_path = self.run_dir / "responses" / f"{node_id}.json"
        cached_response = read_json(cached_response_path) if cached_response_path.is_file() else None
        cached_design = extract_remotion_design(cached_response) if cached_response else None
        cached_contract_valid = False
        if attempt == 1 and cached_design:
            try:
                cached_binding_changes = bind_ad_remotion_assets(
                    cached_design,
                    comparison_image=comparison_input,
                    videos=videos,
                    bgm_url=bgm_input,
                )
                cached_contract_valid = cached_final_design_matches_effect_segments(
                    cached_design,
                    hook_duration=float(probe_video(self.artifact("hook", ".mp4"))["duration"]),
                    result_duration=float(probe_video(self.artifact("result", ".mp4"))["duration"]),
                )
            except AdCreatorError:
                cached_contract_valid = False
        if cached_contract_valid:
            fallback = adapter.render_remotion_fallback(node_id, cached_response, output)
            result = {
                "response_id": cached_response.get("response_id"),
                "render_fallback": fallback,
            }
            final_design = cached_design
            binding_changes = cached_binding_changes
        else:
            result = adapter.chat(
                node_id=node_id,
                prompt=final_prompt(self.config, locale, scripts, MODELS[min(attempt - 1, len(MODELS) - 1)]),
                skill_id=self.config.get("automation", {}).get("builder_skill_id") or None,
                images=[comparison_input],
                videos=videos,
                audios=[bgm_input],
                destination=output,
                require_generated_video=True,
            )
            final_design = extract_remotion_design(result.get("response"))
            if not final_design:
                raise AdCreatorError("Final Remotion output is missing the required caption/scene timing contract")
            binding_changes = bind_ad_remotion_assets(
                final_design,
                comparison_image=comparison_input,
                videos=videos,
                bgm_url=bgm_input,
            )
            validate_ad_remotion_design(final_design)
            if binding_changes:
                corrected = adapter.render_remotion_fallback(node_id, result["response"], output)
                result["render_fallback"] = corrected
        binding_manifest = self.run_dir / "final" / f"asset-bindings-{locale}.json"
        write_json(binding_manifest, {
            "comparisonImage": comparison_input,
            "hookVideo": videos[0],
            "resultVideo": videos[1],
            "workflowVideo": videos[2],
            "ctaVideo": videos[3],
            "bgmUrl": bgm_input,
            "corrected_stale_props": binding_changes,
        })
        timing_manifest = self.run_dir / "final" / f"timing-manifest-{locale}.json"
        write_json(timing_manifest, final_design["props"])
        info = probe_video(output)
        expected = self.config["output"]
        similarity = bgm_similarity_in_cta(
            output,
            self.artifact("bgm"),
            float(self.config["assets"]["logo_cta_excerpt_seconds"]),
        )
        final_checks = {
            "dimensions": is_vertical_resolution_acceptable(info, expected),
            "codec": info["codec"] == "h264",
            "duration": (
                float(expected["minimum_duration_seconds"]) - 0.1
                <= info["duration"]
                <= float(expected["duration_seconds"]) + 0.1
            ),
            "audio": info["has_audio"],
            "continuous_bgm_through_cta": similarity >= 0.55,
            "size": info["bytes"] <= 50 * 1024 * 1024,
        }
        if not all(final_checks.values()):
            failed = ", ".join(name for name, passed in final_checks.items() if not passed)
            raise AdCreatorError(f"Generated final failed preflight and must be rerolled: {failed}")
        self.add_artifact(
            f"final-{locale}",
            output,
            response_id=result.get("response_id"),
            model=MODELS[min(attempt - 1, 2)],
            source_audio_muted=True,
            cta_source_audio_muted=True,
            continuous_bgm_sha256=sha256(self.artifact("bgm")),
            composition_engine="makaron-agent-remotion",
            tts_engine="seed-audio",
            timing_manifest=str(timing_manifest.resolve()),
            composition_contract_version=2,
            asset_binding_manifest=str(binding_manifest.resolve()),
            stale_project_assets_corrected=binding_changes,
            render_fallback=result.get("render_fallback"),
        )

    def _qc(self) -> None:
        expected = self.config["output"]
        bgm_info = probe_audio(self.artifact("bgm"))
        hook_item = self.state["nodes"]["hook"]["artifacts"][0]
        result_item = self.state["nodes"]["result"]["artifacts"][0]
        same_effect_source = bool(
            hook_item.get("source_effect_sha256")
            and hook_item.get("source_effect_sha256") == result_item.get("source_effect_sha256")
        )
        hook_end = float(hook_item.get("start_seconds", -1)) + float(hook_item.get("duration_seconds", -1))
        result_start = float(result_item.get("start_seconds", -1))
        non_overlapping = hook_end <= result_start and float(hook_item.get("start_seconds", -1)) >= 0
        if not same_effect_source or not non_overlapping:
            raise AdCreatorError("Hook/Result provenance must prove non-overlapping ranges from one Effect source")
        report: dict[str, Any] = {
            "status": "PASS",
            "effect_segments": {
                "same_source_sha256": hook_item["source_effect_sha256"],
                "hook": {"start_seconds": hook_item["start_seconds"], "duration_seconds": hook_item["duration_seconds"]},
                "result": {"start_seconds": result_item["start_seconds"], "duration_seconds": result_item["duration_seconds"]},
                "non_overlapping": True,
            },
            "audio_mix": {
                "bgm": bgm_info,
                "same_bgm_for_all_locales": True,
                "looped_from_start_through_cta": True,
                "source_audio_muted": True,
                "cta_source_audio_muted": True,
                "bgm_volume": float(self.config["audio"]["bgm_volume"]),
            },
            "locales": {},
        }
        for locale in ad_locales(self.config):
            final_path = self.artifact(f"final-{locale}", ".mp4")
            final_item = self.state["nodes"][f"final-{locale}"]["artifacts"][0]
            timing_manifest_path = Path(str(final_item.get("timing_manifest", "")))
            timing_contract_valid = False
            if timing_manifest_path.is_file():
                try:
                    validate_timing_manifest(read_json(timing_manifest_path))
                    timing_contract_valid = True
                except AdCreatorError:
                    timing_contract_valid = False
            info = probe_video(final_path)
            bgm_similarity = bgm_similarity_in_cta(
                final_path,
                self.artifact("bgm"),
                float(self.config["assets"]["logo_cta_excerpt_seconds"]),
            )
            checks = {
                "dimensions": is_vertical_resolution_acceptable(info, expected),
                "codec": info["codec"] == "h264",
                "duration": (
                    float(expected["minimum_duration_seconds"]) - 0.1
                    <= info["duration"]
                    <= float(expected["duration_seconds"]) + 0.1
                ),
                "audio": info["has_audio"],
                "continuous_bgm_through_cta": bgm_similarity >= 0.55,
                "scene_bound_caption_contract": timing_contract_valid,
                "size": info["bytes"] <= 50 * 1024 * 1024,
            }
            info["bgm_cta_similarity"] = bgm_similarity
            info["checks"] = checks
            info["pass"] = all(checks.values())
            report["locales"][locale] = info
            if not info["pass"]:
                report["status"] = "BLOCKED"
        output = self.run_dir / "qc_report.json"
        write_json(output, report)
        self.add_artifact("qc", output)
        if report["status"] != "PASS":
            raise AdCreatorError("Final technical QC failed; inspect qc_report.json")

    def _deliver(self) -> None:
        delivery = self.campaign_dir / "deliverables"
        delivery.mkdir(parents=True, exist_ok=True)
        delivered: list[dict[str, Any]] = []
        for locale in ad_locales(self.config):
            source = self.artifact(f"final-{locale}", ".mp4")
            target = delivery / source.name
            shutil.copy2(source, target)
            final_item = self.state["nodes"][f"final-{locale}"]["artifacts"][0]
            timing_source = Path(final_item["timing_manifest"])
            timing_target = delivery / f"timing-manifest-{locale}.json"
            shutil.copy2(timing_source, timing_target)
            binding_source = Path(final_item["asset_binding_manifest"])
            binding_target = delivery / f"asset-bindings-{locale}.json"
            shutil.copy2(binding_source, binding_target)
            delivered.append({"locale": locale, "path": str(target.resolve()), "sha256": sha256(target), "timing_manifest": str(timing_target.resolve()), "asset_binding_manifest": str(binding_target.resolve())})
        bgm_source = self.artifact("bgm")
        bgm_target = delivery / ("bgm-source" + bgm_source.suffix.lower())
        shutil.copy2(bgm_source, bgm_target)
        provenance = {
            "campaign_id": self.config["campaign_id"],
            "skill_id": self.config["target_skill"]["id"],
            "project_id": self.config["project_binding"]["project_id"],
            "input": {"path": self.config["input_image"], "sha256": sha256(Path(self.config["input_image"]))},
            "fixed_logo_cta": {
                "path": str(self._cta_input_path()),
                "master_path": self.config["assets"]["logo_cta"],
                "sha256": sha256(self._cta_input_path()),
                "start_seconds": self.config["assets"]["logo_cta_start_seconds"],
                "excerpt_seconds": self.config["assets"]["logo_cta_excerpt_seconds"],
                "source_audio_used": False,
            },
            "audio_mix": {
                "bgm_path": str(bgm_target.resolve()),
                "bgm_sha256": sha256(bgm_target),
                "bgm_volume": self.config["audio"]["bgm_volume"],
                "same_bgm_looped_across_full_video": True,
                "source_video_audio_muted": True,
                "cta_source_audio_muted": True,
                "tts_source": "seed-audio inside project-bound Remotion final generation",
            },
            "deliverables": delivered,
            "node_lineage": self.state["nodes"],
            "publication_status": "HUMAN_APPROVAL_REQUIRED",
        }
        output = delivery / "provenance.json"
        write_json(output, provenance)
        prompt_sections: list[str] = []
        prompt_dir = self.run_dir / "prompts"
        if prompt_dir.is_dir():
            for prompt_file in sorted(prompt_dir.glob("*.txt")):
                prompt_sections.append(f"## {prompt_file.stem}\n\n```text\n{prompt_file.read_text(encoding='utf-8').rstrip()}\n```\n")
        (delivery / "prompt_used.md").write_text("# Prompt lineage\n\n" + "\n".join(prompt_sections), encoding="utf-8")
        qc = read_json(self.artifact("qc"))
        qc_lines = ["# QC report", "", f"Overall: **{qc['status']}**", ""]
        for locale, info in qc["locales"].items():
            qc_lines += [f"## {locale}", "", f"- Technical pass: {info['pass']}", f"- Size: {info['width']}×{info['height']}", f"- Duration: {info['duration']:.3f}s", f"- Audio: {info['has_audio']}", f"- Same BGM through CTA: {info['checks']['continuous_bgm_through_cta']} (similarity {info['bgm_cta_similarity']:.3f})", ""]
        (delivery / "qc_report.md").write_text("\n".join(qc_lines), encoding="utf-8")
        shutil.copy2(self.campaign_dir / "plan.json", delivery / "plan.json")
        shutil.copy2(self.campaign_dir / "project-binding.json", delivery / "project-binding.json")
        shutil.copy2(self.artifact("scripts"), delivery / "scripts.json")
        review_rows = ["locale,technical_status,human_creative_review,publication_status"]
        review_rows.extend(f"{locale},PASS,PENDING,PAUSED" for locale in ad_locales(self.config))
        (delivery / "review.csv").write_text("\n".join(review_rows) + "\n", encoding="utf-8")
        write_json(delivery / "performance-plan.json", {
            "metrics": ["spend", "impressions", "three_second_views", "clicks", "installs", "ctr", "cpc"],
            "dimensions": ["campaign_id", "skill_id", "locale", "creative_variant", "prompt_hash"],
            "rule": "Do not declare a winner until delivery volume is comparable and sufficient.",
        })
        review = delivery / "review.md"
        review.write_text(
            "# Human publication gate\n\nTechnical generation passed. Review identity, claims, locale naturalness, subtitle timing, and platform policy before publishing. Do not auto-activate ads.\n",
            encoding="utf-8",
        )
        self.add_artifact("deliver", output)

    def _write_agent_request(self, node: dict[str, Any]) -> None:
        node_id = node["id"]
        state = self.state["nodes"][node_id]
        maximum = int(self.config.get("automation", {}).get("max_attempts", 3))
        if state["attempts"] >= maximum:
            state["status"] = "BLOCKED"
            state["last_error"] = "Agent generation budget exhausted"
            return
        state["attempts"] += 1
        model_preference = MODELS[min(state["attempts"] - 1, len(MODELS) - 1)]
        request: dict[str, Any] = {
            "version": 1,
            "campaign_id": self.config["campaign_id"],
            "node_id": node_id,
            "project_id": self.config["project_binding"]["project_id"],
            "skill_id": self.config["target_skill"]["id"],
            "must_use_bound_project": node_id != "bgm",
            "attempt": state["attempts"],
            "model_preference": model_preference,
            "forbidden": ["--project auto", "standalone makaron edit", "standalone makaron video create"],
        }
        if node_id == "scripts":
            request.update({"operation": "generate_json", "prompt": script_prompt(self.config), "expected": "scripts.json"})
        elif node_id == "before":
            request.update({"operation": "generate_image", "prompt": before_prompt(self.config), "images": [self.config["input_image"]], "expected": "before.png"})
        elif node_id == "effect":
            request.update({"operation": "invoke_skill_video", "prompt": effect_prompt(self.config, model_preference), "images": [self.config["input_image"]], "target_skill_id": self.config["target_skill"]["id"], "expected": "effect.mp4", "minimum_resolution": "720x1280"})
        elif node_id == "after":
            request.update({
                "operation": "select_exact_effect_keyframe",
                "prompt": after_prompt(self.config),
                "videos": [str(self.artifact("effect", ".mp4"))],
                "selection_rule": "analyze full clip and export the strongest exact decoded source frame; never regenerate",
                "expected": "after.png",
            })
        elif node_id == "comparison":
            request.update({
                "operation": "compose_comparison_in_makaron",
                "prompt": comparison_prompt(self.config),
                "images": [str(self.artifact("before")), str(self.artifact("after"))],
                "input_roles": ["locked_before", "locked_exact_effect_keyframe"],
                "expected": "comparison.png",
            })
        elif node_id == "bgm":
            request.update({
                "operation": "generate_instrumental_bgm",
                "prompt": bgm_prompt(self.config),
                "style": self.config["audio"]["bgm_style"],
                "command_contract": "makaron music create --style <style> <prompt>",
                "instrumental_only": True,
                "shared_across_selected_locales": True,
                "expected": "bgm.mp3",
            })
        elif node_id.startswith("final-"):
            locale = node_id.split("-", 1)[1]
            scripts = read_json(self.artifact("scripts"))
            videos = self._final_video_inputs(locale)
            request.update({
                "operation": "assemble_localized_ad",
                "locale": locale,
                "prompt": final_prompt(self.config, locale, scripts, model_preference),
                "images": [self._final_image_input("comparison", self.artifact("comparison"), role="comparison")],
                "videos": videos,
                "audios": [self._bgm_input()],
                "input_roles": {
                    "images": ["before_after_comparison"],
                    "videos": ["effect_derived_hook", "non_overlapping_effect_result", "localized_v5_workflow", "fixed_logo_cta"],
                    "audios": ["campaign_bgm"],
                },
                "composition": {
                    "engine": "makaron-agent-remotion",
                    "builder_skill_id": self.config.get("automation", {}).get("builder_skill_id", "tiktok-video"),
                    "one_project_bound_chat": True,
                    "tts_engine": "seed-audio",
                    "caption_format": "remotion-caption-json",
                    "caption_fields": ["text", "startMs", "endMs", "timestampMs", "confidence"],
                    "scene_bound_caption_timing": True,
                    "maximum_caption_audio_drift_ms": 150,
                    "subtitles_burned_in": True,
                    "subtitle_style": {"color": "white", "stroke": "black", "background": "none", "max_lines": 2, "max_characters_per_line": 20},
                    "safe_zone": self.config["output"]["safe_zone"],
                    "hook_and_result_must_be_distinct": True,
                    "hook_and_result_share_exact_effect_source": True,
                    "all_source_video_audio_muted": True,
                    "cta_source_audio_muted": True,
                    "bgm_volume": self.config["audio"]["bgm_volume"],
                    "same_bgm_looped_across_full_video": True,
                    "local_ffmpeg_audio_or_subtitle_postprocess": False,
                },
                "expected": f"final-artifact-{locale}.mp4",
                "expected_timing_manifest": f"timing-manifest-{locale}.json",
            })
        else:
            raise AdCreatorError(f"Agent request is not supported for {node_id}")
        path = self.run_dir / "requests" / f"{node_id}.json"
        write_json(path, request)
        prompt_path = self.run_dir / "prompts" / f"{node_id}.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(str(request["prompt"]).rstrip() + "\n", encoding="utf-8")
        state["status"] = "WAITING_FOR_AGENT"
        state["request"] = str(path)

    def complete_agent_node(
        self,
        node_id: str,
        artifact: Path,
        response_id: str | None = None,
        source_url: str | None = None,
        timing_manifest: Path | None = None,
    ) -> None:
        if node_id not in self.state["nodes"]:
            raise AdCreatorError(f"Unknown node: {node_id}")
        state = self.state["nodes"][node_id]
        if state["status"] != "WAITING_FOR_AGENT":
            raise AdCreatorError(f"Node {node_id} is not waiting for an agent")
        artifact = artifact.resolve()
        if not artifact.is_file():
            raise AdCreatorError(f"Artifact not found: {artifact}")
        if node_id == "scripts":
            scripts = read_json(artifact)
            self._validate_scripts(scripts)
        elif node_id in {"hook", "effect"} or node_id.startswith("workflow-") or node_id.startswith("final-"):
            if artifact.suffix.lower() != ".mp4":
                raise AdCreatorError(f"{node_id} requires an MP4 artifact")
            if node_id.startswith("final-"):
                if not timing_manifest:
                    raise AdCreatorError(f"{node_id} requires a Remotion timing manifest sidecar")
                timing_manifest = timing_manifest.resolve()
                if not timing_manifest.is_file():
                    raise AdCreatorError(f"Timing manifest not found: {timing_manifest}")
                validate_timing_manifest(read_json(timing_manifest))
        elif node_id == "bgm":
            if artifact.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac"}:
                raise AdCreatorError("bgm requires an MP3/WAV/M4A/AAC artifact")
            probe_audio(artifact)
        elif node_id in {"before", "after", "comparison"} and artifact.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise AdCreatorError(f"{node_id} requires an image artifact")
        if node_id == "scripts":
            destination = self.run_dir / "scripts.json"
        elif node_id == "before":
            destination = self.run_dir / "assets" / ("before" + artifact.suffix.lower())
        elif node_id == "hook":
            destination = self.run_dir / "assets" / "hook.mp4"
        elif node_id == "effect":
            destination = self.run_dir / "assets" / "effect.mp4"
        elif node_id == "after":
            destination = self.run_dir / "assets" / ("after" + artifact.suffix.lower())
        elif node_id == "comparison":
            destination = self.run_dir / "assets" / ("comparison" + artifact.suffix.lower())
        elif node_id.startswith("workflow-"):
            locale = node_id.split("-", 1)[1]
            destination = self.run_dir / "workflow" / f"workflow-{locale}.mp4"
        elif node_id == "bgm":
            destination = self.run_dir / "assets" / ("bgm" + artifact.suffix.lower())
        elif node_id.startswith("final-"):
            locale = node_id.split("-", 1)[1]
            destination = self.run_dir / "final" / f"final-artifact-{locale}.mp4"
        else:
            raise AdCreatorError(f"Unsupported completed Agent node: {node_id}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if artifact != destination.resolve():
            shutil.copy2(artifact, destination)
        metadata: dict[str, Any] = {"response_id": response_id}
        if node_id.startswith("final-") and timing_manifest:
            locale = node_id.split("-", 1)[1]
            manifest_destination = self.run_dir / "final" / f"timing-manifest-{locale}.json"
            manifest_destination.parent.mkdir(parents=True, exist_ok=True)
            if timing_manifest != manifest_destination.resolve():
                shutil.copy2(timing_manifest, manifest_destination)
            metadata["timing_manifest"] = str(manifest_destination.resolve())
            metadata["composition_contract_version"] = 2
        if (node_id == "bgm" or node_id in {"hook", "effect"} or node_id.startswith("workflow-")) and source_url:
            if not source_url.startswith(("https://", "http://")):
                raise AdCreatorError(f"{node_id} source_url must use HTTP or HTTPS")
            metadata["source_url"] = source_url
        self.add_artifact(node_id, destination, **metadata)
        state["status"] = "PASS"
        state["completed_at"] = now()
        self.state["status"] = "RUNNING"
        self.save()

    def fail_agent_node(self, node_id: str, error: str) -> None:
        if node_id not in self.state["nodes"]:
            raise AdCreatorError(f"Unknown node: {node_id}")
        state = self.state["nodes"][node_id]
        if state["status"] != "WAITING_FOR_AGENT":
            raise AdCreatorError(f"Node {node_id} is not waiting for an agent")
        maximum = int(self.config.get("automation", {}).get("max_attempts", 3))
        state["last_error"] = error
        state["status"] = "BLOCKED" if state["attempts"] >= maximum else "PENDING"
        self.state["status"] = state["status"]
        self.save()
