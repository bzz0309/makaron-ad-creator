# Synthetic mode reference

## Contents

1. Input contract
2. Marketplace field resolution
3. Version 2 manifest
4. Rendering and cache behavior
5. Failure modes

## Input contract

```bash
python3 scripts/workflow_recording.py synthesize \
  --skill <id-or-label> \
  --locales en,zh-Hant,ja \
  --output-dir <dir> \
  [--catalog-json <catalog.json>] \
  [--cache-dir <cache-dir>]
```

- `--skill`: exact marketplace UUID or exact value from any `labels` entry.
- `--locales`: comma-separated subset of `en,zh-Hant,ja`.
- `--output-dir`: receives MP4, keyframe sheets, QC JSON, and the run manifest.
- `--catalog-json`: bypasses `makaron skills list --json` and makes the run
  reproducible or offline.
- `--cache-dir`: stores downloaded cover and before-image media. The default is
  `<output-dir>/.cache`.

The synthetic renderer requires Pillow plus FFmpeg/FFprobe. It uses curl for
HTTP downloads when available and verifies every cached asset is decodable
before reuse.

## Marketplace field resolution

Sort the complete catalog by ascending `sort_order`, with ID as the stable tie
breaker. Resolve the target by ID first. Label matches must be exact and unique.

For each requested locale:

```text
display name = labels[locale]
prompt       = prompts[locale]
```

For `zh-Hant` only, allow fallback to `labels.zh` and `prompts.zh`. For English,
allow the flat `label` and `prompt` only as compatibility fallbacks. Do not use
English text in Japanese output.

Use `image` as both the target home-card media and animated detail cover. Use
the first `image_count` values from `before_images` as the already-selected
input thumbnails. Fail rather than duplicating or inventing missing inputs.

## Version 2 manifest

Each run writes `<english-slug>-synthetic-manifest.json`:

```json
{
  "version": 2,
  "mode": "synthetic",
  "skill": {},
  "catalog_order": [],
  "target_catalog_index": 12,
  "locales": ["en", "zh-Hant", "ja"],
  "timeline": {},
  "layout": {},
  "assets": {
    "target_cover": {"url": "...", "path": "...", "sha256": "..."},
    "catalog_posters": [],
    "before_images": []
  },
  "outputs": []
}
```

Every output entry records the template card rectangle, template pulse center,
Create rectangle, Create pulse center, output hash, QC path, and keyframe sheet.
This is the source of truth for coordinate debugging; synthetic coordinates
must never be copied from an earlier video.

## Rendering and cache behavior

- Use the actual catalog index to calculate the target row and scroll distance.
- Decode every home-card poster that can enter the viewport from the initial
  home top through the target row. Keep all items in their true order and stop
  explicitly if a visible cover is unavailable; never synthesize a tile.
- Decode and loop the full target cover for the detail segment. Add a subtle
  push-in only when the target cover is a static image.
- Prefer the platform San Francisco/Hiragino family and use bundled Noto Sans
  CJK only as the portable fallback. Wrap cards and prompts by pixel width with
  at most two lines.
- Keep the status bar, safe-area width, bottom navigation, card geometry,
  detail panel, and interaction timeline fixed across locales.
- A failed visible poster is a hard failure for every item, including
  historical non-target cards.

The bundled English home calibration is derived from the complete sequential
iPhone capture of the `All` category supplied by the user. It defines the real
home header crop, grid measurements, scroll density, status chrome, and bottom
navigation. Live catalog order and media remain data-driven so future Skills
do not require another manual capture.

Use `assets/ui-baseline/en/all-catalog-reference.jpg` for compact visual
regression against the full English `All` sequence. It is a calibration sheet,
not a catalog-data substitute.

## Failure modes

| Error | Meaning | Action |
|---|---|---|
| `Skill not found` | ID/label is absent | Refresh catalog or use the marketplace UUID |
| `Skill label is ambiguous` | Multiple localized labels match | Use the listed UUID |
| `missing labels/prompts` | Requested localization is unavailable | Fix marketplace metadata; do not substitute another language |
| `needs N before_images` | Detail cannot represent a ready-to-create state | Add the missing marketplace input references |
| `Downloaded asset is not decodable` | CDN response is incomplete or invalid | Delete bad cache entry and rerun; downloader verifies redownloads |
| QC failure | Codec, duration, dimensions, rate, audio, or layout contract failed | Do not deliver; inspect QC and keyframe sheet |
