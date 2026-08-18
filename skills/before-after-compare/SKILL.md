---
name: before-after-compare
description: Create a respectful ordinary Before image, extract the After frame from a Makaron Skill result video, and compose a deterministic 1080x1920 side-by-side comparison. Use only as the visual-contrast nodes of makaron-ad-creator or to repair those assets.
---

# Before/After Compare

Use the authorized input as the identity/product source. The Before must look ordinary and unpolished without uglification, invented defects, humiliation, body shaming, identity change, or altered product facts. The After must come from the actual target-Skill effect video at 82% duration, not a separate unrelated generation.

Compose locally on a black 1080×1920 canvas: equal-width/equal-height panels, 10px central gap, readable white `BEFORE`/`AFTER` labels with black outline, and no cropped head or key product feature. Use `compose_comparison` from the main Skill's `scripts/makaron_ad_creator/media.py`; do not spend model budget on composition.

Return `before.png`, `after.png`, and `comparison.png`. Identity/product loss is `BLOCKED`; recoverable crop or typography is `REROLL`.
