# Reference editing rhythm

Use these measurements only to tune pacing and QC. Do not copy the supplied subjects, generated effects, music, or localized copy into another campaign.

The three user-supplied finished ads were inspected with stream metadata, one-second contact sheets, and scene-change detection. Boundaries are approximate:

| Reference | Locale | Total | Hook | Comparison | Workflow | Result | Logo CTA |
|---|---|---:|---:|---:|---:|---:|---:|
| Lens Sign | English | 15.27s | 0–2.5s | 2.5–5s | 5–9s | 9–12.27s | 12.27–15.27s |
| Street Paparazzi | Japanese | 19.00s | 0–2.5s | 2.5–5s | 5–9s | 9–about 16s | about 16–19s |
| Photo Peel | Cantonese | 18.50s | 0–5s | 5–7.5s | about 7.5–11.5s | about 11.5–16.5s | 16.5–18.5s |

Apply the supported common pattern:

- Keep the five-part order fixed.
- Use a 2.5-second Hook by default. Extend it to 5 seconds only when the physical action or transformation mechanism is not legible in 2.5 seconds.
- Generate one continuous target-Skill Effect, then extract Hook from its opening range and Result from a later non-overlapping range. The ranges must share the same Effect hash but never reuse, reverse, freeze, loop, or retime the same source frames.
- Keep the simultaneous Before/After comparison at about 2.5 seconds.
- Keep the locale-correct workflow demonstration at about 4 seconds.
- Let the full result occupy 3–7 seconds, using the shortest complete payoff without repetition.
- Keep the final ad between 15 and 20 seconds, preferring about 18 seconds rather than forcing every Skill to the same duration.
- Append a continuous 2–3 second Logo CTA inside the same Makaron Remotion composition. The references begin at the supplied CTA source's 0-second frame, so the bundled default is 0–3 seconds.
- Create Seed Audio first, derive Caption JSON timing from the real audio, and make scene boundaries contain the complete assigned lines: line 1 Hook, line 2 comparison, lines 3–4 workflow, line 5 result. No speech or subtitle crosses into another scene or CTA.
- For Meta Reels use ratios equivalent to top `250/1920`, bottom `340/1920`, left `90/1080`, and right `180/1080`; start captions at `270/1920` of canvas height or lower. These resolve to 250/340/90/180px and y=270 on 1080×1920, but must be recalculated for any other preview size. The former fixed 140px position is only for a non-Meta template because it falls under Meta account UI.
- Use one subtitle track only: white text, black outline, no background bar, at most two lines and 20 visible characters per line, with measured wrapping inside the safe zone.

The examples demonstrate rhythm, not a license to reuse their people, effect outputs, or audio.
