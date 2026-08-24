from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable


class AdCreatorError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdCreatorError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AdCreatorError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return result or "campaign"


def require_binary(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise AdCreatorError(f"Required command is not available: {name}")
    return resolved


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 900,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdCreatorError(f"Command failed to start: {command[0]}: {exc}") from exc
    if check and result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise AdCreatorError(f"Command failed ({command[0]}): {message[-3000:]}")
    return result


def project_binding_key(skill_id: str, image: Path) -> str:
    """Return the stable registry key for one Skill and one exact authorized input."""
    return f"{skill_id}:{sha256(image)[:12]}"


def json_candidates(text: str) -> Iterable[Any]:
    stripped = text.strip()
    if stripped:
        try:
            yield json.loads(stripped)
        except json.JSONDecodeError:
            pass
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] not in "[{":
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def walk(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from walk(child)


MEDIA_EXTENSIONS = {".mp4", ".mov", ".m4v", ".png", ".jpg", ".jpeg", ".webp", ".wav", ".mp3", ".m4a", ".aac"}


def extract_media_urls(value: Any) -> list[str]:
    found: list[str] = []
    for _, child in walk(value):
        if not isinstance(child, str):
            continue
        candidates = re.findall(r"https?://[^\s\"'<>]+", child)
        for candidate in candidates:
            candidate = candidate.rstrip(".,);]}")
            suffix = Path(urllib.parse.urlparse(candidate).path).suffix.lower()
            if suffix in MEDIA_EXTENSIONS or any(token in candidate.lower() for token in ("video", "image", "audio", "artifact", "download")):
                if candidate not in found:
                    found.append(candidate)
    return found


def extract_response_id(value: Any) -> str | None:
    preferred = {"response_id", "responseid", "run_id", "runid", "task_id", "taskid"}
    for key, child in walk(value):
        if key and key.lower() in preferred and isinstance(child, str) and child:
            return child
        if isinstance(child, str):
            for nested in json_candidates(child):
                nested_id = extract_response_id(nested)
                if nested_id:
                    return nested_id
    return None


def download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temp_path = Path(handle.name)
        curl = shutil.which("curl")
        if curl:
            run([
                curl,
                "--fail",
                "--http1.1",
                "--location",
                "--silent",
                "--show-error",
                "--retry",
                "3",
                "--retry-delay",
                "1",
                "--connect-timeout",
                "30",
                "--max-time",
                "600",
                "--user-agent",
                "makaron-ad-creator/0.6.2",
                "--output",
                str(temp_path),
                url,
            ], timeout=660)
        else:
            request = urllib.request.Request(url, headers={"User-Agent": "makaron-ad-creator/0.6.2"})
            with urllib.request.urlopen(request, timeout=120) as response, temp_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    except Exception as exc:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        raise AdCreatorError(f"Cannot download generated artifact: {exc}") from exc
    if temp_path is None or not temp_path.is_file() or temp_path.stat().st_size == 0:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        raise AdCreatorError("Cannot download generated artifact: downloaded file is empty")
    temp_path.replace(destination)
    return destination


def resolve_path(base: Path, value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


def env_without_secrets() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not any(token in key.upper() for token in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
