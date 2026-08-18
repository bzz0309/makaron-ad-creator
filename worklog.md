# Worklog

## 2026-08-18

- Audited `makaron-ad-creator-v6.1` and the newer v5 iOS workflow-recording package.
- Chose CLI state machine + master Skill + child-node Skills.
- Replaced contradictory hard-coded/auto project behavior with a registry-enforced persistent binding.
- Defined final locales `en/ja/yue` and UI mapping `en/ja/zh-Hant`.
- Integrated the supplied metadata-driven synthetic workflow renderer and UI baseline assets.
- Implemented resumable Makaron and cross-Agent executors, deterministic After/comparison nodes, retries, technical QC, lineage, and human publication gate.
- Passed 6 unit/integration-boundary tests, all five Skill validators, CLI doctor, direct CLI Agent-handoff smoke test, and a full offline synthetic render for `en`, `ja`, and `zh-Hant` (all renderer QC PASS).
- Verified the installed Makaron CLI help and removed the obsolete/invalid `--video-model` flag from direct commands.
- Clarified source provenance: `social-ad-creator` was an environment-level reference Skill, not part of the user's zip. Removed it from project dependencies and source claims.
- Restored the user's original five-directory package shape. Replaced `edit-makaron-app-workflow-recording` with the supplied v5 iOS package and verified a zero-diff comparison against the extracted source.
- Added the public two-argument entrypoint: `makaron-ad <image> "<Marketplace Skill name>"`. Skill lookup, ID/core resolution, dedicated project creation/reuse, campaign configuration, and execution are internal.
- Re-ran the v5 renderer for `en`, `ja`, and `zh-Hant`; all three outputs passed with deterministic hashes matching the prior smoke run.
- Prepared the complete project-documentation set and public GitHub initial release at `bzz0309/makaron-ad-creator`; temporary renders, generated campaigns, caches, and credentials are excluded from version control.

## Open integration items

- Run a rights-cleared live campaign against an authorized Makaron project.
- Confirm live response payload parsing against an authorized generation. The installed CLI rejects explicit model flags, so retry model order is recorded as a routing preference in the locked prompt; response polling uses documented `--wait --materialize --json` with fallbacks.
- Optionally publish/install the master and builder Skills after explicit approval.
