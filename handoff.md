# Handoff

Repository: `https://github.com/bzz0309/makaron-ad-creator`

Start with `README.md`, then read `AGENT.md` and the master `skills/makaron-ad-creator/SKILL.md`.

The orchestration implementation is bundled inside the main Skill at `skills/makaron-ad-creator/scripts/makaron_ad_creator/`. Public distribution is the npm package `makaron-ad-creator-cli`, whose executable is `bin/makaron-ad.mjs`; `bin/makaron-ad` remains the source-tree fallback. The user-supplied v5 iOS workflow Skill and its UI/font assets are copied unchanged under `skills/edit-makaron-app-workflow-recording/`.

Before live generation, run `npm test`, `npm run pack:check`, and `makaron-ad doctor`. A fresh Mac runs `npx -y makaron-ad-creator-cli setup` and `makaron-ad login` once; the verified key is stored in macOS Keychain and automatically reused by later user or Agent commands. `makaron-ad logout` removes it. A live campaign needs an owned/licensed image and exact Marketplace Skill metadata; the CLI automatically creates or reuses the one authorized persistent project bound to that Skill. Use `--locale en`, `--locale ja`, `--locale yue`, a comma-separated subset, or omit it for all three. The fixed UI mapping is `en→en`, `ja→ja`, `yue→zh-Hant`. One campaign BGM is generated through `makaron music create`; each locale's complete Hook → comparison → workflow → effect → fixed Logo CTA ad is then exported by one project-bound Makaron chat using internal Remotion, Seed Audio TTS, synchronized subtitles, muted source/CTA audio, and the same BGM looped through the end. Accept only authoritative generated videos. When Makaron materialization returns `Forbidden` but a complete design exists, the pinned local Remotion fallback renders that exact design and then runs the same preflight/QC. The complete CTA source is bundled at `skills/makaron-ad-creator/assets/makaron-logo-cta.mp4`. Do not auto-publish completed ads.

Release steps are in `docs/releasing.md`; current open integration items are in `worklog.md`. Version `0.5.0` is released; `0.5.1` is the tested download-trust and persistent-login update. No credentials are stored in this project.
