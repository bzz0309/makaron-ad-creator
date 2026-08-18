#!/usr/bin/env python3
"""Synthesize, inspect, render, and validate Makaron workflow demos.

Recording mode uses the Python standard library plus FFmpeg/FFprobe. Synthetic
mode additionally uses Pillow. All pixel and timeline operations are
deterministic and repeatable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from synthetic_workflow import add_synthesize_parser


class WorkflowError(RuntimeError):
    pass


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise WorkflowError(f"Required binary not found: {name}")
    return path


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"Top-level JSON value must be an object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: Path) -> dict[str, Any]:
    ffprobe = require_binary("ffprobe")
    result = run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate,duration:format=duration,size,format_name",
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    return json.loads(result.stdout)


def video_stream(metadata: dict[str, Any]) -> dict[str, Any]:
    for stream in metadata.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    raise WorkflowError("Input has no video stream")


def media_duration(metadata: dict[str, Any]) -> float:
    raw = metadata.get("format", {}).get("duration")
    if raw is None:
        raw = video_stream(metadata).get("duration")
    if raw is None:
        raise WorkflowError("Cannot determine media duration")
    return float(raw)


def parse_rate(raw: str | None) -> float:
    if not raw or raw == "0/0":
        return 0.0
    return float(Fraction(raw))


def validate_rect(rect: dict[str, Any], width: int, height: int, label: str) -> None:
    for key in ("x", "y", "w", "h"):
        if key not in rect or not isinstance(rect[key], (int, float)):
            raise WorkflowError(f"{label}.{key} must be numeric")
    x, y, w, h = (float(rect[k]) for k in ("x", "y", "w", "h"))
    if min(x, y) < 0 or w <= 0 or h <= 0:
        raise WorkflowError(f"{label} must have non-negative origin and positive size")
    if x + w > width + 0.01 or y + h > height + 0.01:
        raise WorkflowError(f"{label} exceeds source bounds {width}x{height}")


def validate_time_window(window: Any, duration: float, label: str) -> tuple[float, float]:
    if not isinstance(window, list) or len(window) != 2:
        raise WorkflowError(f"{label} must be [start, end]")
    start, end = float(window[0]), float(window[1])
    if start < 0 or end <= start or end > duration + 0.05:
        raise WorkflowError(f"{label} is invalid for {duration:.3f}s source")
    return start, end


@dataclass(frozen=True)
class RenderSettings:
    width: int
    height: int
    fps: int
    duration: float
    crf: int
    preset: str
    fit: str
    vertical_anchor: str


def validate_config(config: dict[str, Any], metadata: dict[str, Any]) -> RenderSettings:
    version = config.get("version")
    if version != 1:
        raise WorkflowError("config.version must be 1")

    source_video = video_stream(metadata)
    source_width = int(source_video["width"])
    source_height = int(source_video["height"])
    duration = media_duration(metadata)

    output = config.get("output")
    if not isinstance(output, dict):
        raise WorkflowError("config.output must be an object")
    settings = RenderSettings(
        width=int(output.get("width", 1080)),
        height=int(output.get("height", 1920)),
        fps=int(output.get("fps", 30)),
        duration=float(output.get("duration", 4.0)),
        crf=int(output.get("crf", 18)),
        preset=str(output.get("preset", "medium")),
        fit=str(output.get("fit", "contain")),
        vertical_anchor=str(output.get("vertical_anchor", "top")),
    )
    if settings.width <= 0 or settings.height <= 0 or settings.fps <= 0 or settings.duration <= 0:
        raise WorkflowError("output dimensions, fps, and duration must be positive")
    if settings.width % 2 or settings.height % 2:
        raise WorkflowError("output width and height must be even for yuv420p")
    if settings.fit not in {"cover", "contain"}:
        raise WorkflowError("output.fit must be cover or contain")
    if settings.vertical_anchor not in {"top", "center", "bottom"}:
        raise WorkflowError("output.vertical_anchor must be top, center, or bottom")

    segments = config.get("segments")
    if not isinstance(segments, list) or not segments:
        raise WorkflowError("config.segments must be a non-empty array")
    edited_duration = 0.0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise WorkflowError(f"segments[{index}] must be an object")
        start = float(segment.get("source_start", -1))
        end = float(segment.get("source_end", -1))
        speed = float(segment.get("speed", 1.0))
        if start < 0 or end <= start or end > duration + 0.05 or speed <= 0:
            raise WorkflowError(f"segments[{index}] has invalid source times or speed")
        edited_duration += (end - start) / speed
    if edited_duration < settings.duration - 0.25:
        raise WorkflowError(
            f"segments produce only {edited_duration:.3f}s, shorter than requested {settings.duration:.3f}s"
        )

    privacy = config.get("privacy", {})
    if not isinstance(privacy, dict):
        raise WorkflowError("config.privacy must be an object")
    for index, region in enumerate(privacy.get("blur_regions", [])):
        if not isinstance(region, dict):
            raise WorkflowError(f"privacy.blur_regions[{index}] must be an object")
        validate_rect(region.get("source_rect", {}), source_width, source_height, f"blur_regions[{index}].source_rect")
        validate_time_window(region.get("source_time"), duration, f"blur_regions[{index}].source_time")
        sigma = float(region.get("sigma", 30))
        if sigma <= 0:
            raise WorkflowError(f"blur_regions[{index}].sigma must be positive")
        for restore_index, restore in enumerate(region.get("restore", [])):
            if not isinstance(restore, dict):
                raise WorkflowError(f"blur_regions[{index}].restore[{restore_index}] must be an object")
            validate_rect(
                restore.get("source_rect", {}),
                source_width,
                source_height,
                f"blur_regions[{index}].restore[{restore_index}].source_rect",
            )
            validate_time_window(
                restore.get("source_time"),
                duration,
                f"blur_regions[{index}].restore[{restore_index}].source_time",
            )

    for index, tap in enumerate(config.get("taps", [])):
        if not isinstance(tap, dict):
            raise WorkflowError(f"taps[{index}] must be an object")
        at = float(tap.get("at", -1))
        tap_duration = float(tap.get("duration", 0.34))
        x, y = float(tap.get("x", -1)), float(tap.get("y", -1))
        radius = float(tap.get("radius", 74))
        if at < 0 or at + tap_duration > settings.duration + 0.05 or tap_duration <= 0:
            raise WorkflowError(f"taps[{index}] has invalid output time")
        if x < 0 or x > settings.width or y < 0 or y > settings.height or radius <= 0:
            raise WorkflowError(f"taps[{index}] has invalid output position or radius")

    return settings


def ffmpeg_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def between(window: list[Any]) -> str:
    return f"between(t,{ffmpeg_number(float(window[0]))},{ffmpeg_number(float(window[1]))})"


def color_rgba(value: str, alpha: float) -> tuple[int, int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    if len(text) != 6:
        raise WorkflowError(f"Invalid hex color: {value}")
    try:
        red, green, blue = (int(text[offset : offset + 2], 16) for offset in (0, 2, 4))
    except ValueError as exc:
        raise WorkflowError(f"Invalid hex color: {value}") from exc
    return red, green, blue, max(0, min(255, round(alpha * 255)))


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def save_rgba_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    if len(pixels) != width * height * 4:
        raise WorkflowError("Internal PNG buffer size mismatch")
    scanlines = b"".join(b"\x00" + pixels[row * width * 4 : (row + 1) * width * 4] for row in range(height))
    payload = b"\x89PNG\r\n\x1a\n"
    payload += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    payload += png_chunk(b"IDAT", zlib.compress(scanlines, level=9))
    payload += png_chunk(b"IEND", b"")
    path.write_bytes(payload)


def make_touch_frame(
    path: Path,
    *,
    canvas_radius: int,
    ring_radius: float,
    line_width: float,
    color: str,
    opacity: float,
    dot_radius: float,
) -> None:
    size = canvas_radius * 2 + 1
    center = float(canvas_radius)
    red, green, blue, base_alpha = color_rgba(color, opacity)
    pixels = bytearray(size * size * 4)
    half_line = max(0.5, line_width / 2)
    for y in range(size):
        for x in range(size):
            distance = math.hypot(x - center, y - center)
            ring_coverage = max(0.0, min(1.0, half_line + 0.75 - abs(distance - ring_radius)))
            dot_coverage = max(0.0, min(1.0, dot_radius + 0.75 - distance)) if dot_radius > 0 else 0.0
            coverage = max(ring_coverage, dot_coverage)
            index = (y * size + x) * 4
            pixels[index : index + 4] = bytes((red, green, blue, round(base_alpha * coverage)))
    save_rgba_png(path, size, size, bytes(pixels))


def build_touch_assets(config: dict[str, Any], settings: RenderSettings, directory: Path) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    steps_default = max(6, round(settings.fps * 0.34))
    for tap_index, tap in enumerate(config.get("taps", [])):
        at = float(tap["at"])
        duration = float(tap.get("duration", 0.34))
        radius = float(tap.get("radius", 74))
        line_width = float(tap.get("line_width", 9))
        color = str(tap.get("color", "#FFFFFF"))
        steps = int(tap.get("steps", steps_default))
        steps = max(4, min(steps, 20))
        canvas_radius = math.ceil(radius + line_width + 3)
        for step in range(steps):
            progress = step / max(1, steps - 1)
            eased = 1 - (1 - progress) ** 3
            current_radius = radius * (0.48 + 0.52 * eased)
            opacity = 0.95 * (1 - progress**1.7)
            dot_radius = max(0.0, radius * 0.13 * (1 - progress / 0.42)) if progress < 0.42 else 0.0
            path = directory / f"tap-{tap_index:02d}-{step:02d}.png"
            make_touch_frame(
                path,
                canvas_radius=canvas_radius,
                ring_radius=current_radius,
                line_width=line_width,
                color=color,
                opacity=opacity,
                dot_radius=dot_radius,
            )
            frame_start = at + duration * step / steps
            frame_end = at + duration * (step + 1) / steps
            assets.append(
                {
                    "path": path,
                    "x": float(tap["x"]),
                    "y": float(tap["y"]),
                    "size": canvas_radius * 2 + 1,
                    "start": frame_start,
                    "end": frame_end,
                }
            )
    return assets


def fit_filter(settings: RenderSettings) -> str:
    width, height = settings.width, settings.height
    if settings.fit == "contain":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    if settings.vertical_anchor == "top":
        y = "0"
    elif settings.vertical_anchor == "bottom":
        y = "ih-oh"
    else:
        y = "(ih-oh)/2"
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:(iw-ow)/2:{y}"
    )


def build_render_graph(config: dict[str, Any], settings: RenderSettings, touch_assets: list[dict[str, Any]]) -> str:
    privacy_regions = config.get("privacy", {}).get("blur_regions", [])
    branch_count = 1 + len(privacy_regions) + sum(len(region.get("restore", [])) for region in privacy_regions)
    labels = ["privacy_base"] + [f"privacy_src_{index}" for index in range(branch_count - 1)]
    if branch_count == 1:
        filters = ["[0:v]setpts=PTS-STARTPTS[privacy_base]"]
    else:
        filters = [
            f"[0:v]setpts=PTS-STARTPTS,split={branch_count}" + "".join(f"[{label}]" for label in labels)
        ]

    current = "privacy_base"
    source_index = 0
    for region_index, region in enumerate(privacy_regions):
        rect = region["source_rect"]
        blur_source = f"privacy_src_{source_index}"
        source_index += 1
        blurred = f"blurred_{region_index}"
        blurred_composite = f"privacy_blur_{region_index}"
        filters.append(
            f"[{blur_source}]crop={int(rect['w'])}:{int(rect['h'])}:{int(rect['x'])}:{int(rect['y'])},"
            f"gblur=sigma={ffmpeg_number(float(region.get('sigma', 30)))}:steps=2[{blurred}]"
        )
        filters.append(
            f"[{current}][{blurred}]overlay={int(rect['x'])}:{int(rect['y'])}:"
            f"enable='{between(region['source_time'])}':eof_action=pass[{blurred_composite}]"
        )
        current = blurred_composite
        for restore_index, restore in enumerate(region.get("restore", [])):
            restore_rect = restore["source_rect"]
            restore_source = f"privacy_src_{source_index}"
            source_index += 1
            restore_crop = f"restore_crop_{region_index}_{restore_index}"
            restored = f"privacy_restore_{region_index}_{restore_index}"
            filters.append(
                f"[{restore_source}]crop={int(restore_rect['w'])}:{int(restore_rect['h'])}:"
                f"{int(restore_rect['x'])}:{int(restore_rect['y'])}[{restore_crop}]"
            )
            filters.append(
                f"[{current}][{restore_crop}]overlay={int(restore_rect['x'])}:{int(restore_rect['y'])}:"
                f"enable='{between(restore['source_time'])}':eof_action=pass[{restored}]"
            )
            current = restored

    segments = config["segments"]
    segment_inputs = [f"segment_src_{index}" for index in range(len(segments))]
    if len(segments) == 1:
        filters.append(f"[{current}]null[{segment_inputs[0]}]")
    else:
        filters.append(f"[{current}]split={len(segments)}" + "".join(f"[{label}]" for label in segment_inputs))
    segment_outputs: list[str] = []
    for index, segment in enumerate(segments):
        output_label = f"segment_{index}"
        segment_outputs.append(output_label)
        filters.append(
            f"[{segment_inputs[index]}]trim=start={ffmpeg_number(float(segment['source_start']))}:"
            f"end={ffmpeg_number(float(segment['source_end']))},"
            f"setpts=(PTS-STARTPTS)/{ffmpeg_number(float(segment.get('speed', 1.0)))},"
            f"fps={settings.fps},format=yuv420p[{output_label}]"
        )
    filters.append("".join(f"[{label}]" for label in segment_outputs) + f"concat=n={len(segments)}:v=1:a=0[edited]")
    filters.append(
        f"[edited]{fit_filter(settings)},tpad=stop_mode=clone:stop_duration={ffmpeg_number(settings.duration)},"
        f"trim=duration={ffmpeg_number(settings.duration)},setpts=PTS-STARTPTS,fps={settings.fps},format=yuv420p[canvas]"
    )

    current = "canvas"
    for index, asset in enumerate(touch_assets, start=1):
        output_label = f"tap_overlay_{index}"
        x = ffmpeg_number(asset["x"] - asset["size"] / 2)
        y = ffmpeg_number(asset["y"] - asset["size"] / 2)
        filters.append(
            f"[{current}][{index}:v]overlay={x}:{y}:enable='between(t,{ffmpeg_number(asset['start'])},"
            f"{ffmpeg_number(asset['end'])})':eof_action=pass:shortest=0[{output_label}]"
        )
        current = output_label
    filters.append(f"[{current}]format=yuv420p[outv]")
    return ";".join(filters)


def command_render(args: argparse.Namespace) -> int:
    ffmpeg = require_binary("ffmpeg")
    source = args.input.resolve()
    config_path = args.config.resolve()
    output = args.output.resolve()
    if not source.is_file():
        raise WorkflowError(f"Input not found: {source}")
    config = load_json(config_path)
    metadata = probe(source)
    settings = validate_config(config, metadata)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="makaron-workflow-") as temp_name:
        touch_assets = build_touch_assets(config, settings, Path(temp_name))
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
        for asset in touch_assets:
            command.extend(["-loop", "1", "-framerate", str(settings.fps), "-i", str(asset["path"])])
        command.extend(
            [
                "-filter_complex",
                build_render_graph(config, settings, touch_assets),
                "-map",
                "[outv]",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                settings.preset,
                "-crf",
                str(settings.crf),
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-t",
                ffmpeg_number(settings.duration),
                str(output),
            ]
        )
        if args.print_command:
            print(json.dumps(command, ensure_ascii=False, indent=2))
        run(command)

    report = validate_output(output, settings)
    report.update(
        {
            "source": str(source),
            "source_sha256": sha256(source),
            "config": str(config_path),
            "config_sha256": sha256(config_path),
            "output": str(output),
            "output_sha256": sha256(output),
        }
    )
    report_path = output.with_suffix(output.suffix + ".qc.json")
    write_json(report_path, report)
    if not report["pass"]:
        raise WorkflowError(f"Rendered output failed QC; see {report_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    ffmpeg = require_binary("ffmpeg")
    source = args.input.resolve()
    out_dir = args.out_dir.resolve()
    if not source.is_file():
        raise WorkflowError(f"Input not found: {source}")
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = probe(source)
    duration = media_duration(metadata)
    frame_count = max(4, int(args.frames))
    interval = duration / frame_count
    columns = min(4, frame_count)
    rows = math.ceil(frame_count / columns)
    contact_sheet = out_dir / "contact-sheet.jpg"
    filter_graph = (
        f"fps=1/{ffmpeg_number(interval)},scale={int(args.thumb_width)}:-2,"
        f"tile={columns}x{rows}:padding=4:margin=4:color=black"
    )
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            filter_graph,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(contact_sheet),
        ]
    )
    manifest = {
        "input": str(source),
        "input_sha256": sha256(source),
        "probe": metadata,
        "contact_sheet": str(contact_sheet),
        "tile_order": "left-to-right, top-to-bottom",
        "sample_times_seconds": [round(interval * index, 3) for index in range(frame_count)],
        "columns": columns,
        "rows": rows,
    }
    manifest_path = out_dir / "inspection.json"
    write_json(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def validate_output(path: Path, settings: RenderSettings) -> dict[str, Any]:
    metadata = probe(path)
    stream = video_stream(metadata)
    actual_duration = media_duration(metadata)
    actual_width = int(stream["width"])
    actual_height = int(stream["height"])
    actual_fps = parse_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
    audio_streams = [item for item in metadata.get("streams", []) if item.get("codec_type") == "audio"]
    checks = {
        "duration": abs(actual_duration - settings.duration) <= 0.05,
        "dimensions": actual_width == settings.width and actual_height == settings.height,
        "fps": abs(actual_fps - settings.fps) <= 0.01,
        "muted": not audio_streams,
        "codec": stream.get("codec_name") == "h264",
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "actual": {
            "duration": actual_duration,
            "width": actual_width,
            "height": actual_height,
            "fps": actual_fps,
            "codec": stream.get("codec_name"),
            "audio_streams": len(audio_streams),
        },
        "expected": {
            "duration": settings.duration,
            "width": settings.width,
            "height": settings.height,
            "fps": settings.fps,
            "codec": "h264",
            "audio_streams": 0,
        },
    }


def command_validate(args: argparse.Namespace) -> int:
    config = load_json(args.config.resolve())
    metadata = probe(args.input.resolve())
    settings = validate_config(config, metadata)
    report = validate_output(args.output.resolve(), settings)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Probe a recording and create a contact sheet")
    inspect_parser.add_argument("--input", type=Path, required=True)
    inspect_parser.add_argument("--out-dir", type=Path, required=True)
    inspect_parser.add_argument("--frames", type=int, default=12)
    inspect_parser.add_argument("--thumb-width", type=int, default=360)
    inspect_parser.set_defaults(func=command_inspect)

    render_parser = subparsers.add_parser("render", help="Render a configured short workflow demo")
    render_parser.add_argument("--input", type=Path, required=True)
    render_parser.add_argument("--config", type=Path, required=True)
    render_parser.add_argument("--output", type=Path, required=True)
    render_parser.add_argument("--print-command", action="store_true")
    render_parser.set_defaults(func=command_render)

    validate_parser = subparsers.add_parser("validate", help="Validate an output against its config")
    validate_parser.add_argument("--input", type=Path, required=True, help="Original source recording")
    validate_parser.add_argument("--config", type=Path, required=True)
    validate_parser.add_argument("--output", type=Path, required=True)
    validate_parser.set_defaults(func=command_validate)

    add_synthesize_parser(subparsers, WorkflowError)
    return root


def main() -> int:
    try:
        args = parser().parse_args()
        return int(args.func(args))
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        print(f"Command failed with exit code {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
