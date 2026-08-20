# Reusable methods

## Put state in the CLI, judgment in the Agent

Long creative chains become reliable when the CLI owns the DAG, dependencies, attempts, artifacts, hashes, and resume point. An Agent receives one bounded request at a time and cannot silently skip steps.

## Separate ad language from UI language

Voiceover/subtitles use a selected subset of `en`, `ja`, and `yue`; app workflow uses the corresponding Marketplace UI locales. Keep `en→en`, `ja→ja`, and `yue→zh-Hant` explicit in config and lineage, and generate no unselected workflow or final nodes.

## Retry nodes, not campaigns

Lock passed inputs. Retry only the failed generative node in `seedance-2-0 → kling → grok` order. Reset downstream dependents only when an upstream artifact changes.

## Keep evidence with every artifact

Persist prompt, command shape, response ID, local path, SHA-256, size, project binding, and node dependency. This makes handoff and failure recovery deterministic.

## Distinguish synthetic demos from recordings

Metadata-driven UI animation is appropriate for scalable workflow proof, but must not be represented as genuine device footage. Genuine recordings remain a separate compatibility mode.

## Separate distribution from orchestration

Use a small Node launcher for `npx` installation, runtime discovery, Agent Skill installation, and authentication passthrough. Keep the tested Python DAG as the orchestration core. This gives a one-command cross-machine setup without rewriting campaign behavior or requiring users to manage Python dependencies.

## Bundle fixed brand assets at the public entrypoint

A fixed CTA must live inside the npm-distributed master Skill, not at a contributor-specific Desktop path. Store the complete source once, record its hash in provenance, and pass it to the project-bound Remotion final node with an explicit trim range. Mute CTA source audio, finish locale TTS before it, and keep the same campaign BGM playing through it. Never ask a generative model to redraw the logo.

## Separate music creation from the localized final render

Generate one instrumental campaign BGM with `makaron music create`, retain both its downloaded artifact and public source URL, and reuse it for every locale. Then use one project-bound Makaron chat per locale to drive internal Remotion for source muting, Seed Audio voiceover, synchronized subtitles, timing, CTA placement, continuous BGM looping, and direct MP4 export. This avoids local edge-tts/ASS/amix drift while keeping the two-input public CLI unchanged.

## Release rollback invariant

Treat every published npm version and matching Git tag/Release as immutable. Before promoting a new `latest`, assign the npm `previous` dist-tag to the outgoing version. Publish the packed tarball plus SHA-256 checksum on the matching GitHub Release, and document both npm rollback and source recovery commands there. Never force-move or delete release tags to simulate a rollback.

## Persist credentials in the operating-system keychain

Do not make long-running or resumable Agents request the same API key for every process. Verify it once, store it in the current user's macOS Keychain, and inject it only into child-process memory. Environment variables can override the saved credential for automation, and logout must delete the keychain item. Never put a live key in command documentation, project JSON, state, logs, tests, or Git.

## Distinguish generated outputs from uploaded attachments

Media URLs found anywhere in an Agent response are not automatically outputs: prompts, events, and response payloads can repeat source-attachment URLs. Final delivery must come from authoritative generated video fields such as `output[type=video]` or `result.videos`. If the Agent returns a complete Remotion design but platform materialization fails, validate the bounded composition and render that same design with pinned Remotion dependencies; keep local TTS, subtitle reconstruction, and FFmpeg audio assembly forbidden.

## Derive timing ranges from multiple finished references

Do not turn one finished ad into a universal frame chart. Measure several examples, keep the common order fixed, and encode only stable ranges: Hook 2.5–5 seconds, comparison about 2.5 seconds, workflow about 4 seconds, result 3–7 seconds, CTA 2–3 seconds, and total 15–20 seconds. Let mechanism clarity—not locale alone—choose the exact duration.

## Derive scene cuts from narration, not guessed frames

Generate the continuous Seed Audio take first, retain Caption JSON with measured `startMs`/`endMs`, and make scene boundaries contain their assigned lines. A scene may expand to fit natural speech; a subtitle or spoken line must never spill into the next semantic beat. Require a machine-readable timing contract before accepting a locally rendered Remotion fallback.

## Derive Hook and Result from one target-Skill Effect

Invoke the target Skill once for one continuous Effect source. Extract the opening Hook and later Result as exact non-overlapping ranges, preserve the Effect SHA-256 in both artifact records, and reject missing or overlapping provenance during QC. This avoids a second generation drifting away from the selected Skill while still preventing repeated source frames in the final edit.

## Treat platform minimum and delivery target separately

For Meta Reels, target 1080×1920 but accept 720×1280 as the hard 9:16 floor. Keep key content inside the Meta overlay-safe center; a generic 140px top caption offset is not Meta-safe on a 1080×1920 canvas.

## Select evidence frames by visual quality, not timeline percentage

An After image should be an exact decoded frame from the effect result, but its timestamp must be chosen after examining the whole clip. Reject transitions, blur, black frames, incomplete transformations, identity drift, UI, text, and watermark contamination. A hard-coded percentage such as 82% is only a timing guess and is not a creative-quality rule.

## Require authoritative generated images as well as videos

Uploaded source attachments can reappear in generic response URL lists. For Before, After, and comparison nodes, accept only authoritative generated-image fields. For localized workflows, run the bundled v5 synthetic renderer and require its MP4, keyframe sheet, QC JSON, and version-2 manifest. This prevents an input attachment or an unrelated generic workflow design from silently satisfying the node.

## Keep large final inputs URL-native

When an upstream cloud generation already has an authoritative public URL, store and reuse it instead of download-then-upload. Some Agent sandboxes cannot reach the Supabase/Cloudflare signed-URL PUT route used for local video/audio attachments. For unavoidable local assets, use the backend upload endpoint once, key the cache by content SHA-256, and pass the returned CDN URL to chat. Keep small images on the CLI's base64 path when available.

## Bind persistent-project designs to the current campaign

A long-lived project can contain visually similar media and music from earlier campaigns. Attachment order in the prompt is not enough: validate and overwrite the Remotion media props with the exact current campaign URLs before rendering, then retain an asset-binding manifest. This is deterministic correction of declared inputs, not creative regeneration.
