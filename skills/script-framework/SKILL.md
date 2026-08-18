---
name: script-framework
description: Generate the locked five-beat English, Japanese, and Hong Kong Cantonese voiceover JSON for a Makaron contrast ad. Use only as the script node called by makaron-ad-creator or when repairing that node's locale copy.
---

# Script Framework

Accept `target_skill.name`, factual `target_skill.core`, transformation type, and supported offer. Return exactly five non-empty strings under each of `en`, `ja`, and `yue`.

Use these beats in order: surprising result hook; one ordinary photo; Open Makaron; Use the template; emotional result. Keep line 2 under 2.3 spoken seconds. Adapt Japanese and Cantonese culturally; do not translate literally. Do not invent a feature, price, rating, endorsement, urgency, or claim.

Use the locked script prompt in the main Skill's `scripts/makaron_ad_creator/prompts.py`. Save the exact result as `scripts.json`. Invalid JSON or a locale with anything other than five lines is `REROLL`; three failures or unsupported claims are `BLOCKED`.
