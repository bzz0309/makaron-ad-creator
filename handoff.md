# Handoff

Repository: `https://github.com/bzz0309/makaron-ad-creator`

Start with `README.md`, then read `AGENT.md` and the master `skills/makaron-ad-creator/SKILL.md`.

The implementation is bundled inside the main Skill at `skills/makaron-ad-creator/scripts/makaron_ad_creator/`; the executable is `bin/makaron-ad`. The user-supplied v5 iOS workflow Skill and its UI/font assets are copied unchanged under `skills/edit-makaron-app-workflow-recording/`.

Before live generation, run the unit tests and `bin/makaron-ad doctor`. A live campaign needs an owned/licensed image, exact Marketplace Skill metadata, and an explicitly authorized persistent Makaron project ID. Do not create or publish external state implicitly.

Current open items and compatibility notes are in `worklog.md`. No credentials are stored in this project.
