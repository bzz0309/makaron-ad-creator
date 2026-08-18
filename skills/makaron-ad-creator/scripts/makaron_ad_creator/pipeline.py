from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapter import MakaronAdapter, extract_json_object
from .media import compose_comparison, extract_after_frame, probe_video
from .prompts import before_prompt, effect_prompt, final_prompt, script_prompt
from .schema import validate_config
from .util import AdCreatorError, json_candidates, read_json, run, sha256, write_json


MODELS = ["seedance-fast", "kling", "grok"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def plan_for(config: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [
        {"id": "validate", "kind": "local", "depends_on": []},
        {"id": "scripts", "kind": "generate_json", "depends_on": ["validate"]},
        {"id": "before", "kind": "generate_image", "depends_on": ["validate"]},
        {"id": "effect", "kind": "generate_video", "depends_on": ["validate"]},
        {"id": "after", "kind": "local", "depends_on": ["effect"]},
        {"id": "comparison", "kind": "local", "depends_on": ["before", "after"]},
        {"id": "workflow", "kind": "local", "depends_on": ["validate"]},
    ]
    for locale in ("en", "ja", "yue"):
        nodes.append({
            "id": f"final-{locale}",
            "kind": "generate_video",
            "depends_on": ["scripts", "comparison", "effect", "workflow"],
        })
    nodes += [
        {"id": "qc", "kind": "local", "depends_on": ["final-en", "final-ja", "final-yue"]},
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
        maximum = int(self.config.get("automation", {}).get("max_attempts", 3)) if node["kind"].startswith("generate_") or node["id"] == "workflow" else 1
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
        elif node_id == "effect":
            self._generate_effect(attempt)
        elif node_id == "after":
            output = self.run_dir / "assets" / "after.png"
            extract_after_frame(self.artifact("effect", ".mp4"), output)
            self.add_artifact(node_id, output)
        elif node_id == "comparison":
            output = self.run_dir / "assets" / "comparison.png"
            compose_comparison(self.artifact("before"), self.artifact("after"), output)
            self.add_artifact(node_id, output)
        elif node_id == "workflow":
            self._generate_workflow()
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
        scripts = extract_json_object(result["response"])
        self._validate_scripts(scripts)
        output = self.run_dir / "scripts.json"
        write_json(output, scripts)
        self.add_artifact("scripts", output, response_id=result.get("response_id"))

    def _validate_scripts(self, scripts: dict[str, Any]) -> None:
        for locale in ("en", "ja", "yue"):
            lines = scripts.get(locale)
            if not isinstance(lines, list) or len(lines) != 5 or not all(isinstance(line, str) and line.strip() for line in lines):
                raise AdCreatorError(f"scripts.{locale} must contain exactly five non-empty strings")

    def _generate_before(self) -> None:
        output = self.run_dir / "assets" / "before.png"
        result = self._adapter().chat(
            node_id="before", prompt=before_prompt(self.config), images=[Path(self.config["input_image"])], destination=output
        )
        self.add_artifact("before", output, response_id=result.get("response_id"))

    def _generate_effect(self, attempt: int) -> None:
        output = self.run_dir / "assets" / "effect.mp4"
        result = self._adapter().chat(
            node_id="effect",
            prompt=effect_prompt(self.config, MODELS[min(attempt - 1, len(MODELS) - 1)]),
            skill_id=self.config["target_skill"]["id"],
            images=[Path(self.config["input_image"])],
            destination=output,
        )
        self.add_artifact("effect", output, response_id=result.get("response_id"), model=MODELS[min(attempt - 1, 2)])

    def _generate_workflow(self) -> None:
        main_skill_dir = Path(__file__).resolve().parents[2]
        script = main_skill_dir.parent / "edit-makaron-app-workflow-recording" / "scripts" / "workflow_recording.py"
        output_dir = self.run_dir / "workflow"
        command = [
            "python3", str(script), "synthesize", "--skill", self.config["target_skill"]["id"],
            "--locales", "en,ja,zh-Hant", "--output-dir", str(output_dir),
        ]
        if self.config.get("catalog_json"):
            command += ["--catalog-json", self.config["catalog_json"]]
        result = run(command, timeout=1800)
        candidates = [value for value in json_candidates(result.stdout) if isinstance(value, dict)]
        if not candidates:
            raise AdCreatorError("Synthetic workflow returned no JSON result")
        parsed = candidates[-1]
        outputs = parsed.get("outputs", [])
        if len(outputs) != 3:
            raise AdCreatorError("Synthetic workflow did not return all three UI locales")
        manifest = Path(parsed["manifest"])
        artifact = self.add_artifact("workflow", manifest)
        artifact["locale_outputs"] = {item["locale"]: item["output"] for item in outputs}

    def _workflow_for(self, ad_locale: str) -> Path:
        ui_locale = {"en": "en", "ja": "ja", "yue": "zh-Hant"}[ad_locale]
        item = self.state["nodes"]["workflow"]["artifacts"][0]
        path = Path(item["locale_outputs"][ui_locale])
        if not path.is_file():
            raise AdCreatorError(f"Missing workflow video for {ui_locale}")
        return path

    def _generate_final(self, locale: str, attempt: int) -> None:
        scripts = read_json(self.artifact("scripts"))
        output = self.run_dir / "final" / f"final-artifact-{locale}.mp4"
        videos = [self.artifact("effect", ".mp4"), self._workflow_for(locale)]
        if self.config.get("assets", {}).get("logo_cta"):
            videos.append(Path(self.config["assets"]["logo_cta"]))
        result = self._adapter().chat(
            node_id=f"final-{locale}",
            prompt=final_prompt(self.config, locale, scripts, MODELS[min(attempt - 1, len(MODELS) - 1)]),
            skill_id=self.config.get("automation", {}).get("builder_skill_id") or None,
            images=[self.artifact("comparison")],
            videos=videos,
            destination=output,
        )
        self.add_artifact(f"final-{locale}", output, response_id=result.get("response_id"), model=MODELS[min(attempt - 1, 2)])

    def _qc(self) -> None:
        expected = self.config["output"]
        report: dict[str, Any] = {"status": "PASS", "locales": {}}
        for locale in ("en", "ja", "yue"):
            info = probe_video(self.artifact(f"final-{locale}", ".mp4"))
            checks = {
                "dimensions": info["width"] == expected["width"] and info["height"] == expected["height"],
                "codec": info["codec"] == "h264",
                "duration": 0 < info["duration"] <= float(expected["duration_seconds"]) + 0.1,
                "audio": info["has_audio"],
                "size": info["bytes"] <= 50 * 1024 * 1024,
            }
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
        for locale in ("en", "ja", "yue"):
            source = self.artifact(f"final-{locale}", ".mp4")
            target = delivery / source.name
            shutil.copy2(source, target)
            delivered.append({"locale": locale, "path": str(target.resolve()), "sha256": sha256(target)})
        provenance = {
            "campaign_id": self.config["campaign_id"],
            "skill_id": self.config["target_skill"]["id"],
            "project_id": self.config["project_binding"]["project_id"],
            "input": {"path": self.config["input_image"], "sha256": sha256(Path(self.config["input_image"]))},
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
            qc_lines += [f"## {locale}", "", f"- Technical pass: {info['pass']}", f"- Size: {info['width']}×{info['height']}", f"- Duration: {info['duration']:.3f}s", f"- Audio: {info['has_audio']}", ""]
        (delivery / "qc_report.md").write_text("\n".join(qc_lines), encoding="utf-8")
        shutil.copy2(self.campaign_dir / "plan.json", delivery / "plan.json")
        shutil.copy2(self.campaign_dir / "project-binding.json", delivery / "project-binding.json")
        shutil.copy2(self.artifact("scripts"), delivery / "scripts.json")
        (delivery / "review.csv").write_text(
            "locale,technical_status,human_creative_review,publication_status\n"
            "en,PASS,PENDING,PAUSED\n"
            "ja,PASS,PENDING,PAUSED\n"
            "yue,PASS,PENDING,PAUSED\n",
            encoding="utf-8",
        )
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
            "must_use_bound_project": True,
            "attempt": state["attempts"],
            "model_preference": model_preference,
            "forbidden": ["--project auto", "standalone makaron edit", "standalone makaron video create"],
        }
        if node_id == "scripts":
            request.update({"operation": "generate_json", "prompt": script_prompt(self.config), "expected": "scripts.json"})
        elif node_id == "before":
            request.update({"operation": "generate_image", "prompt": before_prompt(self.config), "images": [self.config["input_image"]], "expected": "before.png"})
        elif node_id == "effect":
            request.update({"operation": "invoke_skill_video", "prompt": effect_prompt(self.config, model_preference), "images": [self.config["input_image"]], "target_skill_id": self.config["target_skill"]["id"], "expected": "effect.mp4"})
        elif node_id.startswith("final-"):
            locale = node_id.split("-", 1)[1]
            scripts = read_json(self.artifact("scripts"))
            videos = [str(self.artifact("effect", ".mp4")), str(self._workflow_for(locale))]
            if self.config.get("assets", {}).get("logo_cta"):
                videos.append(self.config["assets"]["logo_cta"])
            request.update({
                "operation": "assemble_localized_ad",
                "locale": locale,
                "prompt": final_prompt(self.config, locale, scripts, model_preference),
                "images": [str(self.artifact("comparison"))],
                "videos": videos,
                "expected": f"final-artifact-{locale}.mp4",
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

    def complete_agent_node(self, node_id: str, artifact: Path, response_id: str | None = None) -> None:
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
        elif node_id in {"effect", "final-en", "final-ja", "final-yue"}:
            if artifact.suffix.lower() != ".mp4":
                raise AdCreatorError(f"{node_id} requires an MP4 artifact")
        elif node_id == "before" and artifact.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise AdCreatorError("before requires an image artifact")
        if node_id == "scripts":
            destination = self.run_dir / "scripts.json"
        elif node_id == "before":
            destination = self.run_dir / "assets" / ("before" + artifact.suffix.lower())
        elif node_id == "effect":
            destination = self.run_dir / "assets" / "effect.mp4"
        else:
            locale = node_id.split("-", 1)[1]
            destination = self.run_dir / "final" / f"final-artifact-{locale}.mp4"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if artifact != destination.resolve():
            shutil.copy2(artifact, destination)
        self.add_artifact(node_id, destination, response_id=response_id)
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
