# Reusable methods

## Put state in the CLI, judgment in the Agent

Long creative chains become reliable when the CLI owns the DAG, dependencies, attempts, artifacts, hashes, and resume point. An Agent receives one bounded request at a time and cannot silently skip steps.

## Separate ad language from UI language

Voiceover/subtitles use a selected subset of `en`, `ja`, and `yue`; app workflow uses the corresponding Marketplace UI locales. Keep `en→en`, `ja→ja`, and `yue→zh-Hant` explicit in config and lineage, and generate no unselected workflow or final nodes.

## Retry nodes, not campaigns

Lock passed inputs. Retry only the failed generative node in `seedance-fast → kling → grok` order. Reset downstream dependents only when an upstream artifact changes.

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

## Derive timing ranges from multiple finished references

Do not turn one finished ad into a universal frame chart. Measure several examples, keep the common order fixed, and encode only stable ranges: Hook 2.5–5 seconds, comparison about 2.5 seconds, workflow about 4 seconds, result 3–7 seconds, CTA 2–3 seconds, and total 15–20 seconds. Let mechanism clarity—not locale alone—choose the exact duration.
