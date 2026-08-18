from __future__ import annotations

import json
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


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


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
            panel = _cover(raw.convert("RGB"), (panel_w, panel_h))
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

