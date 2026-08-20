---
name: edit-makaron-app-workflow-recording
description: >-
  Generate polished localized Makaron app workflow demo videos automatically
  from a Makaron Marketplace Skill ID or exact label, or edit genuine iOS and
  Android Makaron recordings when source footage is explicitly supplied. Use
  when the user asks for Makaron 录屏、录屏效果视频、投放素材里的 App 操作片段、三语言
  workflow videos, automatic homepage-to-detail demos, corrected template/Create
  click indicators, or English/Japanese/Traditional-Chinese variants. Default to
  synthetic metadata-driven generation with no human recording: start at the
  localized home-page top, scroll to the real catalog position, add concentric
  white/magenta pulses, hard-cut to a populated detail page, and pulse Create.
---

# Edit Makaron App Workflow Recording

## Master-CLI integration

When this package is orchestrated by `makaron-ad-creator-cli`, do not run the local synthetic renderer. The master CLI supplies this v5 package's locale-correct `home-top`, `home-target`, and `detail` baseline frames to Makaron's public `screen-demo` Skill, and Makaron produces the four-second Remotion workflow artifact in the bound project. The commands below remain available only for standalone compatibility, regression testing, or explicit repair work.

## Choose the mode

Default to `synthetic`. Require only a Marketplace Skill ID or exact label and
generate `en`, `zh-Hant`, and `ja` videos without operating a phone.

Use `recording` only when the user explicitly supplies recordings or asks to
repair footage. Never call a synthetic demo a genuine device recording.

| Mode | Required input | Use |
|---|---|---|
| `synthetic` | Marketplace Skill ID or exact localized label | New automatic workflow demos |
| `recording` | One source recording per locale plus target template | Repairs, legacy footage, or UI states not represented by the synthetic skin |

Both modes export exact `1080x1920`, 30 fps, four-second, muted H.264 MP4s and
write deterministic QC JSON.

## Synthetic quick start

Confirm `python3`, Pillow, FFmpeg/FFprobe, curl, and the Makaron CLI are
available. Then run:

```bash
python3 <skill-dir>/scripts/workflow_recording.py synthesize \
  --skill <marketplace-id-or-exact-label> \
  --locales en,zh-Hant,ja \
  --output-dir <output-dir>
```

Prefer a Skill ID. Label lookup is exact across all localized labels and fails
when ambiguous. Use `--catalog-json <snapshot.json>` for offline or reproducible
runs and `--cache-dir <dir>` to share downloaded cover media across jobs.

The command automatically:

1. reads and sorts the marketplace catalog by `sort_order`;
2. resolves localized `labels` and `prompts`;
3. downloads and hashes `image` and the required `before_images`;
4. renders the localized home top and catalog scroll;
5. computes the target-card pulse center from its layout bounds;
6. hard-cuts past all upload/picker activity to a populated detail layout;
7. computes the Create pulse center from its control bounds;
8. exports MP4, keyframe sheet, QC JSON, and a version 2 manifest.

Read [synthetic-mode.md](references/synthetic-mode.md) when troubleshooting
metadata, caches, localization, long text, missing input images, or catalog
placement.

## Synthetic visual contract

Keep this timeline fixed unless the user asks for a different duration:

```text
0.00–0.25  localized home page at the true top
0.25–1.40  eased scroll to the target's catalog row
1.42–1.76  white outer pulse on the template card
1.47–1.72  magenta inner pulse at the identical center
1.80       clean hard cut
1.80–3.45  animated detail cover with all required inputs populated
3.48–3.82  white outer pulse on Create
3.53–3.78  magenta inner pulse at the identical center
4.00       end
```

Do not accept hand-entered tap coordinates in synthetic mode. The renderer must
derive template and Create centers from the final layout rectangles. Do not add
photo pickers, galleries, upload confirmation, Gaussian blur, transition
residue, crossfades, Control Center, or recorder controls.

Use the bundled UI baseline frames as visual regression references, not as
skill-specific content. Dynamic card covers, detail media, labels, prompts, and
input thumbnails must come from the selected marketplace record.

## Synthetic delivery check

Open every generated `*.keyframes.jpg`, then read the paired `*.mp4.qc.json`.
Deliver only when all technical and `visual_contract` checks pass and the sheet
shows the correct locale, target card, cover, input count, prompt, and Create
control. The generated video contains no hidden picker frames because the
detail view is constructed directly.

If the app UI has materially changed, update the one-time baseline skin from
new approved home-top and detail screenshots. Do not resume manual recording
for every Skill.

## Recording compatibility mode

Preserve the existing version 1 config and commands:

```bash
python3 <skill-dir>/scripts/workflow_recording.py inspect \
  --input <recording.mp4> --out-dir <inspection-dir> --frames 24

python3 <skill-dir>/scripts/workflow_recording.py render \
  --input <recording.mp4> --config <workflow.json> \
  --output <localized-workflow.mp4>

python3 <skill-dir>/scripts/workflow_recording.py validate \
  --input <recording.mp4> --config <workflow.json> \
  --output <localized-workflow.mp4>
```

Read [config-schema.md](references/config-schema.md) before writing a recording
config. Start from [direct-detail-example.json](references/direct-detail-example.json)
for the default two-segment flow. Use [picker-visible-mode.md](references/picker-visible-mode.md)
and [rainy-kiss-example.json](references/rainy-kiss-example.json) only when the
user explicitly requires the picker to remain visible.

For recording mode, inspect every locale independently. Start at the true
localized home top, end the first segment before native transition residue,
start the second only after inputs are already present, and use a hard cut.
Measure pulses on a no-tap final-size draft; never reuse coordinates across
languages or measure from a scaled chat screenshot.

## Failure rules

- Fail when the selected Skill lacks `image`, a requested localized label or
  prompt, or enough `before_images` for `image_count`.
- Allow `zh-Hant` text to fall back to `zh`; do not silently cross languages for
  English or Japanese.
- Fail if any catalog cover that can enter the viewport is missing or cannot
  be decoded. Synthetic mode must never draw a placeholder card.
- Preserve the complete live catalog order from `sort_order`.
- Treat the user-provided complete English `All` category iPhone screenshot
  sequence as the visual authority for the home header, card geometry,
  spacing, corner radii, scroll density, iOS status chrome, and bottom nav.
- Keep source recordings unchanged in recording mode and write only new work
  products.
- Never expose gallery thumbnails, notifications, account data, API keys,
  location data, or recorder UI.
