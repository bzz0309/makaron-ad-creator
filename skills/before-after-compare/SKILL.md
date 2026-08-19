---
name: before-after-compare
description: Create a respectful ordinary Before image, extract the After frame from a Makaron Skill result video, and compose a deterministic 1080x1920 side-by-side comparison. Use only as the visual-contrast nodes of makaron-ad-creator or to repair those assets.
---

# Before/After Compare

Use the authorized input as the identity/product source. Keep the Before naturally bright and normally exposed, not dark, underexposed, grey, or low-key graded; only ordinary unpolished detail should create the contrast. For an authorized adult person, preserve the exact source skin tone and show restrained realistic texture such as natural pores, mild unevenness or redness where plausible, soft under-eye tiredness, dehydrated microtexture, very low shine, no visible makeup, plainly unstyled hair, natural brows, unpolished lips, simple wrinkled clothing, a tired unposed expression, and an ordinary lived-in bedroom or bathroom corner photographed as a slightly awkward handheld selfie. Do not impose those human appearance instructions on products or nonhuman subjects. Never uglify, invent severe blemishes or disease, humiliate, body-shame, change identity, or alter product facts. The After must come from the actual target-Skill effect video at 82% duration, not a separate unrelated generation.

Compose locally on a black 1080×1920 canvas: equal-width/equal-height panels, 10px central gap, readable white `BEFORE`/`AFTER` labels with black outline, and no cropped head or key product feature. Use `compose_comparison` from the main Skill's `scripts/makaron_ad_creator/media.py`; do not spend model budget on composition.

Return `before.png`, `after.png`, and `comparison.png`. Identity/product loss is `BLOCKED`; recoverable crop or typography is `REROLL`.
