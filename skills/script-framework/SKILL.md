---
name: script-framework
description: Generate locked five-beat voiceover JSON for the English, Japanese, and/or Hong Kong Cantonese locales selected by makaron-ad-creator. Use only as its script node or when repairing selected-locale copy.
---

# Script Framework

Accept `target_skill.name`, factual `target_skill.core`, transformation type, supported offer, and selected locales. Return exactly five non-empty strings under each selected key and do not return unselected locale keys.

Use these beats in order: surprising result hook; one ordinary photo; Open Makaron; Use the template; emotional result. Keep line 2 under 2.3 spoken seconds. Adapt Japanese and Cantonese culturally; do not translate literally. Do not invent a feature, price, rating, endorsement, urgency, or claim.

Use the locked script prompt in the main Skill's `scripts/makaron_ad_creator/prompts.py`. Save the exact result as `scripts.json`. Invalid JSON or a locale with anything other than five lines is `REROLL`; three failures or unsupported claims are `BLOCKED`.
