# Handoff

Repository: `https://github.com/bzz0309/makaron-ad-creator`

Start with `README.md`, then read `AGENT.md` and the master `skills/makaron-ad-creator/SKILL.md`.

The orchestration implementation is bundled inside the main Skill at `skills/makaron-ad-creator/scripts/makaron_ad_creator/`. Public distribution is the npm package `makaron-ad-creator-cli`, whose executable is `bin/makaron-ad.mjs`; `bin/makaron-ad` remains the source-tree fallback. The user-supplied v5 iOS workflow Skill and its UI/font assets are copied unchanged under `skills/edit-makaron-app-workflow-recording/`.

Before live generation, run `npm test`, `npm run pack:check`, and `makaron-ad doctor`. A fresh computer runs `npx -y makaron-ad-creator-cli setup` and `makaron-ad login` once. A live campaign needs an owned/licensed image and exact Marketplace Skill metadata; the CLI automatically creates or reuses the one authorized persistent project bound to that Skill. Use `--locale en`, `--locale ja`, `--locale yue`, a comma-separated subset, or omit it for all three. The fixed UI mapping is `en→en`, `ja→ja`, `yue→zh-Hant`. Final assembly is Hook → comparison → workflow → effect → fixed Logo CTA; timing adapts within 15–20 seconds using the measured reference envelope in `references/reference-editing-rhythm.md`. TTS defaults to a young-adult female voice and ends before the CTA. The complete CTA source is bundled at `skills/makaron-ad-creator/assets/makaron-logo-cta.mp4`, so installed Agents do not need the contributor's Desktop file. Do not auto-publish completed ads.

Release steps are in `docs/releasing.md`; current open integration items are in `worklog.md`. Version `0.4.0` is the approved release represented by this checkout. No credentials are stored in this project.
