from __future__ import annotations

import json
import math
import subprocess
from array import array
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .util import AdCreatorError, require_binary, run, sha256


def extract_after_frame(video: Path, output: Path) -> Path:
    ffmpeg = require_binary("ffmpeg")
    ffprobe = require_binary("ffprobe")
    result = run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)])
    duration = float(json.loads(result.stdout)["format"]["duration"])
    timestamp = max(0.0, duration * 0.82)
    output.parent.mkdir(parents=True, exist_ok=True)
    run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.3f}", "-i", str(video), "-frames:v", "1", str(output)])
    return output


def effect_segment_plan(video: Path, *, preferred_hook_seconds: float = 2.5, minimum_result_seconds: float = 3.0) -> dict[str, float]:
    """Split one target-Skill result into non-overlapping Hook and Result ranges."""
    duration = float(probe_video(video)["duration"])
    if duration < 4.5:
        raise AdCreatorError(
            f"Target-Skill effect is too short to derive distinct Hook and Result segments: {duration:.3f}s"
        )
    hook_duration = min(preferred_hook_seconds, duration - minimum_result_seconds)
    if hook_duration < 1.5:
        raise AdCreatorError("Target-Skill effect leaves less than 1.5 seconds for an extracted Hook")
    return {
        "source_duration": duration,
        "hook_start": 0.0,
        "hook_duration": hook_duration,
        "result_start": hook_duration,
        "result_duration": duration - hook_duration,
    }


def extract_video_segment(video: Path, output: Path, *, start_seconds: float, duration_seconds: float) -> Path:
    """Encode an exact time range from a source video without generating new content."""
    ffmpeg = require_binary("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        f"{duration_seconds:.3f}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ], timeout=600)
    return output


def _contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    scale = min(target_w / image.width, target_h / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    panel = Image.new("RGB", (target_w, target_h), "black")
    left = (target_w - resized.width) // 2
    top = (target_h - resized.height) // 2
    panel.paste(resized, (left, top))
    return panel


def _font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def compose_comparison(before: Path, after: Path, output: Path, width: int = 1080, height: int = 1920) -> Path:
    canvas = Image.new("RGB", (width, height), "black")
    gap = 10
    panel_w = (width - gap) // 2
    panel_h = round(height * 0.72)
    top = (height - panel_h) // 2 - 50
    for index, source in enumerate((before, after)):
        with Image.open(source) as raw:
            panel = _contain(raw.convert("RGB"), (panel_w, panel_h))
        x = 0 if index == 0 else panel_w + gap
        canvas.paste(panel, (x, top))
    draw = ImageDraw.Draw(canvas)
    font = _font(72)
    label_y = top + panel_h + 35
    for index, label in enumerate(("BEFORE", "AFTER")):
        center_x = panel_w // 2 if index == 0 else panel_w + gap + panel_w // 2
        box = draw.textbbox((0, 0), label, font=font, stroke_width=4)
        draw.text((center_x - (box[2] - box[0]) / 2, label_y), label, font=font, fill="white", stroke_width=5, stroke_fill="black")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=95)
    return output


def probe_image(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    return {
        "path": str(path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "width": int(width),
        "height": int(height),
    }


def probe_audio(path: Path) -> dict[str, Any]:
    ffprobe = require_binary("ffprobe")
    result = run([
        ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)
    ])
    metadata = json.loads(result.stdout)
    audio = next((item for item in metadata.get("streams", []) if item.get("codec_type") == "audio"), None)
    if not audio:
        raise AdCreatorError(f"No audio stream in {path}")
    return {
        "path": str(path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "codec": audio.get("codec_name"),
        "sample_rate": int(audio.get("sample_rate", 0) or 0),
        "channels": int(audio.get("channels", 0) or 0),
        "duration": float(metadata.get("format", {}).get("duration", 0)),
        "has_audio": True,
    }


def _pcm_segment(path: Path, start_seconds: float, duration_seconds: float, *, loop: bool = False) -> array:
    ffmpeg = require_binary("ffmpeg")
    command = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    if loop:
        command += ["-stream_loop", "-1"]
    command += [
        "-ss", f"{max(0.0, start_seconds):.3f}",
        "-t", f"{duration_seconds:.3f}",
        "-i", str(path),
        "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1",
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=120)
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise AdCreatorError(f"Cannot decode audio segment from {path}: {message[-1000:]}")
    samples = array("h")
    samples.frombytes(result.stdout)
    return samples


def bgm_similarity_in_cta(final_video: Path, bgm: Path, cta_seconds: float) -> float:
    """Compare the CTA audio with the expected timeline position of the campaign BGM."""
    final_info = probe_video(final_video)
    bgm_info = probe_audio(bgm)
    if final_info["duration"] <= cta_seconds or bgm_info["duration"] <= 0:
        return 0.0
    segment_duration = min(0.9, max(0.4, cta_seconds - 0.6))
    final_start = final_info["duration"] - cta_seconds + 0.25
    bgm_start = final_start % bgm_info["duration"]
    final_samples = _pcm_segment(final_video, final_start, segment_duration)
    bgm_samples = _pcm_segment(bgm, bgm_start, segment_duration, loop=True)
    count = min(len(final_samples), len(bgm_samples))
    if count < 1600:
        return 0.0
    final_values = [float(value) for value in final_samples[:count]]
    bgm_values = [float(value) for value in bgm_samples[:count]]
    final_mean = sum(final_values) / count
    bgm_mean = sum(bgm_values) / count
    final_values = [value - final_mean for value in final_values]
    bgm_values = [value - bgm_mean for value in bgm_values]
    best = 0.0
    # AAC/container padding can shift the rendered mix by several dozen milliseconds.
    # Search ±100ms so an otherwise identical continuous BGM is not rejected solely
    # because the MP4 duration has a small encoder tail.
    for lag in range(-800, 801, 8):
        if lag >= 0:
            left = final_values[lag:]
            right = bgm_values[:count - lag]
        else:
            left = final_values[:count + lag]
            right = bgm_values[-lag:]
        dot = sum(a * b for a, b in zip(left, right))
        left_energy = sum(value * value for value in left)
        right_energy = sum(value * value for value in right)
        if left_energy <= 0 or right_energy <= 0:
            continue
        best = max(best, abs(dot) / math.sqrt(left_energy * right_energy))
    return round(best, 4)


def probe_video(path: Path) -> dict[str, Any]:
    ffprobe = require_binary("ffprobe")
    result = run([
        ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)
    ])
    metadata = json.loads(result.stdout)
    video = next((item for item in metadata.get("streams", []) if item.get("codec_type") == "video"), None)
    audio = next((item for item in metadata.get("streams", []) if item.get("codec_type") == "audio"), None)
    if not video:
        raise AdCreatorError(f"No video stream in {path}")
    return {
        "path": str(path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "width": int(video.get("width", 0)),
        "height": int(video.get("height", 0)),
        "codec": video.get("codec_name"),
        "duration": float(metadata.get("format", {}).get("duration", 0)),
        "has_audio": audio is not None,
    }


def is_vertical_resolution_acceptable(info: dict[str, Any], output: dict[str, Any]) -> bool:
    """Accept the 1080p target or a 9:16 fallback that is never below 720p."""
    width = int(info.get("width", 0))
    height = int(info.get("height", 0))
    minimum_width = max(720, int(output.get("minimum_width", 720)))
    minimum_height = max(1280, int(output.get("minimum_height", 1280)))
    if width < minimum_width or height < minimum_height:
        return False
    return abs((width / height) - (9 / 16)) <= 0.01


def normalize_near_vertical_resolution(video: Path, output: dict[str, Any]) -> bool:
    """Pad a provider's near-9:16 720p result when it is only a few pixels short."""
    info = probe_video(video)
    if is_vertical_resolution_acceptable(info, output):
        return False
    width = int(info.get("width", 0))
    height = int(info.get("height", 0))
    minimum_width = max(720, int(output.get("minimum_width", 720)))
    minimum_height = max(1280, int(output.get("minimum_height", 1280)))
    if (
        width < minimum_width
        or height < round(minimum_height * 0.98)
        or abs((width / max(height, 1)) - (9 / 16)) > 0.015
    ):
        return False
    ffmpeg = require_binary("ffmpeg")
    normalized = video.with_name(f"{video.stem}.normalized{video.suffix}")
    run([
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-vf",
        f"scale={minimum_width}:{minimum_height}:force_original_aspect_ratio=decrease,pad={minimum_width}:{minimum_height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(normalized),
    ], timeout=600)
    normalized.replace(video)
    return True
