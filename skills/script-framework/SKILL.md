---
name: script-framework
description: Generate locked five-beat voiceover JSON for the English, Japanese, and/or Hong Kong Cantonese locales selected by makaron-ad-creator. Use only as its script node or when repairing selected-locale copy.
---

# Script Framework

Accept `target_skill.name`, factual `target_skill.core`, transformation type, supported offer, and selected locales. Return exactly five non-empty strings under each selected key and do not return unselected locale keys.

Use these beats in order: surprising result hook; one ordinary photo; open Makaron; select the effect; emotional result. Write the whole script as one first-person testimonial from the user or creator who supplied the photo. The speaker describes their own input, actions, and result; never refer to the depicted subject as a detached he/she/they, 佢, 彼, or 彼女. Lines 3 and 4 describe what the speaker did, not commands to the viewer. English uses `I/my`, Cantonese uses `我/我嘅`, and Japanese establishes an explicit first-person speaker at least once before naturally omitting the pronoun. Keep line 2 under 2.3 spoken seconds. Adapt Japanese and Cantonese culturally; do not translate literally. Do not invent a feature, price, rating, endorsement, urgency, or claim.

Use the locked script prompt in the main Skill's `scripts/makaron_ad_creator/prompts.py`. Save the exact result as `scripts.json`. Invalid JSON or a locale with anything other than five lines is `REROLL`; three failures or unsupported claims are `BLOCKED`.
