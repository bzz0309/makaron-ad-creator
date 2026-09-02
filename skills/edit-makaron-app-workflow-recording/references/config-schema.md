# Workflow recording config schema

Use version `1`. Keep all source-space coordinates in the original recording's
pixel grid. Keep tap coordinates in the final output's pixel grid.

## Default direct-detail shape

```json
{
  "version": 1,
  "output": {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "duration": 4.0,
    "crf": 18,
    "preset": "medium",
    "fit": "contain",
    "vertical_anchor": "top"
  },
  "segments": [
    {"source_start": 0.05, "source_end": 2.48, "speed": 1.35},
    {"source_start": 8.0, "source_end": 11.3, "speed": 1.5}
  ],
  "privacy": {
    "blur_regions": []
  },
  "taps": [
    {
      "at": 0.4,
      "x": 260,
      "y": 1255,
      "duration": 0.34,
      "radius": 74,
      "line_width": 9,
      "color": "#FFFFFF",
      "steps": 10
    },
    {
      "at": 0.45,
      "x": 260,
      "y": 1255,
      "duration": 0.25,
      "radius": 52,
      "line_width": 7,
      "color": "#FF2FD1",
      "steps": 8
    }
  ]
}
```

## Fields

### `output`

- `width`, `height`: even-numbered MP4 dimensions. Default delivery is
  `1080x1920`.
- `fps`: output frame rate. Default is `30`.
- `duration`: exact target duration. Default is `4.0` seconds.
- `crf`: H.264 quality. Use `18` for review/delivery.
- `preset`: libx264 preset such as `medium` or `slow`.
- `fit`: `contain` keeps the complete phone screen and is the default for app
  demos; `cover` fills the canvas but crops overflow.
- `vertical_anchor`: for `cover`, use `top`, `center`, or `bottom`. `top` usually
  preserves the iPhone status bar and Dynamic Island.

The renderer always exports H.264, yuv420p, fast-start MP4 with no audio.

### `segments`

List the visible workflow beats in final order. Each item trims the original
recording from `source_start` to `source_end`, then applies `speed`.

Edited duration is `(source_end - source_start) / speed`. Make the sum equal to
the target duration. The renderer can trim a small excess but rejects a large
shortfall.

Default two-segment four-second allocation:

1. Localized home page from its true top, browse, and template mark: `1.7–1.9s`.
2. Stable detail page with the chosen photo already present and Create mark: `2.1–2.3s`.

End segment 1 before the app's native template-to-detail transition begins.
Start segment 2 only after all photo-picker, upload, confirmation, selected-photo
float, and dissolve residue has disappeared. `concat` is a hard cut; do not add a
crossfade to hide excluded user actions.

### `privacy.blur_regions`

In the default direct-detail workflow this list must be empty because gallery
frames are excluded completely.

When the user explicitly requests the legacy picker-visible mode, apply blur
only to actual photo-grid rectangles. Keep navigation, album tabs,
confirmation buttons, permission notices, and other UI controls readable.

- `source_rect`: blur rectangle in original-source pixels.
- `source_time`: original-source time window, not edited-output time.
- `sigma`: Gaussian blur strength; `24–36` is normally sufficient.
- `restore`: original-source rectangles and time windows to copy back sharply
  after blur. Use these for selected input thumbnails only.

If the picker scrolls, splits, or changes layout, use multiple blur regions with
separate time windows. Never restore an unrelated personal thumbnail.

### `taps`

Add a high-contrast white-outer/magenta-inner double pulse rather than a mouse
pointer, hand-drawn annotation, or low-contrast single purple ring. Represent
one interaction with two tap entries that use exactly the same `x,y`.

- `at`: edited-output time.
- `x`, `y`: touch center in final-output pixels.
- `duration`: for the synthetic four-second v5 recording, hold the template ring for at least `0.45s` and the Create/Use ring for at least `0.75s`; inner and outer rings overlap for nearly the whole dwell.
- `radius`: for the synthetic v5 recording, outer is `104–118px`; inner is `74–86px`, so both survive final-video downscaling.
- `line_width`: for the synthetic v5 recording, outer is `14px`; inner is `11px`.
- `color`: outer default `#FFFFFF`; inner default `#FF2FD1`.
- `steps`: optional animation frames, clamped to `4–20`.

Center the template ring well inside the target card image, normally near its
visual center. Do not place it on the card's upper boundary, the gap between
cards, or the label outside the image. Center the Create ring on the visible
word/control rather than its surrounding card or loading chip. Review one frame
at peak radius before delivery.

Example pair:

```json
[
  {"at": 1.52, "x": 330, "y": 1080, "duration": 0.34, "radius": 74, "line_width": 9, "color": "#FFFFFF", "steps": 10},
  {"at": 1.57, "x": 330, "y": 1080, "duration": 0.25, "radius": 52, "line_width": 7, "color": "#FF2FD1", "steps": 8}
]
```

## Coordinate conversion

Do not guess coordinates from a scaled chat screenshot, contact-sheet tile, or
original recording. First render the exact final edit with `taps: []`, then
extract a full-resolution frame from that `1080x1920` draft at the intended
touch time and measure directly on it. This automatically accounts for contain
padding, crop, anchor, segment speed, and scroll state.

For an already-scaled screenshot:

```text
source_x = screenshot_x * source_width / screenshot_width
source_y = screenshot_y * source_height / screenshot_height
```

Tap coordinates are measured after the renderer's final `contain`/`cover`
transform. A source-to-screenshot conversion is only for privacy rectangles,
not for final tap coordinates.

## QC contract

An output passes deterministic QC only when it is:

- exact configured dimensions;
- within 0.05 seconds of configured duration;
- exact configured frame rate within 0.01 fps;
- H.264 video;
- muted with no audio stream.

Visual review must additionally confirm: correct locale starts at the true home
page top, correct template, no picker/upload/confirmation/residue frames, detail
photo is already present, readable controls, no tap ring crossing a card/control
boundary, clean hard cut, no Control Center, and no accidental freeze.
