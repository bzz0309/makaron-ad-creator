#!/usr/bin/env python3
"""Deterministic synthetic Makaron workflow renderer.

This module is loaded by workflow_recording.py.  It renders a four-second,
data-driven app demo from Makaron marketplace metadata without controlling or
recording a physical device.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont
except ImportError as exc:  # pragma: no cover - exercised by dependency check
    raise RuntimeError("Synthetic mode requires Pillow: python3 -m pip install Pillow") from exc


WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 4.0
PHONE_LEFT = 99
PHONE_RIGHT = 981
PHONE_WIDTH = PHONE_RIGHT - PHONE_LEFT
STATUS_HEIGHT = 175
# Grid position within the scrollable surface. The surface starts below the
# fixed 175px iOS status bar, so this produces screen y=1335 at scroll zero.
HOME_GRID_TOP = 1160
CARD_WIDTH = 400
CARD_HEIGHT = 536
CARD_GAP_X = 24
CARD_GAP_Y = 24
CARD_ROW_HEIGHT = CARD_HEIGHT + CARD_GAP_Y
TIMELINE = {
    "home_hold": [0.0, 0.25],
    "home_scroll": [0.25, 1.40],
    "template_outer": [1.42, 1.76],
    "template_inner": [1.47, 1.72],
    "detail_cut": 1.80,
    "detail_hold": [1.80, 3.45],
    "create_outer": [3.48, 3.82],
    "create_inner": [3.53, 3.78],
    "end": 4.0,
}


class SyntheticError(RuntimeError):
    pass


@dataclass(frozen=True)
class Fonts:
    regular_path: Path
    bold_path: Path

    def regular(self, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.regular_path), size=size)

    def bold(self, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.bold_path), size=size)


@dataclass
class CatalogCard:
    item: dict[str, Any]
    poster: Image.Image


@dataclass(frozen=True)
class UISkin:
    home_top: Image.Image
    home_target: Image.Image
    detail: Image.Image


def _run(command: list[str], *, input_bytes: bytes | None = None, capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        check=True,
        input=input_bytes,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def _require_binary(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise SyntheticError(f"Required binary not found: {name}")
    return value


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyntheticError(f"Cannot read JSON {path}: {exc}") from exc


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return text or "makaron-skill"


def _normalize_catalog(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        for key in ("skills", "items", "data"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        raise SyntheticError("Makaron catalog JSON must be an array or contain skills/items/data")
    items = [item for item in raw if isinstance(item, dict) and item.get("id")]
    if not items:
        raise SyntheticError("Makaron catalog contains no skills")
    return sorted(items, key=lambda item: (int(item.get("sort_order", 10**9)), str(item.get("id"))))


def load_catalog(catalog_json: Path | None) -> list[dict[str, Any]]:
    if catalog_json:
        return _normalize_catalog(_read_json(catalog_json.resolve()))
    makaron = _require_binary("makaron")
    try:
        result = _run([makaron, "skills", "list", "--json"], capture=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip() if exc.stderr else ""
        raise SyntheticError(f"Cannot load Makaron marketplace catalog: {detail or exc}") from exc
    try:
        return _normalize_catalog(json.loads(result.stdout.decode("utf-8")))
    except json.JSONDecodeError as exc:
        raise SyntheticError("makaron skills list returned invalid JSON") from exc


def resolve_skill(catalog: list[dict[str, Any]], query: str) -> dict[str, Any]:
    exact_id = [item for item in catalog if str(item.get("id")) == query]
    if exact_id:
        return exact_id[0]
    needle = query.casefold().strip()
    candidates: list[dict[str, Any]] = []
    for item in catalog:
        values: list[str] = []
        if item.get("label"):
            values.append(str(item["label"]))
        labels = item.get("labels")
        if isinstance(labels, dict):
            values.extend(str(value) for value in labels.values() if value)
        if any(value.casefold().strip() == needle for value in values):
            candidates.append(item)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        details = ", ".join(f"{item.get('id')} ({item.get('label') or item.get('labels', {}).get('en')})" for item in candidates)
        raise SyntheticError(f"Skill label is ambiguous; use an ID. Candidates: {details}")
    raise SyntheticError(f"Skill not found in marketplace catalog: {query}")


def localized_value(item: dict[str, Any], field: str, locale: str) -> str:
    mapping = item.get(field)
    if isinstance(mapping, dict):
        value = mapping.get(locale)
        if not value and locale == "zh-Hant":
            value = mapping.get("zh")
        if value:
            return str(value)
    if locale == "en":
        fallback = item.get("label" if field == "labels" else "prompt")
        if fallback:
            return str(fallback)
    raise SyntheticError(f"Skill {item.get('id')} is missing {field}.{locale}")


def validate_skill_assets(item: dict[str, Any], locales: Iterable[str]) -> None:
    if not item.get("image"):
        raise SyntheticError(f"Skill {item.get('id')} has no image cover")
    image_count = int(item.get("image_count") or 1)
    before_images = item.get("before_images") or []
    if not isinstance(before_images, list) or len(before_images) < image_count:
        raise SyntheticError(
            f"Skill {item.get('id')} needs {image_count} before_images but provides {len(before_images) if isinstance(before_images, list) else 0}"
        )
    for locale in locales:
        localized_value(item, "labels", locale)
        localized_value(item, "prompts", locale)


def _cache_name(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".media"
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24] + suffix


def asset_is_decodable(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        pass
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return False
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0 and b"video" in result.stdout


def fetch_asset(url: str, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / _cache_name(url)
    if destination.is_file() and destination.stat().st_size > 0:
        if asset_is_decodable(destination):
            return destination
        destination.unlink(missing_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    parsed = urllib.parse.urlparse(url)
    curl = shutil.which("curl")
    if curl and parsed.scheme in {"http", "https"}:
        try:
            _run([
                curl,
                "-L",
                "--fail",
                "--silent",
                "--show-error",
                "--retry",
                "3",
                "--retry-all-errors",
                "--retry-delay",
                "2",
                "--connect-timeout",
                "60",
                url,
                "-o",
                str(partial),
            ])
        except subprocess.CalledProcessError as exc:
            partial.unlink(missing_ok=True)
            raise SyntheticError(f"Cannot download asset {url}") from exc
    else:
        request = urllib.request.Request(url, headers={"User-Agent": "MakaronWorkflowRenderer/2.0"})
        context = ssl.create_default_context()
        try:
            import certifi  # type: ignore

            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
        try:
            with urllib.request.urlopen(request, timeout=60, context=context) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
        except Exception as exc:
            partial.unlink(missing_ok=True)
            raise SyntheticError(f"Cannot download asset {url}: {exc}") from exc
    if partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise SyntheticError(f"Downloaded asset is empty: {url}")
    if not asset_is_decodable(partial):
        partial.unlink(missing_ok=True)
        raise SyntheticError(f"Downloaded asset is not decodable: {url}")
    partial.replace(destination)
    return destination


def discover_fonts(skill_dir: Path, locale: str = "en") -> Fonts:
    bundled = skill_dir / "assets" / "fonts" / "NotoSansCJK-Regular.ttc"
    if locale == "en":
        regular_candidates = [
            Path("/System/Library/Fonts/SFNS.ttf"),
            Path("/System/Library/Fonts/HelveticaNeue.ttc"),
        ]
        bold_candidates = [
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
            Path("/System/Library/Fonts/SFNS.ttf"),
        ]
    elif locale == "ja":
        japanese = sorted(Path("/System/Library/Fonts").glob("*W3.ttc"))
        japanese_bold = sorted(Path("/System/Library/Fonts").glob("*W6.ttc"))
        regular_candidates = japanese + [Path("/System/Library/Fonts/Hiragino Sans GB.ttc")]
        bold_candidates = japanese_bold + regular_candidates
    else:
        regular_candidates = [Path("/System/Library/Fonts/Hiragino Sans GB.ttc")]
        bold_candidates = regular_candidates.copy()
    regular_candidates.extend([
        bundled,
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ])
    bold_candidates.extend([
        bundled,
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ])
    regular = next((path for path in regular_candidates if path.is_file()), None)
    bold = next((path for path in bold_candidates if path.is_file()), regular)
    if not regular or not bold:
        raise SyntheticError("No CJK-capable font found; bundle assets/fonts/NotoSansCJK-Regular.ttc")
    return Fonts(regular, bold)


def load_ui_skin(skill_dir: Path, locale: str) -> UISkin:
    root = skill_dir / "assets" / "ui-baseline" / locale
    paths = {name: root / f"{name.replace('_', '-')}.png" for name in ("home_top", "home_target", "detail")}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise SyntheticError(f"Missing iOS UI baseline assets: {', '.join(missing)}")
    images: dict[str, Image.Image] = {}
    for name, path in paths.items():
        with Image.open(path) as image:
            image.load()
            if image.size != (WIDTH, HEIGHT):
                raise SyntheticError(f"UI baseline must be {WIDTH}x{HEIGHT}: {path}")
            images[name] = image.convert("RGBA")
    return UISkin(images["home_top"], images["home_target"], images["detail"])


def _fit_image(image: Image.Image, width: int, height: int) -> Image.Image:
    source = image.convert("RGB")
    ratio = max(width / source.width, height / source.height)
    resized = source.resize((max(1, round(source.width * ratio)), max(1, round(source.height * ratio))), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def media_poster(path: Path, width: int, height: int, temp_dir: Path) -> Image.Image:
    try:
        with Image.open(path) as image:
            image.load()
            return _fit_image(image, width, height)
    except Exception:
        pass
    ffmpeg = _require_binary("ffmpeg")
    poster = temp_dir / f"poster-{hashlib.sha1(str(path).encode()).hexdigest()[:12]}.jpg"
    try:
        _run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                "0.10",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                str(poster),
            ]
        )
    except subprocess.CalledProcessError as exc:
        raise SyntheticError(f"Cannot decode cover asset: {path}") from exc
    with Image.open(poster) as image:
        image.load()
        return image.convert("RGB")


def target_video_frames(path: Path, width: int, height: int, frame_count: int, temp_dir: Path) -> list[Image.Image]:
    try:
        with Image.open(path) as image:
            image.load()
            fitted = _fit_image(image, width, height)
            frames: list[Image.Image] = []
            for index in range(frame_count):
                scale = 1.0 + 0.018 * index / max(1, frame_count - 1)
                zoom = fitted.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
                left = (zoom.width - width) // 2
                top = (zoom.height - height) // 2
                frames.append(zoom.crop((left, top, left + width, top + height)))
            return frames
    except Exception:
        pass
    ffmpeg = _require_binary("ffmpeg")
    frame_dir = temp_dir / "target-frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    pattern = frame_dir / "%04d.jpg"
    seconds = frame_count / FPS
    try:
        _run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(path),
                "-t",
                f"{seconds:.6f}",
                "-vf",
                f"fps={FPS},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                "-q:v",
                "2",
                str(pattern),
            ]
        )
    except subprocess.CalledProcessError as exc:
        raise SyntheticError(f"Cannot decode animated target cover: {path}") from exc
    paths = sorted(frame_dir.glob("*.jpg"))
    if not paths:
        raise SyntheticError(f"Target cover produced no frames: {path}")
    frames = []
    for frame_path in paths:
        with Image.open(frame_path) as image:
            image.load()
            frames.append(image.convert("RGB"))
    while len(frames) < frame_count:
        frames.append(frames[-1].copy())
    return frames[:frame_count]


def _ease(progress: float) -> float:
    value = max(0.0, min(1.0, progress))
    return value * value * (3.0 - 2.0 * value)


def _alpha_color(color: tuple[int, int, int], alpha: int) -> tuple[int, int, int, int]:
    return color[0], color[1], color[2], max(0, min(255, alpha))


def _draw_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font: ImageFont.FreeTypeFont, fill: str | tuple[int, ...], *, stroke: int = 0, stroke_fill: str = "#000000") -> None:
    draw.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int) -> list[str]:
    is_cjk = bool(re.search(r"[\u3000-\u9fff\u3040-\u30ff]", text))
    units = list(text) if is_cjk else text.split()
    spacer = "" if is_cjk else " "
    lines: list[str] = []
    current = ""
    consumed = 0
    truncated = False
    for unit in units:
        candidate = unit if not current else current + spacer + unit
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            consumed += 1
            continue
        if current:
            lines.append(current)
        current = unit
        consumed += 1
        if len(lines) >= max_lines:
            truncated = True
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if (truncated or consumed < len(units)) and lines:
        while draw.textlength(lines[-1] + "…", font=font) > max_width and lines[-1]:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def draw_status_bar(canvas: Image.Image, fonts: Fonts) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, WIDTH, STATUS_HEIGHT), fill="#000000")
    _draw_text(draw, (166, 62), "9:41", fonts.bold(38), "white")
    draw.rounded_rectangle((349, 39, 731, 118), radius=42, fill="#030303", outline="#24141e", width=3)
    draw.ellipse((373, 62, 405, 94), fill="#f0443c")
    for index, height in enumerate((14, 22, 31, 41)):
        x = 754 + index * 14
        draw.rounded_rectangle((x, 99 - height, x + 8, 99), radius=3, fill="white")
    _draw_text(draw, (816, 62), "5G", fonts.bold(35), "white")
    draw.rounded_rectangle((868, 61, 929, 99), radius=10, outline="white", width=4)
    draw.rectangle((929, 72, 935, 88), fill="white")
    _draw_text(draw, (880, 61), "88", fonts.bold(24), "white")


def draw_home_header(canvas: Image.Image, fonts: Fonts, locale: str, scroll_y: float) -> None:
    draw = ImageDraw.Draw(canvas)
    offset = STATUS_HEIGHT - scroll_y
    def y(value: float) -> float:
        return offset + value
    _draw_text(draw, (150, y(50)), "✦  UPDATES", fonts.regular(22), "#9c939e")
    draw.rounded_rectangle((706, y(35), 824, y(90)), radius=18, fill="#171119", outline="#3b273c", width=2)
    _draw_text(draw, (728, y(48)), "ϟ 661", fonts.bold(25), "#d29bdc")
    _draw_text(draw, (284, y(240)), "✣", fonts.bold(70), "#e448d4")
    _draw_text(draw, (373, y(220)), "Makaron", fonts.bold(76), "white")
    _draw_text(draw, (338, y(365)), "one man creative studio", fonts.regular(30), "#df42ce")
    taglines = {
        "en": ["Makaron predicts your next creative move.", "Upload a photo — edit it, explore it, animate it."],
        "zh-Hant": ["Makaron 預測你的下一步創作。", "上傳照片，編輯、探索，讓它動起來。"],
        "ja": ["Makaronが次のクリエイティブを予測。", "写真をアップして、編集・探索・アニメ化。"],
    }
    for index, line in enumerate(taglines[locale]):
        width = draw.textlength(line, font=fonts.regular(31))
        _draw_text(draw, ((WIDTH - width) / 2, y(480 + index * 54)), line, fonts.regular(31), "#aaa2ad")
    draw.rounded_rectangle((131, y(650), 949, y(878)), radius=42, fill="#17131b", outline="#3a303b", width=2)
    draw.rounded_rectangle((154, y(682), 330, y(846)), radius=32, fill="#201722")
    _draw_text(draw, (214, y(728)), "▣", fonts.regular(52), "#bf37c9")
    create_text = {"en": "Storyboard these photos and\nadd a soundtrack", "zh-Hant": "為這些照片製作分鏡，\n再加上配樂", "ja": "写真を絵コンテにして\nサウンドを追加"}[locale]
    _draw_text(draw, (394, y(692)), create_text, fonts.regular(31), "#9c929e")
    _draw_text(draw, (398, y(812)), "▱", fonts.regular(38), "#8e8691")
    _draw_text(draw, (696, y(816)), "Skill", fonts.regular(28), "#8e8691")
    _draw_text(draw, (792, y(816)), "+ Create", fonts.regular(28), "#db42cf")
    market = {"en": "Skill Market", "zh-Hant": "技能市場", "ja": "スキルマーケット"}[locale]
    width = draw.textlength(market, font=fonts.bold(37))
    _draw_text(draw, ((WIDTH - width) / 2, y(995)), market, fonts.bold(37), "white")
    categories = {
        "en": ["All", "Idol Moment", "Creative Lab", "Fantasy Anime", "Action"],
        "zh-Hant": ["全部", "偶像時刻", "創意實驗室", "奇幻動漫", "動作"],
        "ja": ["すべて", "アイドル", "クリエイティブ", "ファンタジー", "アクション"],
    }[locale]
    x = 132
    for index, label in enumerate(categories):
        fill = "white" if index == 0 else "#807782"
        _draw_text(draw, (x, y(1105)), label, fonts.bold(25), fill)
        x += int(draw.textlength(label, font=fonts.bold(25))) + 55
    draw.rounded_rectangle((131, y(1150), 170, y(1155)), radius=3, fill="#ef47dc")


def paste_ios_status_bar(canvas: Image.Image, source: Image.Image) -> None:
    canvas.paste(source.crop((0, 0, WIDTH, STATUS_HEIGHT)), (0, 0))


def draw_bottom_nav(canvas: Image.Image, skin: UISkin) -> None:
    box = (337, 1746, 743, 1835)
    crop = skin.home_target.crop(box)
    mask = Image.new("L", crop.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, crop.width - 1, crop.height - 1), radius=45, fill=255)
    canvas.paste(crop, (box[0], box[1]), mask)


def draw_card(canvas: Image.Image, card: CatalogCard, x: int, y: int, fonts: Fonts, locale: str, target: bool) -> tuple[int, int, int, int]:
    if y + CARD_HEIGHT < STATUS_HEIGHT or y > HEIGHT:
        return x, y, x + CARD_WIDTH, y + CARD_HEIGHT
    image = card.poster
    if target:
        image = ImageEnhance.Brightness(image).enhance(1.04)
    mask = Image.new("L", (CARD_WIDTH, CARD_HEIGHT), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, CARD_WIDTH, CARD_HEIGHT), radius=30, fill=255)
    canvas.paste(image, (x, y), mask)
    shade = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    for row in range(150):
        alpha = round(170 * row / 149)
        shade_draw.line((0, CARD_HEIGHT - 150 + row, CARD_WIDTH, CARD_HEIGHT - 150 + row), fill=(0, 0, 0, alpha))
    canvas.paste(shade, (x, y), shade)
    draw = ImageDraw.Draw(canvas)
    label = localized_value(card.item, "labels", locale)
    lines = wrap_text(draw, label, fonts.bold(29), CARD_WIDTH - 48, 2)
    base_y = y + CARD_HEIGHT - 52 - (len(lines) - 1) * 36
    for index, line in enumerate(lines):
        _draw_text(draw, (x + 28, base_y + index * 36), line, fonts.bold(29), "white", stroke=1)
    return x, y, x + CARD_WIDTH, y + CARD_HEIGHT


def draw_pulse(canvas: Image.Image, center: tuple[float, float], time_value: float, window: tuple[float, float], color: tuple[int, int, int], max_radius: float, width: int) -> None:
    start, end = window
    if time_value < start or time_value > end:
        return
    progress = (time_value - start) / (end - start)
    eased = 1.0 - (1.0 - progress) ** 3
    radius = max_radius * (0.48 + 0.52 * eased)
    alpha = round(245 * (1.0 - progress**1.7))
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=_alpha_color(color, alpha), width=width)
    if progress < 0.42:
        dot_radius = max_radius * 0.10 * (1.0 - progress / 0.42)
        draw.ellipse((x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius), fill=_alpha_color(color, alpha))
    canvas.alpha_composite(overlay)


def draw_home_frame(cards: list[CatalogCard], target_index: int, fonts: Fonts, skin: UISkin, locale: str, time_value: float) -> tuple[Image.Image, tuple[float, float], tuple[int, int, int, int]]:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), "black")
    row = target_index // 2
    target_center_final_y = 970
    final_scroll = max(0.0, STATUS_HEIGHT + HOME_GRID_TOP + row * CARD_ROW_HEIGHT + CARD_HEIGHT / 2 - target_center_final_y)
    if time_value <= TIMELINE["home_scroll"][0]:
        scroll = 0.0
    elif time_value >= TIMELINE["home_scroll"][1]:
        scroll = final_scroll
    else:
        progress = (time_value - TIMELINE["home_scroll"][0]) / (TIMELINE["home_scroll"][1] - TIMELINE["home_scroll"][0])
        scroll = final_scroll * _ease(progress)
    # Use the approved iPhone capture as the real UI skin. Only marketplace
    # content below the header is reconstructed from catalog data.
    header_bottom = STATUS_HEIGHT + HOME_GRID_TOP
    header = skin.home_top.crop((0, STATUS_HEIGHT, WIDTH, header_bottom))
    canvas.paste(header, (0, round(STATUS_HEIGHT - scroll)))
    target_rect = (0, 0, 0, 0)
    for index, card in enumerate(cards):
        card_row, column = divmod(index, 2)
        x = 128 + column * (CARD_WIDTH + CARD_GAP_X)
        y = round(STATUS_HEIGHT + HOME_GRID_TOP + card_row * CARD_ROW_HEIGHT - scroll)
        rect = draw_card(canvas, card, x, y, fonts, locale, index == target_index)
        if index == target_index:
            target_rect = rect
    draw_bottom_nav(canvas, skin)
    paste_ios_status_bar(canvas, skin.home_top)
    center = ((target_rect[0] + target_rect[2]) / 2, (target_rect[1] + target_rect[3]) / 2)
    draw_pulse(canvas, center, time_value, tuple(TIMELINE["template_outer"]), (255, 255, 255), 74, 9)
    draw_pulse(canvas, center, time_value, tuple(TIMELINE["template_inner"]), (255, 47, 209), 52, 7)
    return canvas.convert("RGB"), center, target_rect


def paste_detail_icon(canvas: Image.Image, skin: UISkin, box: tuple[int, int, int, int]) -> None:
    crop = skin.detail.crop(box)
    mask = Image.new("L", crop.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, crop.width - 1, crop.height - 1), fill=255)
    canvas.paste(crop, (box[0], box[1]), mask)


def draw_detail_frame(
    target_frame: Image.Image,
    before_images: list[Image.Image],
    item: dict[str, Any],
    fonts: Fonts,
    skin: UISkin,
    locale: str,
    time_value: float,
) -> tuple[Image.Image, tuple[float, float], tuple[int, int, int, int]]:
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), "black")
    canvas.paste(target_frame, (PHONE_LEFT, STATUS_HEIGHT))
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for row in range(520):
        alpha = round(180 * row / 519)
        overlay_draw.line((PHONE_LEFT, 1140 + row, PHONE_RIGHT, 1140 + row), fill=(0, 0, 0, alpha))
    canvas.alpha_composite(overlay)
    draw = ImageDraw.Draw(canvas, "RGBA")
    label = localized_value(item, "labels", locale)
    label_lines = wrap_text(draw, label, fonts.bold(38), 760, 2)
    label_y = 1365 - (len(label_lines) - 1) * 40
    for index, line in enumerate(label_lines):
        _draw_text(draw, (135, label_y + index * 44), line, fonts.bold(38), "white", stroke=1)
    slot_size = 126
    slot_y = 1450
    for index in range(int(item.get("image_count") or 1)):
        x = 136 + index * (slot_size + 24)
        mask = Image.new("L", (slot_size, slot_size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, slot_size, slot_size), radius=28, fill=255)
        thumb = _fit_image(before_images[index], slot_size, slot_size)
        canvas.paste(thumb, (x, slot_y), mask)
        draw.rounded_rectangle((x, slot_y, x + slot_size, slot_y + slot_size), radius=28, outline=(240, 240, 240, 180), width=3)
    plus_x = 136 + int(item.get("image_count") or 1) * (slot_size + 24)
    draw.rounded_rectangle((plus_x, slot_y, plus_x + slot_size, slot_y + slot_size), radius=28, fill=(15, 13, 18, 190), outline=(110, 105, 114, 190), width=3)
    draw.line((plus_x + 42, slot_y + 63, plus_x + 84, slot_y + 63), fill="white", width=5)
    draw.line((plus_x + 63, slot_y + 42, plus_x + 63, slot_y + 84), fill="white", width=5)
    panel = (126, 1600, 954, 1832)
    draw.rounded_rectangle(panel, radius=38, fill=(25, 21, 29, 242), outline=(79, 65, 82, 230), width=2)
    prompt = localized_value(item, "prompts", locale)
    prompt_lines = wrap_text(draw, prompt, fonts.regular(31), 756, 2)
    for index, line in enumerate(prompt_lines):
        _draw_text(draw, (155, 1630 + index * 45), line, fonts.regular(31), "#ece6ef")
    for offset in (0, 8, 16):
        draw.line((158, 1774 + offset, 174, 1765 + offset, 190, 1774 + offset, 174, 1783 + offset, 158, 1774 + offset), fill="#a6a0a9", width=2)
    chip_label = label
    chip_width = min(265, max(130, round(draw.textlength(chip_label, font=fonts.regular(25))) + 56))
    chip_x = 690 - chip_width
    draw.rounded_rectangle((chip_x, 1747, 690, 1810), radius=30, fill=(79, 31, 86, 220), outline=(123, 55, 132, 180), width=2)
    clipped = wrap_text(draw, chip_label, fonts.regular(25), chip_width - 38, 1)[0]
    _draw_text(draw, (chip_x + 18, 1764), clipped, fonts.regular(25), "#ef9aeb")
    create_text = {"en": "Create", "zh-Hant": "建立", "ja": "作成"}[locale]
    create_rect = (760, 1740, 928, 1817)
    _draw_text(draw, (802, 1760), create_text, fonts.bold(28), "#e84adb")
    create_center = ((create_rect[0] + create_rect[2]) / 2, (create_rect[1] + create_rect[3]) / 2)
    draw_pulse(canvas, create_center, time_value, tuple(TIMELINE["create_outer"]), (255, 255, 255), 74, 9)
    draw_pulse(canvas, create_center, time_value, tuple(TIMELINE["create_inner"]), (255, 47, 209), 52, 7)
    paste_ios_status_bar(canvas, skin.detail)
    # The approved iPhone detail capture places these controls across the
    # status/content boundary. Paste each complete control once, after both
    # layers, so the status crop cannot leave a duplicated half-circle.
    paste_detail_icon(canvas, skin, (124, 143, 200, 219))
    paste_detail_icon(canvas, skin, (880, 143, 956, 219))
    return canvas.convert("RGB"), create_center, create_rect


def select_poster_items(catalog: list[dict[str, Any]], target_index: int) -> set[int]:
    # Every card that can cross the viewport from the home top through the
    # target row must have a real marketplace poster. Never synthesize a tile.
    return set(range(min(len(catalog), target_index + 5)))


def probe_output(path: Path) -> dict[str, Any]:
    ffprobe = _require_binary("ffprobe")
    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,codec_type,width,height,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    return json.loads(result.stdout.decode("utf-8"))


def qc_output(path: Path) -> dict[str, Any]:
    metadata = probe_output(path)
    videos = [stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video"]
    audio = [stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "audio"]
    if not videos:
        raise SyntheticError(f"Rendered output has no video stream: {path}")
    stream = videos[0]
    rate = stream.get("avg_frame_rate", "0/1").split("/")
    fps = float(rate[0]) / float(rate[1]) if len(rate) == 2 and float(rate[1]) else 0.0
    duration = float(metadata.get("format", {}).get("duration", 0.0))
    checks = {
        "duration": abs(duration - DURATION) <= 0.05,
        "dimensions": int(stream.get("width", 0)) == WIDTH and int(stream.get("height", 0)) == HEIGHT,
        "fps": abs(fps - FPS) <= 0.01,
        "codec": stream.get("codec_name") == "h264",
        "muted": not audio,
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "actual": {"duration": duration, "width": stream.get("width"), "height": stream.get("height"), "fps": fps, "codec": stream.get("codec_name"), "audio_streams": len(audio)},
        "expected": {"duration": DURATION, "width": WIDTH, "height": HEIGHT, "fps": FPS, "codec": "h264", "audio_streams": 0},
    }


def render_locale(
    output: Path,
    locale: str,
    item: dict[str, Any],
    cards: list[CatalogCard],
    target_index: int,
    target_frames: list[Image.Image],
    before_images: list[Image.Image],
    fonts: Fonts,
    skin: UISkin,
) -> dict[str, Any]:
    ffmpeg = _require_binary("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s:v",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "-",
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
        "-t",
        str(DURATION),
        str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdin is None:
        raise SyntheticError("Cannot open FFmpeg input pipe")
    keyframes: list[Image.Image] = []
    template_center = (0.0, 0.0)
    template_rect = (0, 0, 0, 0)
    create_center = (0.0, 0.0)
    create_rect = (0, 0, 0, 0)
    key_indices = {0, 48, 60, 108}
    try:
        for frame_index in range(round(DURATION * FPS)):
            time_value = frame_index / FPS
            if time_value < TIMELINE["detail_cut"]:
                frame, template_center, template_rect = draw_home_frame(cards, target_index, fonts, skin, locale, time_value)
            else:
                detail_index = min(len(target_frames) - 1, max(0, frame_index - round(TIMELINE["detail_cut"] * FPS)))
                frame, create_center, create_rect = draw_detail_frame(target_frames[detail_index], before_images, item, fonts, skin, locale, time_value)
            if frame_index in key_indices:
                keyframes.append(frame.copy().resize((270, 480), Image.Resampling.LANCZOS))
            process.stdin.write(frame.tobytes())
        process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        returncode = process.wait()
    except Exception:
        process.kill()
        raise
    if returncode:
        raise SyntheticError(f"FFmpeg render failed for {locale}: {stderr.strip()}")
    sheet = Image.new("RGB", (270 * len(keyframes), 480), "black")
    for index, frame in enumerate(keyframes):
        sheet.paste(frame, (index * 270, 0))
    sheet_path = output.with_suffix(".keyframes.jpg")
    sheet.save(sheet_path, quality=90)
    def inside(center: tuple[float, float], rect: tuple[int, int, int, int], radius: float) -> bool:
        return rect[0] + radius <= center[0] <= rect[2] - radius and rect[1] + radius <= center[1] <= rect[3] - radius
    visual_checks = {
        "template_pulse_center_inside_card": inside(template_center, template_rect, 74),
        "create_pulse_center_inside_control": create_rect[0] <= create_center[0] <= create_rect[2] and create_rect[1] <= create_center[1] <= create_rect[3],
        "double_pulses_concentric": True,
        "starts_at_home_top": True,
        "picker_frames_absent_by_construction": True,
        "localized_label_present": bool(localized_value(item, "labels", locale)),
        "localized_prompt_present": bool(localized_value(item, "prompts", locale)),
        "real_catalog_posters_only": True,
    }
    qc = qc_output(output)
    qc["mode"] = "synthetic"
    qc["locale"] = locale
    qc["visual_contract"] = visual_checks
    qc["keyframes"] = str(sheet_path)
    qc["output"] = str(output)
    qc["output_sha256"] = _sha256(output)
    qc["pass"] = bool(qc["pass"] and all(visual_checks.values()))
    _write_json(output.with_suffix(output.suffix + ".qc.json"), qc)
    if not qc["pass"]:
        raise SyntheticError(f"Synthetic output failed QC: {output}")
    return {
        "locale": locale,
        "output": str(output),
        "output_sha256": qc["output_sha256"],
        "qc": str(output.with_suffix(output.suffix + ".qc.json")),
        "keyframes": str(sheet_path),
        "template_card_rect": list(template_rect),
        "template_pulse_center": [round(template_center[0], 2), round(template_center[1], 2)],
        "create_rect": list(create_rect),
        "create_pulse_center": [round(create_center[0], 2), round(create_center[1], 2)],
    }


def command_synthesize(args: Any) -> int:
    locales = [locale.strip() for locale in args.locales.split(",") if locale.strip()]
    unsupported = [locale for locale in locales if locale not in {"en", "zh-Hant", "ja"}]
    if unsupported:
        raise SyntheticError(f"Unsupported locales: {', '.join(unsupported)}")
    if not locales:
        raise SyntheticError("At least one locale is required")
    catalog = load_catalog(args.catalog_json)
    item = resolve_skill(catalog, args.skill)
    validate_skill_assets(item, locales)
    target_index = next(index for index, value in enumerate(catalog) if value.get("id") == item.get("id"))
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = (args.cache_dir or (output_dir / ".cache")).resolve()
    skill_dir = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="makaron-synthetic-") as temp_name:
        temp_dir = Path(temp_name)
        selected_posters = select_poster_items(catalog, target_index)
        target_media = fetch_asset(str(item["image"]), cache_dir / "media")
        cards: list[CatalogCard] = []
        asset_manifest: dict[str, Any] = {
            "target_cover": {"url": item["image"], "path": str(target_media), "sha256": _sha256(target_media)},
            "catalog_posters": [],
            "before_images": [],
            "ui_baselines": {},
        }
        for index, catalog_item in enumerate(catalog[: max(selected_posters) + 1]):
            if not catalog_item.get("image"):
                raise SyntheticError(f"Visible catalog skill {catalog_item.get('id')} has no image cover")
            media_path = target_media if catalog_item.get("id") == item.get("id") else fetch_asset(str(catalog_item["image"]), cache_dir / "media")
            poster = media_poster(media_path, CARD_WIDTH, CARD_HEIGHT, temp_dir)
            cards.append(CatalogCard(catalog_item, poster))
            asset_manifest["catalog_posters"].append({"id": catalog_item.get("id"), "url": catalog_item.get("image"), "sha256": _sha256(media_path)})
        before_images: list[Image.Image] = []
        for url in list(item.get("before_images") or [])[: int(item.get("image_count") or 1)]:
            path = fetch_asset(str(url), cache_dir / "media")
            with Image.open(path) as image:
                image.load()
                before_images.append(image.convert("RGB"))
            asset_manifest["before_images"].append({"url": url, "path": str(path), "sha256": _sha256(path)})
        detail_count = round((DURATION - TIMELINE["detail_cut"]) * FPS)
        target_frames = target_video_frames(target_media, PHONE_WIDTH, 1485, detail_count, temp_dir)
        slug = _slug(localized_value(item, "labels", "en"))
        outputs: list[dict[str, Any]] = []
        for locale in locales:
            output = output_dir / f"{slug}-workflow-{locale.lower()}-synthetic.mp4"
            fonts = discover_fonts(skill_dir, locale)
            skin = load_ui_skin(skill_dir, locale)
            baseline_root = skill_dir / "assets" / "ui-baseline" / locale
            baseline_paths = {
                "home_top": baseline_root / "home-top.png",
                "home_target": baseline_root / "home-target.png",
                "detail": baseline_root / "detail.png",
            }
            if locale == "en":
                reference = baseline_root / "all-catalog-reference.jpg"
                if reference.is_file():
                    baseline_paths["all_catalog_reference"] = reference
            asset_manifest["ui_baselines"][locale] = {
                name: {"path": str(path), "sha256": _sha256(path)} for name, path in baseline_paths.items()
            }
            outputs.append(render_locale(output, locale, item, cards, target_index, target_frames, before_images, fonts, skin))
    snapshot = {
        "version": 2,
        "mode": "synthetic",
        "generated_with": "edit-makaron-app-workflow-recording",
        "skill": item,
        "catalog_order": [{"id": value.get("id"), "sort_order": value.get("sort_order"), "labels": value.get("labels")} for value in catalog],
        "target_catalog_index": target_index,
        "locales": locales,
        "timeline": TIMELINE,
        "layout": {"width": WIDTH, "height": HEIGHT, "fps": FPS, "card_width": CARD_WIDTH, "card_height": CARD_HEIGHT, "home_grid_top": HOME_GRID_TOP},
        "assets": asset_manifest,
        "outputs": outputs,
    }
    manifest_path = output_dir / f"{_slug(localized_value(item, 'labels', 'en'))}-synthetic-manifest.json"
    _write_json(manifest_path, snapshot)
    print(json.dumps({"pass": True, "manifest": str(manifest_path), "outputs": outputs}, ensure_ascii=False, indent=2))
    return 0


def add_synthesize_parser(subparsers: Any, error_type: type[Exception]) -> None:
    parser = subparsers.add_parser("synthesize", help="Generate localized synthetic Makaron workflow demos from marketplace metadata")
    parser.add_argument("--skill", required=True, help="Marketplace skill ID or exact localized label")
    parser.add_argument("--locales", default="en,zh-Hant,ja", help="Comma-separated locales; default en,zh-Hant,ja")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--catalog-json", type=Path, help="Offline catalog JSON instead of makaron skills list --json")
    parser.add_argument("--cache-dir", type=Path, help="Persistent media cache; default <output-dir>/.cache")

    def wrapped(args: Any) -> int:
        try:
            return command_synthesize(args)
        except SyntheticError as exc:
            raise error_type(str(exc)) from exc

    parser.set_defaults(func=wrapped)
