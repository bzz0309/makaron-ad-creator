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
    ) -> dict[str, Any]:
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
        if response_id and not urls:
            raw, urls = self._materialize(node_id, response_id, raw)
        if destination:
            if not urls:
                raise AdCreatorError(f"Makaron returned no downloadable media for {node_id}; response_id={response_id or 'unknown'}")
            expected_video = destination.suffix.lower() in {".mp4", ".mov", ".m4v"}
            matching = []
            for url in urls:
                suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
                is_video = suffix in {".mp4", ".mov", ".m4v", ".webm"} or "video" in url.lower()
                if is_video == expected_video:
                    matching.append(url)
            download((matching or urls)[0], destination)
        response_path = self.run_dir / "responses" / f"{node_id}.json"
        write_json(response_path, {"response_id": response_id, "media_urls": urls, "response": raw})
        return {"response_id": response_id, "media_urls": urls, "response": raw, "response_path": str(response_path)}

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

    def _materialize(self, node_id: str, response_id: str, fallback: Any) -> tuple[Any, list[str]]:
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
            if urls:
                return last, urls
        return last, []


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
