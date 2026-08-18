# Architecture decision: use a CLI orchestration core

## Decision

Use one master Skill for discovery and operating policy, a Python CLI for execution state, and small child Skills/adapters for bounded creative nodes.

Only the master Skill/CLI is public. The package retains the user's original five folders for internal modularity, but the user supplies only `input image + Marketplace Skill name`. The CLI resolves metadata and project state automatically.

## Why

A single large Skill can describe the workflow, but it cannot reliably retain node status, safely resume after a failed video, enforce one-project binding, validate three locale outputs, or expose portable work requests to another Agent. Those are deterministic control-plane responsibilities and belong in the CLI.

The CLI writes a visible DAG and state file, executes local nodes, and either calls Makaron directly or pauses on a machine-readable request for another Agent. The same campaign can therefore move between agents without re-planning or losing provenance.

```text
master Skill
    ↓ policy + input contract
makaron-ad CLI
    ├── local: validate / After frame / comparison / synthetic UI / QC / package
    ├── Makaron: script / Before / target-Skill effect / localized final
    └── Agent protocol: request.json → artifact → complete → resume
```

## Automation boundary

Rights/consent, claim truth, initial persistent project binding, and publication are human gates. Once the first three are recorded, creative production is unattended and resumable. Publication stays paused because spending money and external distribution are materially different actions from creating files.

## Source-package resolution

- Use the user-supplied `edit-makaron-app-workflow-recording-v5-ios.zip` implementation and bundled baselines unchanged; the packaged folder is verified by zero-diff comparison.
- Do not depend on the environment-level `social-ad-creator` Skill; it was not part of the user's source package.
- Retain recording mode only for explicitly supplied genuine footage.
- Replace the old hard-coded project and `--project auto` instructions.
- Replace per-asset approval loops with node QC and retry budget.
- Normalize output to 1080×1920 instead of the conflicting 886×1920 legacy builder value.
- Treat old "uglify" language as unsafe; the Before is ordinary/unpolished, never degrading.
