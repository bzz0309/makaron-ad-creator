# Reusable methods

## Put state in the CLI, judgment in the Agent

Long creative chains become reliable when the CLI owns the DAG, dependencies, attempts, artifacts, hashes, and resume point. An Agent receives one bounded request at a time and cannot silently skip steps.

## Separate ad language from UI language

Voiceover/subtitles use `en`, `ja`, and `yue`; app workflow uses Marketplace UI locales `en`, `ja`, and `zh-Hant`. Keep the mapping explicit in config and lineage.

## Retry nodes, not campaigns

Lock passed inputs. Retry only the failed generative node in `seedance-fast → kling → grok` order. Reset downstream dependents only when an upstream artifact changes.

## Keep evidence with every artifact

Persist prompt, command shape, response ID, local path, SHA-256, size, project binding, and node dependency. This makes handoff and failure recovery deterministic.

## Distinguish synthetic demos from recordings

Metadata-driven UI animation is appropriate for scalable workflow proof, but must not be represented as genuine device footage. Genuine recordings remain a separate compatibility mode.

## Separate distribution from orchestration

Use a small Node launcher for `npx` installation, runtime discovery, Agent Skill installation, and authentication passthrough. Keep the tested Python DAG as the orchestration core. This gives a one-command cross-machine setup without rewriting campaign behavior or requiring users to manage Python dependencies.
