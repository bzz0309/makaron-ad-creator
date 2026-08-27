from __future__ import annotations

import json
import math
import subprocess
from array import array
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

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


def extract_video_segment(
    video: Path,
    output: Path,
    *,
    start_seconds: float,
    duration_seconds: float,
    playback_speed: float = 1.0,
) -> Path:
    """Encode an exact time range from a source video without generating new content."""
    ffmpeg = require_binary("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        f"{duration_seconds:.3f}",
        "-i",
        str(video),
        "-an",
    ]
    if abs(playback_speed - 1.0) > 0.001:
        command += ["-vf", f"setpts=(PTS-STARTPTS)/{playback_speed:.6f}"]
    command += [
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
    ]
    run(command, timeout=600)
    return output


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


def _comparison_source(path: Path) -> Image.Image:
    with Image.open(path) as raw:
        oriented = ImageOps.exif_transpose(raw)
        if oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info:
            rgba = oriented.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
            background.alpha_composite(rgba)
            return background.convert("RGB")
        return oriented.convert("RGB")


def _comparison_render(
    before: Path,
    after: Path,
    *,
    width: int = 1080,
    height: int = 1920,
) -> tuple[Image.Image, dict[str, Any]]:
    if (width, height) != (1080, 1920):
        raise AdCreatorError("Before/After comparison canvas is locked to 1080x1920")
    gap = 10
    minimum_outer_margin = 40
    label_gap = 35
    font_size = 72
    stroke_width = 5
    font = _font(font_size)
    metric_draw = ImageDraw.Draw(Image.new("RGB", (1, 1), "black"))
    relative_label_boxes = {
        label: metric_draw.textbbox((0, 0), label, anchor="ms", font=font, stroke_width=stroke_width)
        for label in ("BEFORE", "AFTER")
    }
    label_top_relative = min(box[1] for box in relative_label_boxes.values())
    label_bottom_relative = max(box[3] for box in relative_label_boxes.values())
    label_visual_h = label_bottom_relative - label_top_relative
    sources = {
        "before": _comparison_source(before),
        "after": _comparison_source(after),
    }
    aspect_sum = sum(image.width / image.height for image in sources.values())
    available_pair_w = width - (2 * minimum_outer_margin) - gap
    width_limited_h = math.floor(available_pair_w / aspect_sum)
    available_image_h = height - label_gap - label_visual_h
    common_h = min(width_limited_h, available_image_h)
    if common_h < 1:
        raise AdCreatorError("Before/After source proportions leave no renderable common image height")

    rendered_widths = {
        role: max(1, round(source.width * common_h / source.height))
        for role, source in sources.items()
    }
    while sum(rendered_widths.values()) + gap > width - (2 * minimum_outer_margin):
        common_h -= 1
        if common_h < 1:
            raise AdCreatorError("Before/After source proportions leave no renderable common image height")
        rendered_widths = {
            role: max(1, round(source.width * common_h / source.height))
            for role, source in sources.items()
        }

    group_h = common_h + label_gap + label_visual_h
    image_top = (height - group_h) // 2
    image_bottom = image_top + common_h
    label_baseline_y = image_bottom + label_gap - label_top_relative
    pair_w = rendered_widths["before"] + gap + rendered_widths["after"]
    pair_left = (width - pair_w) // 2
    pair_right = pair_left + pair_w
    canvas = Image.new("RGB", (width, height), "black")
    draw = ImageDraw.Draw(canvas)
    image_layout: dict[str, dict[str, Any]] = {}
    label_layout: dict[str, dict[str, Any]] = {}
    roles = (
        ("before", "BEFORE", pair_left),
        ("after", "AFTER", pair_left + rendered_widths["before"] + gap),
    )
    for role, label, image_left in roles:
        source = sources[role]
        rendered_w = rendered_widths[role]
        resized = source.resize((rendered_w, common_h), Image.Resampling.LANCZOS)
        image_right = image_left + rendered_w
        canvas.paste(resized, (image_left, image_top))
        image_center_x = image_left + rendered_w / 2
        draw.text(
            (image_center_x, label_baseline_y),
            label,
            anchor="ms",
            font=font,
            fill="white",
            stroke_width=stroke_width,
            stroke_fill="black",
        )
        label_bbox = draw.textbbox(
            (image_center_x, label_baseline_y),
            label,
            anchor="ms",
            font=font,
            stroke_width=stroke_width,
        )
        image_layout[role] = {
            "source_width": source.width,
            "source_height": source.height,
            "left": image_left,
            "top": image_top,
            "right": image_right,
            "bottom": image_bottom,
            "rendered_width": rendered_w,
            "rendered_height": common_h,
            "center_x": image_center_x,
            "fully_contained": image_left >= 0 and image_right <= width,
        }
        label_layout[role] = {
            "text": label,
            "anchor_center_x": image_center_x,
            "baseline_y": label_baseline_y,
            "visible_top": label_bbox[1],
            "bbox": list(label_bbox),
            "image_center_delta_px": 0.0,
        }
    layout = {
        "version": 2,
        "canvas": {"width": width, "height": height, "background": "#000000"},
        "gap_px": gap,
        "minimum_outer_margin_px": minimum_outer_margin,
        "common_h": common_h,
        "group": {
            "top": image_top,
            "bottom": image_top + group_h,
            "height": group_h,
            "left": pair_left,
            "right": pair_right,
            "width": pair_w,
            "outer_left": pair_left,
            "outer_right": width - pair_right,
        },
        "images": image_layout,
        "labels": label_layout,
        "label_gap_px": label_gap,
        "label_font_size_px": font_size,
        "label_stroke_width_px": stroke_width,
    }
    return canvas, layout


def comparison_layout_qc(
    before: Path,
    after: Path,
    output: Path,
    *,
    width: int = 1080,
    height: int = 1920,
) -> dict[str, Any]:
    expected, layout = _comparison_render(before, after, width=width, height=height)
    with Image.open(output) as raw:
        actual = raw.convert("RGB")
    images = layout["images"]
    labels = layout["labels"]
    before_box = images["before"]
    after_box = images["after"]
    allowed = Image.new("L", (width, height), 0)
    allowed_draw = ImageDraw.Draw(allowed)
    for item in images.values():
        allowed_draw.rectangle((item["left"], item["top"], item["right"] - 1, item["bottom"] - 1), fill=255)
    for item in labels.values():
        left, top, right, bottom = item["bbox"]
        allowed_draw.rectangle((math.floor(left), math.floor(top), math.ceil(right), math.ceil(bottom)), fill=255)
    if actual.size == (width, height):
        non_black = ImageChops.difference(actual, Image.new("RGB", actual.size, "black"))
        outside_mask = ImageOps.invert(allowed)
        outside_rgb = Image.merge("RGB", (outside_mask, outside_mask, outside_mask))
        background_black = ImageChops.multiply(non_black, outside_rgb).getbbox() is None
        pixel_exact = ImageChops.difference(actual, expected).getbbox() is None
    else:
        background_black = False
        pixel_exact = False
    checks = {
        "canvas_1080x1920": actual.size == (1080, 1920),
        "actual_image_gap_10px": after_box["left"] - before_box["right"] == layout["gap_px"] == 10,
        "outer_margins_symmetric_lte_1px": abs(layout["group"]["outer_left"] - layout["group"]["outer_right"]) <= 1,
        "outer_margins_at_least_40px": min(layout["group"]["outer_left"], layout["group"]["outer_right"]) >= 40,
        "rendered_height_delta_lte_1px": abs(before_box["rendered_height"] - after_box["rendered_height"]) <= 1,
        "rendered_top_delta_lte_1px": abs(before_box["top"] - after_box["top"]) <= 1,
        "rendered_bottom_delta_lte_1px": abs(before_box["bottom"] - after_box["bottom"]) <= 1,
        "images_fully_contained": before_box["fully_contained"] and after_box["fully_contained"],
        "labels_centered_lte_1px": all(item["image_center_delta_px"] <= 1 for item in labels.values()),
        "labels_share_baseline": labels["before"]["baseline_y"] == labels["after"]["baseline_y"],
        "labels_35px_below_images_lte_1px": all(abs((item["visible_top"] - before_box["bottom"]) - 35) <= 1 for item in labels.values()),
        "group_vertically_centered_lte_1px": abs(layout["group"]["top"] - (height - layout["group"]["bottom"])) <= 1,
        "background_outside_images_and_labels_black": background_black,
        "output_matches_deterministic_render": pixel_exact,
    }
    report = {"status": "PASS" if all(checks.values()) else "FAIL", "layout": layout, "checks": checks}
    if report["status"] != "PASS":
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise AdCreatorError(f"Before/After comparison QC failed: {failed}")
    return report


def compose_comparison(before: Path, after: Path, output: Path, width: int = 1080, height: int = 1920) -> Path:
    canvas, _ = _comparison_render(before, after, width=width, height=height)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True)
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
