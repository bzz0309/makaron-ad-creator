# Legacy picker-visible mode

Use this mode only when the human explicitly requests visible photo selection.
The default workflow removes all picker frames.

## Segment order

1. Localized home page and template tap.
2. Photo picker, intended selection, and confirmation.
3. Stable template detail and Create action.

## Privacy rules

Blur only the actual photo-grid rectangles. Keep navigation, album tabs,
permission notices, confirmation buttons, and other controls readable. Restore
only the intended selected thumbnail cells after selection becomes visible.

Measure every rectangle in original-source pixels and every ripple in final
output pixels. If the picker scrolls or changes layout, use separate blur regions
and time windows. Never restore unrelated personal thumbnails.

## Four-second allocation

- Home discovery and template tap: `0.7–0.9s`.
- Picker selection and confirmation: `1.0–1.3s`.
- Detail and Create: `1.9–2.2s`.

Speed up picker hesitation while preserving visible cause and effect. If privacy
cannot be isolated, stop and request a safer recording.
