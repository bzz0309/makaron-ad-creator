from __future__ import annotations

import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

from .util import (
    AdCreatorError,
    download,
    extract_media_urls,
    extract_response_id,
    json_candidates,
    require_binary,
    run,
    walk,
    write_json,
)


class MakaronAdapter:
    def __init__(self, project_id: str, run_dir: Path, binary: str = "makaron") -> None:
        if not project_id or project_id == "auto":
            raise AdCreatorError("A non-auto persistent Makaron project_id is required")
        self.binary = require_binary(binary)
        self.project_id = project_id
        self.run_dir = run_dir
        self.command_log = run_dir / "commands.jsonl"

    def _log(self, node_id: str, command: list[str]) -> None:
        safe = []
        skip_next = False
        for index, token in enumerate(command):
            if skip_next:
                safe.append("<prompt>")
                skip_next = False
            elif token in {"-b", "--brief", "--prompt"}:
                safe.append(token)
                skip_next = True
            else:
                safe.append(token)
        self.command_log.parent.mkdir(parents=True, exist_ok=True)
        with self.command_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"node_id": node_id, "command": safe}, ensure_ascii=False) + "\n")

    def chat(
        self,
        *,
        node_id: str,
        prompt: str,
        destination: Path | None = None,
        skill_id: str | None = None,
        images: list[Path] | None = None,
        videos: list[Path] | None = None,
        audios: list[Path | str] | None = None,
        require_generated_video: bool = False,
        require_generated_image: bool = False,
        allow_remotion_fallback: bool = True,
    ) -> dict[str, Any]:
        if require_generated_video and require_generated_image:
            raise AdCreatorError("A chat output cannot require both a generated video and generated image")
        prompt_path = self.run_dir / "prompts" / f"{node_id}.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt.rstrip() + "\n", encoding="utf-8")
        command = [self.binary, "chat", "--project", self.project_id]
        if skill_id:
            command += ["--skill", skill_id]
        for image in images or []:
            command += ["--image", str(image)]
        for video in videos or []:
            command += ["--video", str(video)]
        for audio in audios or []:
            command += ["--audio", str(audio)]
        command += ["--json", "-b", prompt]
        self._log(node_id, command)
        result = run(command, timeout=1800)
        values = list(json_candidates(result.stdout))
        raw: Any = values[-1] if values else {"text": result.stdout}
        response_id = extract_response_id(raw)
        urls = extract_media_urls(raw)
        generated_video_urls = extract_generated_video_urls(raw)
        generated_image_urls = extract_generated_image_urls(raw)
        needs_materialized_response = (
            not urls
            or (require_generated_video and not generated_video_urls and not extract_remotion_design(raw))
            or (require_generated_image and not generated_image_urls)
        )
        if response_id and needs_materialized_response:
            required_kind = "video" if require_generated_video else "image" if require_generated_image else None
            raw, urls = self._materialize(node_id, response_id, raw, required_kind=required_kind)
        response_path = self.run_dir / "responses" / f"{node_id}.json"
        write_json(response_path, {"response_id": response_id, "media_urls": urls, "response": raw})
        if destination:
            if require_generated_video:
                downloadable = extract_generated_video_urls(raw)
            elif require_generated_image:
                downloadable = extract_generated_image_urls(raw)
            else:
                downloadable = urls
            if not downloadable:
                if require_generated_video and allow_remotion_fallback:
                    fallback = self.render_remotion_fallback(node_id, raw, destination)
                    return {
                        "response_id": response_id,
                        "media_urls": urls,
                        "response": raw,
                        "response_path": str(response_path),
                        "render_fallback": fallback,
                    }
                media_label = "generated video" if require_generated_video else "generated image" if require_generated_image else "downloadable media"
                raise AdCreatorError(f"Makaron returned no {media_label} for {node_id}; response_id={response_id or 'unknown'}")
            expected_video = destination.suffix.lower() in {".mp4", ".mov", ".m4v"}
            matching = []
            for url in downloadable:
                suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
                is_video = suffix in {".mp4", ".mov", ".m4v", ".webm"} or "video" in url.lower()
                if is_video == expected_video:
                    matching.append(url)
            download((matching or downloadable)[0], destination)
        return {"response_id": response_id, "media_urls": urls, "response": raw, "response_path": str(response_path)}

    def render_remotion_fallback(self, node_id: str, response: Any, destination: Path) -> dict[str, Any]:
        design = extract_remotion_design(response)
        if not design:
            raise AdCreatorError(
                f"Makaron returned no exported final MP4 or reusable Remotion design for {node_id}; "
                "attached source videos are not final artifacts"
            )
        validate_ad_remotion_design(design)
        design_path = self.run_dir / "responses" / f"{node_id}.remotion-design.json"
        write_json(design_path, design)
        script = Path(__file__).resolve().parents[1] / "remotion_fallback" / "render.mjs"
        if not script.is_file():
            raise AdCreatorError(f"Bundled Remotion fallback renderer is missing: {script}")
        node = require_binary("node")
        run([node, str(script), str(design_path), str(destination)], timeout=3600)
        if not destination.is_file() or destination.stat().st_size == 0:
            raise AdCreatorError("Local Remotion fallback did not create a non-empty final MP4")
        return {
            "engine": "local-remotion-from-makaron-design",
            "design_path": str(design_path),
            "snapshot_id": design.get("snapshotId") or design.get("snapshot_id"),
        }

    def create_music(
        self,
        *,
        node_id: str,
        prompt: str,
        style: str,
        destination: Path,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        """Generate one standalone instrumental track with `makaron music create` and poll it."""
        prompt_path = self.run_dir / "prompts" / f"{node_id}.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt.rstrip() + "\n", encoding="utf-8")
        command = [self.binary, "music", "create"]
        if style:
            command += ["--style", style]
        command.append(prompt)
        self._log(node_id, [self.binary, "music", "create", "--style", style, "--prompt", prompt])
        submitted = run(command, timeout=180)
        values = list(json_candidates(submitted.stdout))
        raw: Any = values[-1] if values else {"text": submitted.stdout}
        task_id = extract_response_id(raw)
        urls = extract_media_urls(raw)
        status_raw: Any = raw
        deadline = time.monotonic() + timeout_seconds
        while not urls and task_id and time.monotonic() < deadline:
            time.sleep(5)
            status_command = [self.binary, "music", "status", task_id]
            self._log(node_id + "-poll", status_command)
            status_result = run(status_command, timeout=90)
            candidates = list(json_candidates(status_result.stdout))
            status_raw = candidates[-1] if candidates else {"text": status_result.stdout}
            urls = extract_media_urls(status_raw)
            lowered = json.dumps(status_raw, ensure_ascii=False).lower()
            if not urls and any(token in lowered for token in ('"status":"failed"', '"status": "failed"', "music failed")):
                raise AdCreatorError(f"Makaron music generation failed: task_id={task_id}")
        if not urls:
            raise AdCreatorError(
                "Makaron music generation returned no downloadable audio "
                f"before timeout; task_id={task_id or 'unknown'}"
            )
        audio_urls = []
        for url in urls:
            suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
            if suffix in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"} or "audio" in url.lower() or "music" in url.lower():
                audio_urls.append(url)
        source_url = (audio_urls or urls)[0]
        download(source_url, destination)
        response_path = self.run_dir / "responses" / f"{node_id}.json"
        write_json(response_path, {
            "task_id": task_id,
            "media_urls": urls,
            "submitted": raw,
            "completed": status_raw,
        })
        return {
            "response_id": task_id,
            "media_urls": urls,
            "source_url": source_url,
            "response": status_raw,
            "response_path": str(response_path),
        }

    def _materialize(
        self,
        node_id: str,
        response_id: str,
        fallback: Any,
        *,
        required_kind: str | None = None,
    ) -> tuple[Any, list[str]]:
        attempts = [
            [self.binary, "responses", "get", response_id, "--wait", "--materialize", "--json"],
            [self.binary, "responses", "get", response_id, "--wait", "--json"],
            [self.binary, "responses", "get", response_id, "--json"],
        ]
        last = fallback
        for command in attempts:
            self._log(node_id + "-poll", command)
            try:
                result = run(command, timeout=1800)
            except AdCreatorError:
                continue
            values = list(json_candidates(result.stdout))
            last = values[-1] if values else {"text": result.stdout}
            urls = extract_media_urls(last)
            generated = (
                extract_generated_video_urls(last)
                if required_kind == "video"
                else extract_generated_image_urls(last)
                if required_kind == "image"
                else urls
            )
            if generated or (required_kind == "video" and extract_remotion_design(last)):
                return last, urls
        return last, []


def extract_generated_video_urls(response: Any) -> list[str]:
    """Return only videos produced by the response, never uploaded source attachments."""
    found: list[str] = []
    roots = [response]
    if isinstance(response, dict) and isinstance(response.get("response"), dict):
        roots.append(response["response"])

    def add(candidate: Any) -> None:
        if not isinstance(candidate, str) or not candidate.startswith(("https://", "http://")):
            return
        suffix = Path(urllib.parse.urlparse(candidate).path).suffix.lower()
        if suffix not in {".mp4", ".mov", ".m4v", ".webm"} and "video" not in candidate.lower():
            return
        if candidate not in found:
            found.append(candidate)

    for root in roots:
        if not isinstance(root, dict):
            continue
        for item in root.get("output", []) if isinstance(root.get("output"), list) else []:
            if isinstance(item, dict) and str(item.get("type", "")).lower() == "video":
                add(item.get("url") or item.get("videoUrl") or item.get("video_url"))
        result = root.get("result")
        if isinstance(result, dict):
            for item in result.get("videos", []) if isinstance(result.get("videos"), list) else []:
                if isinstance(item, dict):
                    add(item.get("videoUrl") or item.get("video_url") or item.get("url"))
                else:
                    add(item)
        for item in root.get("videos", []) if isinstance(root.get("videos"), list) else []:
            if isinstance(item, dict):
                add(item.get("videoUrl") or item.get("video_url") or item.get("url"))
            else:
                add(item)
    return found


def extract_generated_image_urls(response: Any) -> list[str]:
    """Return only images produced by the response, never uploaded source attachments."""
    found: list[str] = []
    roots = [response]
    if isinstance(response, dict) and isinstance(response.get("response"), dict):
        roots.append(response["response"])

    def add(candidate: Any) -> None:
        if not isinstance(candidate, str) or not candidate.startswith(("https://", "http://")):
            return
        suffix = Path(urllib.parse.urlparse(candidate).path).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".avif"} and "image" not in candidate.lower():
            return
        if candidate not in found:
            found.append(candidate)

    for root in roots:
        if not isinstance(root, dict):
            continue
        for item in root.get("output", []) if isinstance(root.get("output"), list) else []:
            if isinstance(item, dict) and str(item.get("type", "")).lower() == "image":
                add(item.get("url") or item.get("imageUrl") or item.get("image_url"))
        result = root.get("result")
        if isinstance(result, dict):
            for item in result.get("images", []) if isinstance(result.get("images"), list) else []:
                if isinstance(item, dict):
                    add(item.get("imageUrl") or item.get("image_url") or item.get("url"))
                else:
                    add(item)
        for item in root.get("images", []) if isinstance(root.get("images"), list) else []:
            if isinstance(item, dict):
                add(item.get("imageUrl") or item.get("image_url") or item.get("url"))
            else:
                add(item)
    return found


def extract_remotion_design(response: Any) -> dict[str, Any] | None:
    roots = [response]
    if isinstance(response, dict) and isinstance(response.get("response"), dict):
        roots.append(response["response"])
    for root in roots:
        if not isinstance(root, dict):
            continue
        result = root.get("result")
        designs = result.get("designs", []) if isinstance(result, dict) else []
        for design in designs if isinstance(designs, list) else []:
            if (
                isinstance(design, dict)
                and isinstance(design.get("code"), str)
                and isinstance(design.get("props"), dict)
                and isinstance(design.get("animation"), dict)
            ):
                return design
    return None


def validate_ad_remotion_design(design: dict[str, Any]) -> None:
    """Reject stale/hand-timed designs that predate the synchronized ad contract."""
    props = design.get("props")
    if not isinstance(props, dict):
        raise AdCreatorError("Remotion design is missing props")
    validate_timing_manifest(props)


def validate_timing_manifest(props: dict[str, Any]) -> None:
    """Validate the portable caption/scene sidecar used by Makaron and other Agents."""
    def numeric(value: Any, label: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise AdCreatorError(f"Remotion timing manifest has invalid {label}") from exc

    if numeric(props.get("compositionContractVersion", 0), "compositionContractVersion") < 2:
        raise AdCreatorError("Remotion design is missing compositionContractVersion 2")
    safe = props.get("safeZone")
    if not isinstance(safe, dict):
        raise AdCreatorError("Remotion timing manifest is missing the Meta safeZone")
    safe_minimums = {"topPx": 250, "bottomPx": 340, "leftPx": 90, "rightPx": 180, "captionTopPx": 250}
    for key, minimum in safe_minimums.items():
        if numeric(safe.get(key, 0), f"safeZone.{key}") < minimum:
            raise AdCreatorError(f"Remotion Meta safeZone.{key} must be at least {minimum}")
    maximum_characters = numeric(safe.get("maxCharactersPerLine", 0), "safeZone.maxCharactersPerLine")
    if maximum_characters != int(maximum_characters) or int(maximum_characters) not in range(1, 21):
        raise AdCreatorError("Remotion safeZone.maxCharactersPerLine must be between 1 and 20")
    captions = props.get("captions")
    if not isinstance(captions, list) or len(captions) != 5:
        raise AdCreatorError("Remotion design must contain exactly five timed Caption objects")
    for caption in captions:
        if not isinstance(caption, dict) or not all(key in caption for key in ("text", "startMs", "endMs", "timestampMs", "confidence")):
            raise AdCreatorError("Every Remotion caption requires text/startMs/endMs/timestampMs/confidence")
        if numeric(caption["endMs"], "caption.endMs") <= numeric(caption["startMs"], "caption.startMs"):
            raise AdCreatorError("Remotion caption timing must have endMs after startMs")
    scenes = props.get("scenes")
    required_scenes = ("hook", "comparison", "workflow", "result", "cta")
    if not isinstance(scenes, dict) or any(scene not in scenes for scene in required_scenes):
        raise AdCreatorError("Remotion design must contain all five scene timing ranges")
    for scene in required_scenes:
        timing = scenes[scene]
        if not isinstance(timing, dict) or numeric(timing.get("endMs", 0), f"scenes.{scene}.endMs") <= numeric(timing.get("startMs", -1), f"scenes.{scene}.startMs"):
            raise AdCreatorError(f"Remotion scene {scene} has invalid timing")
    expected_map = ["hook", "comparison", "workflow", "workflow", "result"]
    if props.get("lineSceneMap") != expected_map:
        raise AdCreatorError("Remotion lineSceneMap does not match the locked five-beat contract")
    for caption, scene_name in zip(captions, expected_map):
        scene = scenes[scene_name]
        if numeric(caption["startMs"], "caption.startMs") < numeric(scene["startMs"], f"scenes.{scene_name}.startMs") or numeric(caption["endMs"], "caption.endMs") > numeric(scene["endMs"], f"scenes.{scene_name}.endMs"):
            raise AdCreatorError(f"Caption crosses its assigned {scene_name} scene boundary")
    if numeric(captions[-1]["endMs"], "caption.endMs") > numeric(scenes["cta"]["startMs"], "scenes.cta.startMs"):
        raise AdCreatorError("Voiceover/subtitles must finish before CTA")


def extract_json_object(response: Any, required_keys: tuple[str, ...] = ("en", "ja", "yue")) -> dict[str, Any]:
    if isinstance(response, dict) and all(key in response for key in required_keys):
        return response
    for _, value in walk(response):
        if isinstance(value, dict) and all(key in value for key in required_keys):
            return value
        if not isinstance(value, str):
            continue
        for candidate in json_candidates(value):
            if isinstance(candidate, dict) and all(key in candidate for key in required_keys):
                return candidate
        match = re.search(r"\{[\s\S]*\}", value)
        if match:
            try:
                candidate = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and all(key in candidate for key in required_keys):
                return candidate
    expected = "/".join(required_keys)
    raise AdCreatorError(f"Text generation did not return the required {expected} JSON object")
