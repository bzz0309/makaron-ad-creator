# Architecture decision: use a CLI orchestration core

## Decision

Use one master Skill for discovery and operating policy, a Python CLI for execution state, and small child Skills/adapters for bounded creative nodes.

Only the master Skill/CLI is public. The npm package retains the user's original five folders for internal modularity, but `setup` installs only the master Skill. The user supplies only `input image + Marketplace Skill name`; the CLI resolves metadata and project state automatically.

The distribution layer mirrors the Makaron music-library experience: `npx ... setup` installs a global command and Agent Skill. The Node launcher owns portable installation, one-time macOS Keychain login, and discovery of the bundled Makaron CLI, FFmpeg, FFprobe, and private Python/Pillow environment; the existing Python core continues to own campaign semantics and resumable state. Saved credentials are injected only into child-process memory and never enter campaign state or repository files.

## Why

A single large Skill can describe the workflow, but it cannot reliably retain node status, safely resume after a failed video, enforce one-project binding, validate only the selected locale outputs, or expose portable work requests to another Agent. Those are deterministic control-plane responsibilities and belong in the CLI.

The CLI writes a visible DAG and state file, executes local nodes, and either calls Makaron directly or pauses on a machine-readable request for another Agent. The same campaign can therefore move between agents without re-planning or losing provenance.

The npm package owns both the complete fixed Makaron Logo CTA master and its same-source silent three-second upload-safe excerpt. Campaign configs resolve the portable asset inside the package, so remote Agents never depend on the original contributor's Desktop path. One target-Skill node generates a continuous Effect, preferring Seedance 2.0; deterministic local nodes extract non-overlapping Hook and Result ranges and record the common source hash. A dedicated `bgm` node calls `makaron music create` once and reuses that audio across locales. Each final node sends Hook, comparison, Result, localized v5 workflow, fixed CTA, BGM, and script to one project-bound `makaron chat` using built-in `tiktok-video`. The Remotion runtime creates Seed Audio first, derives Caption JSON/scene boundaries from measured timing, applies the Meta safe-zone profile, mutes all source audio, loops BGM through CTA, and exports the MP4. Only authoritative generated video outputs plus a valid contract-v2 timing manifest can satisfy the node. If Makaron's export endpoint rejects an otherwise complete design, the CLI validates that same contract before pinned local Remotion rendering. Local FFmpeg may extract exact Effect time ranges, but it is not the final concat/amix/subtitle engine.

Final-input transport is URL-first. The DAG preserves authoritative BGM/comparison URLs and recovers them from cached responses for older campaigns. Derived Hook/Result, v5 workflow, and bundled CTA files are uploaded once through the Makaron backend `admin upload` endpoint and cached by SHA-256. This avoids the Makaron CLI local video/audio signed-URL PUT path, which is unreachable from some Agent sandboxes.

```text
master Skill
    ↓ policy + input contract
global makaron-ad Node launcher
    ↓ portable runtime + bundled dependencies
Python orchestration core
    ├── local: Effect segment extraction / localized v5 workflow / validate / QC / package / encode unchanged final Remotion design only when cloud export is forbidden
    ├── Makaron: script / Before / one target-Skill Effect / best source-frame After / comparison / final
    └── Agent protocol: request.json → artifact → complete → resume
```

## Automation boundary

Rights/consent, claim truth, initial persistent project binding, and publication are human gates. Once the first three are recorded, creative production is unattended and resumable. Publication stays paused because spending money and external distribution are materially different actions from creating files.

## Source-package resolution

- Run the user-supplied v5 `edit-makaron-app-workflow-recording` synthetic renderer as the production workflow node. Pass the real Marketplace Skill ID and require its locale-specific QC, keyframe sheet, and version-2 manifest; do not replace it with generic `screen-demo`.
- Do not depend on the environment-level `social-ad-creator` Skill; it was not part of the user's source package.
- Retain recording mode only for explicitly supplied genuine footage.
- Replace the old hard-coded project and `--project auto` instructions.
- Replace per-asset approval loops with node QC and retry budget.
- Target 1080×1920 instead of the conflicting 886×1920 legacy builder value; accept Meta's official 720×1280 minimum only as a 9:16 fallback.
- Treat old "uglify" language as unsafe; the Before is ordinary/unpolished, never degrading.
