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


def append_logo_cta(
    body: Path,
    logo_cta: Path,
    output: Path,
    *,
    start_seconds: float,
    excerpt_seconds: float,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    """Append an unchanged-in-content excerpt of the fixed CTA using local FFmpeg."""
    body_info = probe_video(body)
    cta_info = probe_video(logo_cta)
    if not body_info["has_audio"]:
        raise AdCreatorError("Generated ad body has no audio; cannot append fixed Logo CTA")
    if not cta_info["has_audio"]:
        raise AdCreatorError("Fixed Logo CTA has no audio")
    if start_seconds < 0 or excerpt_seconds <= 0 or start_seconds + excerpt_seconds > cta_info["duration"] + 0.05:
        raise AdCreatorError("Fixed Logo CTA excerpt falls outside the source video")
    ffmpeg = require_binary("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    filter_graph = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps=30,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[bodyv];"
        "[0:a]aresample=48000,asetpts=PTS-STARTPTS[bodya];"
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps=30,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[ctav];"
        "[1:a]aresample=48000,asetpts=PTS-STARTPTS[ctaa];"
        "[bodyv][bodya][ctav][ctaa]concat=n=2:v=1:a=1[outv][outa]"
    )
    run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(body),
        "-ss", f"{start_seconds:.3f}", "-t", f"{excerpt_seconds:.3f}", "-i", str(logo_cta),
        "-filter_complex", filter_graph,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(output),
    ], timeout=600)
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
