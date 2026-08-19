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

A fixed CTA must live inside the npm-distributed master Skill, not at a contributor-specific Desktop path. Store the complete source once, record its hash in provenance, expose the local post-process in Agent requests, and append only the configured 2–3 second continuous excerpt with deterministic FFmpeg composition. Keep target-locale TTS out of that branded segment and never ask a generative model to reproduce the logo.

## Derive timing ranges from multiple finished references

Do not turn one finished ad into a universal frame chart. Measure several examples, keep the common order fixed, and encode only stable ranges: Hook 2.5–5 seconds, comparison about 2.5 seconds, workflow about 4 seconds, result 3–7 seconds, CTA 2–3 seconds, and total 15–20 seconds. Let mechanism clarity—not locale alone—choose the exact duration.
