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
- Added npm/npx distribution matching the music-library CLI pattern: `npx -y makaron-ad-creator-cli setup` installs the global command, portable media binaries, private Python/Pillow runtime, Makaron CLI dependency, and only the master Agent Skill.
- Added global `makaron-ad` commands for login, credits, doctor, two-input creation, and resumable internal operations. The existing tested Python DAG remains the orchestration core.
- Passed npm smoke tests, 7 Python tests, all five Skill validators, package-content inspection, v5 zero-diff verification, and isolated tarball installation with `doctor.ok=true`.
- Confirmed `makaron-ad-creator-cli` is not currently claimed on the public npm registry. This computer is not authenticated to npm, so registry publication remains the only distribution release step.

## Open integration items

- Run a rights-cleared live campaign against an authorized Makaron project.
- Confirm live response payload parsing against an authorized generation. The installed CLI rejects explicit model flags, so retry model order is recorded as a routing preference in the locked prompt; response polling uses documented `--wait --materialize --json` with fallbacks.

## 2026-08-19

- Added end-to-end locale selection with `--locale en`, `--locale ja`, `--locale yue`, `--locale en,ja`, or the default `all`.
- Made the DAG, script JSON, synthetic workflow rendering, final generation, QC, review CSV, provenance, and delivery operate only on selected locales.
- Locked UI mapping as `en→en`, `ja→ja`, and `yue→zh-Hant`; added regression coverage for Cantonese-only generation.
- Updated the Before prompt from the supplied change list to keep scenes naturally bright and unpolished while preserving source skin tone and avoiding invented severe defects or degrading treatment.
- Added the supplied fashion direction as an adult-person-only conditional rule so it cannot be applied to minors, age-ambiguous people, products, nonhuman subjects, or unrelated transformations.
- Bundled the user-supplied 10.10-second Makaron Logo CTA source in the npm-distributed master Skill with an identical SHA-256 copy.
- Locked every final edit to Hook video → comparison image → locale-correct workflow video → effect/result video → fixed Logo CTA video, with explicit cross-Agent input roles.
- Changed default target-locale TTS to a natural energetic young-adult female voice, ending before the CTA while preserving the CTA excerpt's original audio.
- Moved Logo CTA assembly out of the generative node: Makaron/another Agent now returns the four-part body and the CLI appends the fixed CTA locally with FFmpeg, preventing brand drift.
- Analyzed three supplied finished ads (English Lens Sign, Japanese Street Paparazzi, and Cantonese Photo Peel). Changed the fixed CTA default to the source's observed 0–3 second opening, and replaced the forced 18-second edit with a 15–20 second adaptive envelope: 2.5–5 second Hook, about 2.5 second comparison, about 4 second workflow, and a complete 3–7 second result.
- Bumped the release candidate to `0.4.0`; passed 16 npm/Python tests, deterministic CTA append integration, package dry-run inspection, and Skill validation.
- Received explicit approval to push and publish `0.4.0`. Repeated `npm ci`, all 16 tests, package inspection, and an isolated tarball install under a restricted PATH; the installed CLI reported `0.4.0` and `doctor.ok=true` using its bundled Makaron CLI, FFmpeg, FFprobe, v5 workflow Skill, and fixed Logo CTA.
- Began the post-`0.4.0` audio-pipeline revision from the user's updated requirement and three finished-ad references. Added one resumable campaign-level `bgm` node using `makaron music create`, requiring an at-least-20-second original instrumental with no early fade-out and preserving its public source URL for long-audio chat attachment.
- Replaced the `0.4.0` local CTA/audio post-process contract. Each locale now sends comparison + effect + localized workflow + fixed CTA + BGM + five lines through one bound-project `makaron chat`; the Agent must drive internal Remotion for all source muting, Seed Audio young-female TTS, synchronized top-safe subtitles, CTA trim, continuous BGM at `0.22`, and direct final MP4 export. CTA source audio is forbidden and local edge-tts/FFmpeg concat-amix/ASS/PIL final composition is removed.
- Made rollback preservation a release invariant: keep the outgoing npm version and Git tag/Release immutable, assign npm `previous` before updating `latest`, attach the packed tarball plus checksum to each GitHub Release, and publish concrete rollback commands.
- Read the supplied legacy `makaron-ad-video-builder/SKILL.md` as a reference. Adopted its Remotion/Seed Audio/subtitle/BGM lessons while deliberately retaining the current project's 1080×1920 output, per-Skill persistent project binding, v5 synthetic localized workflow, and no-`auto` rule instead of importing contradictory legacy settings.
- Published `makaron-ad-creator-cli@0.5.0`, Git tag/Release `v0.5.0`, and npm rollback tag `previous=0.4.0`; the GitHub Release includes the exact npm tarball and checksum.
- During the rights-cleared Crystal Ballet English integration campaign, live generation succeeded but Python's private CA store blocked an Evolink artifact download. Version `0.5.1` now prefers the system `curl` trust store, retries transient transfers, validates non-empty output, and atomically installs downloads; regression coverage passes.
- Added one-time persistent CLI login. `makaron-ad login` validates the supplied key and saves it in macOS Keychain; later Agent runs automatically inject it, while `makaron-ad logout` removes it. Credentials remain outside project files, logs, and Git.
- Completed the rights-cleared Crystal Ballet English integration campaign. The pipeline generated script, Before, target-Skill effect, 21.5-second original BGM, After, comparison, English synthetic workflow, Seed Audio voiceover, synchronized subtitles, and an 18.048-second 1080×1920 H.264/AAC final; technical QC passed, including continuous BGM through the silent-source CTA.
- Fixed a live final-output bug where generic media URL extraction could select the uploaded 10.1-second CTA after Makaron's Remotion exporter returned `Forbidden`. Final nodes now accept only authoritative generated video fields, preflight dimensions/duration/audio/BGM before PASS, and safely render the returned bounded Remotion design with pinned Remotion 4.0.506 when platform materialization is unavailable.

## 2026-08-20

- Diagnosed the Crystal Ballet English timing defect: the second voiceover line extended beyond the comparison beat because scene cuts and subtitles were independently hand-timed. Replaced the contract with Seed Audio first, measured Remotion Caption JSON second, and scene boundaries derived from the complete assigned lines.
- Added an independent target-Skill Hook node. Hook and result are now separate artifacts and the final composition forbids repeated shots, actions, camera paths, or retimed source frames between them.
- Changed video routing to Makaron's canonical `seedance-2-0 → kling → grok`; Seedance 2.0 is used unless the current node fails.
- Kept 1080×1920 as the delivery target while accepting Meta's official 720px Reels minimum as a 720×1280 9:16 fallback floor.
- Defaulted final composition to Makaron's built-in `tiktok-video` Remotion builder and added composition contract v2 validation for five Caption objects, five scene timing ranges, and the fixed line-to-scene mapping before any local fallback render.
- Added the Meta Reels safe-zone profile: top 250px, bottom 340px, left 90px, right 180px, captions at y=270 or lower. Subtitles are one white/black-outline track, no bar, maximum two lines and 20 visible characters per line. The old 140px top offset is explicitly excluded from Meta output.
