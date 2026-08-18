---
name: makaron-ad-creator
description: Fully orchestrate a rights-cleared input image and one Makaron Marketplace Skill into resumable English, Japanese, and Cantonese vertical ad videos. Use when an Agent or Makaron must plan, generate, localize, QC, resume, or package the complete ad chain without per-step human handoffs; also use for one-image ad campaigns, three-language delivery, synthetic Makaron workflow demos, or CLI-driven cross-Agent execution.
allowed-tools: [generate_video, analyze_image]
metadata:
  makaron:
    icon: "🎬"
    color: "#FF2FD1"
    tags: [advertising, automation, localization]
    faceProtection: default
    defaultAspectRatio: "9:16"
    models: [seedance-fast, kling, grok]
---

# Makaron Ad Creator

## Core concept

Accept exactly two user inputs—one owned/licensed image and one Makaron Marketplace Skill name—then run a resumable asset DAG that produces English, Japanese, and Hong Kong Cantonese ads. Resolve every other field automatically, keep generation in one persistent project bound to that Skill, generate the App workflow deterministically from Marketplace metadata, and package prompts, hashes, QC, and three final MP4s.

Use the bundled project CLI as the state owner. Do not improvise a parallel ad workflow in chat.

## Public input contract

| Field | Required | Type | Meaning |
|---|:---:|---|---|
| `input_image` | ✅ | file | Owned/licensed person, character, or product image |
| `skill_name` | ✅ | string | Exact or resolvable Makaron Marketplace Skill name |

Do not ask the user for Skill ID, project ID, language mapping, Campaign JSON, output size, prompts, CTA asset, recording, or per-step confirmation. Resolve or default them internally.

Example user request:

```text
Use this image with the Rainy Kiss Skill and create the ad videos.
```

Treat the user's act of supplying the image for this exact generation request as the run-level rights attestation. Still block when the content itself indicates a minor, public figure, prohibited product, private information, or deceptive claim.

## Project isolation

Bind one Skill to one persistent Makaron project inside the current Agent/browser workspace. Use `makaron chat --project <project_id>` for every image, video, audio, localization, correction, and assembly operation. Reject `--project auto`, standalone `makaron edit`, standalone `makaron video create`, a second project for the same Skill, or project reuse by a different Skill.

Invoking this Skill with the two required inputs explicitly authorizes creating the one dedicated Makaron project needed for the requested generation. Create it automatically on first use, persist it in `project-registry.json`, and reuse it automatically thereafter. Another Agent scope may have its own binding.

## Safety gates

Allow owned/licensed adult-person, fictional-character, product, landscape, food, fashion, and ordinary app-workflow advertising.

Block sexualized minors, weapons promotion, graphic violence, hateful content, illegal goods, deceptive financial/medical claims, body shaming, public-figure manipulation, fake endorsements/ratings, copied logos, unlicensed music, private UI data, and unsupported product claims. Preserve authorized identity, age, skin tone, facial structure, body proportions, product geometry, labels, and factual capability.

Return `BLOCKED` before generation when consent/ownership is unclear, a subject may be a minor, a claim is not substantiated, the project binding is missing/`auto`, Marketplace metadata lacks the required localized inputs, privacy cannot be isolated, or publication authority is absent. Synthetic workflow demos must be labeled internally as synthetic and never described as literal device recordings.

## Budget

| Attempt | Model | Action |
|:--:|---|---|
| 1 | `seedance-fast` | Primary effect/final generation |
| 2 | `kling` | Retry only the failed node with locked inputs |
| 3 | `grok` | Final retry only for that failed node |

Three failures, identity/product loss, prompt drift, or unresolved policy risk → `BLOCKED`. Never regenerate passed upstream assets merely to create variation.

## Workflow

1. Validate rights, claims, input, locales, output, binaries, and the Skill↔project registry.
2. Write `plan.json` and initialize resumable `state.json`.
3. Generate five-line culturally adapted `en/ja/yue` script JSON.
4. Generate a neutral ordinary Before image, invoke the target Skill for the effect video, extract an After frame, and compose a black-background side-by-side comparison locally.
5. Run `edit-makaron-app-workflow-recording` in synthetic mode for `en/ja/zh-Hant`; map Cantonese voiceover to the `zh-Hant` UI video.
6. Assemble three ads with the same timing and creative mechanism. Generate natural locale TTS, one subtitle track, instrumental BGM, and CTA inside the bound project.
7. Run technical QC, then package MP4s, scripts, plan, prompts, project binding, review gate, provenance, and performance plan. Publication remains human-approved and paused by default.

## CLI protocol

From the project root, expose only this command to the user:

```bash
bin/makaron-ad /owned/input.jpg "Marketplace Skill Name"
```

The CLI automatically calls `makaron skills show`, resolves the Skill ID/core metadata, creates or reuses its persistent project, writes the campaign config, and runs the full pipeline. Return only the final status and deliverables path.

For another Agent, use `--executor agent`. The CLI emits one `run/requests/<node>.json` at a time. Execute exactly that request in the bound project, then attach the result and resume:

```bash
bin/makaron-ad complete <campaign.json> --node <node-id> --artifact <file> --response-id <id>
bin/makaron-ad run <campaign.json> --executor agent
```

Read [executor-protocol.md](references/executor-protocol.md) for request semantics and recovery. Read [campaign-schema.md](references/campaign-schema.md) only when editing campaign JSON directly.

## Locked prompt rule

Use the English templates in `scripts/makaron_ad_creator/prompts.py`. Fill placeholders only. Do not translate, rewrite, reorder, add, or remove template sections before execution. Save every filled prompt under `run/prompts/` and compile them into `deliverables/prompt_used.md`.

The five fixed final beats are: outcome Hook → simultaneous Before/After → truthful localized workflow demo → full result → CTA. Keep the same mechanism and timing across locales; adapt language and voice, not the experiment design.

## QC

| Result | Condition | Action |
|---|---|---|
| `PASS` | Three 1080×1920 H.264/AAC MP4s ≤18s; result first; Before/After coexist; identity/product stable; correct UI locale; readable single subtitles; natural language; audio present; provenance complete | Deliver to human review |
| `REROLL` | Recoverable node-level face/hand drift, subtitle collision, timing issue, failed download, or literal localization | Retry only that node with the next model |
| `BLOCKED` | Rights/claims unclear, prohibited content, project isolation broken, missing required Marketplace data, subject/product lost, prompt drift, or budget exhausted | Stop and report exact node/error |

Technical QC cannot prove creative truthfulness or locale naturalness. Keep `review.md` as a required publication gate; never auto-activate media spend.

## Outputs

- `final-artifact-en.mp4`
- `final-artifact-ja.mp4`
- `final-artifact-yue.mp4`
- `plan.json`, `scripts.json`, `prompt_used.md`
- `qc_report.md`, `review.csv`, `review.md`
- `provenance.json`, `performance-plan.json`, `project-binding.json`
