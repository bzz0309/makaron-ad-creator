from __future__ import annotations

import json
import re
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
        audios: list[Path] | None = None,
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
