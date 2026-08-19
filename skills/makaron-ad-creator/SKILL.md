---
name: makaron-ad-creator
description: Fully orchestrate a rights-cleared input image and one Makaron Marketplace Skill into resumable English, Japanese, and/or Cantonese vertical ad videos. Use when an Agent or Makaron must generate one selected locale or a locale subset, localize the matching App workflow, QC, resume, or package the complete ad chain without per-step human handoffs.
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

Accept two required user inputs—one owned/licensed image and one Makaron Marketplace Skill name—and an optional locale selection. Run a resumable asset DAG that produces only the selected English, Japanese, and/or Hong Kong Cantonese ads. Keep generation in one persistent project bound to that Skill, generate only the matching App workflow locales, and package prompts, hashes, QC, and the selected final MP4s. Default to all three ad locales when no locale is supplied.

Use the bundled project CLI as the state owner. Do not improvise a parallel ad workflow in chat.

## Public input contract

| Field | Required | Type | Meaning |
|---|:---:|---|---|
| `input_image` | ✅ | file | Owned/licensed person, character, or product image |
| `skill_name` | ✅ | string | Exact or resolvable Makaron Marketplace Skill name |
| `locale` | 否 | `en`, `ja`, `yue`, `all`, or comma-separated subset | Ad language selection; defaults to `all` |

Do not ask the user for Skill ID, project ID, language mapping, Campaign JSON, output size, prompts, CTA asset, recording, voice selection, or per-step confirmation. Resolve the fixed mapping internally: `en→en`, `ja→ja`, `yue→zh-Hant`. Use the bundled fixed Makaron Logo CTA source and default TTS to a natural energetic young-adult female voice.

Example user request:

```text
Use this image with the Rainy Kiss Skill and create the ad videos.
```

Treat the user's act of supplying the image for this exact generation request as the run-level rights attestation. Still block when the content itself indicates a minor, public figure, prohibited product, private information, or deceptive claim.

## Project isolation

Bind one Skill to one persistent Makaron project inside the current Agent/browser workspace. Use `makaron chat --project <project_id>` for every image, video, TTS, localization, correction, and final Remotion assembly operation. Reject `--project auto`, standalone `makaron edit`, standalone `makaron video create`, a second project for the same Skill, or project reuse by a different Skill. The only standalone creative exception is the campaign's single instrumental BGM node, which must call `makaron music create` exactly once and then be reused by every selected locale.

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
3. Generate five-line culturally adapted script JSON for only the selected ad locales.
4. Generate a neutral ordinary Before image, invoke the target Skill for the effect video, extract an After frame, and compose a black-background side-by-side comparison locally.
5. Run `edit-makaron-app-workflow-recording` only for the selected UI locales: English uses `en`, Japanese uses `ja`, and Cantonese uses `zh-Hant`.
6. Call `makaron music create` once to generate an original instrumental BGM of at least 20 seconds with no early fade-out. Reuse that exact BGM asset for every selected locale.
7. For each locale, issue one bound-project `makaron chat` request with the comparison image, effect video, locale-correct workflow video, fixed CTA source, BGM, and five script lines. Require the Makaron Agent's internal Remotion workflow to mute every source video (including CTA), create one continuous Seed Audio young-female TTS take, burn one synchronized top-safe subtitle set, loop the same BGM from frame zero through CTA, and directly export the complete five-part MP4. Do not use local edge-tts, FFmpeg concat/amix, ASS subtitle rendering, or PIL final composition.
8. Run technical QC, then package MP4s, BGM source, scripts, plan, prompts, project binding, review gate, provenance, and performance plan. Publication remains human-approved and paused by default.

## CLI protocol

Use the globally installed CLI. If it is missing on a new machine, install the package and this Skill together:

```bash
npx -y makaron-ad-creator-cli setup
makaron-ad login
```

Expose only this generation command to the user:

```bash
makaron-ad create --image /owned/input.jpg --skill "Marketplace Skill Name"
```

Generate only Cantonese with a Traditional-Chinese workflow recording:

```bash
makaron-ad create --image /owned/input.jpg --skill "Marketplace Skill Name" --locale yue
```

The CLI automatically calls `makaron skills show`, resolves the Skill ID/core metadata, creates or reuses its persistent project, writes the campaign config, and runs the locale-scoped pipeline. Return only the final status and deliverables path.

For another Agent, use `--executor agent`. The CLI emits one `run/requests/<node>.json` at a time. Execute exactly that request in the bound project, then attach the result and resume:

```bash
makaron-ad complete <campaign.json> --node <node-id> --artifact <file> --response-id <id>
# For another Agent's BGM node, also retain the generated public audio URL:
makaron-ad complete <campaign.json> --node bgm --artifact <file> --response-id <id> --source-url <https-url>
makaron-ad run <campaign.json> --executor agent
```

Read [executor-protocol.md](references/executor-protocol.md) for request semantics and recovery. Read [campaign-schema.md](references/campaign-schema.md) only when editing campaign JSON directly.

## Locked prompt rule

Use the English templates in `scripts/makaron_ad_creator/prompts.py`. Fill placeholders only. Do not translate, rewrite, reorder, add, or remove template sections before execution. Save every filled prompt under `run/prompts/` and compile them into `deliverables/prompt_used.md`.

The five fixed final beats are: outcome Hook video → simultaneous Before/After comparison image → truthful localized workflow video → full effect/result video → fixed Makaron Logo CTA video. Keep the same order and timing bounds across locales; allow exact beat lengths to adapt to the Skill mechanism and natural speech. TTS defaults to a natural energetic young-adult female Seed Audio voice in the target locale and must finish before CTA. Every source video is muted. CTA source audio is never used. One separately generated instrumental BGM is looped continuously from 0.0 seconds through the final CTA frame at relative mix volume `0.22`, with only a gentle final fade.

Read [reference-editing-rhythm.md](references/reference-editing-rhythm.md) only when changing timing, duration QC, subtitle placement, or CTA selection.

## QC

| Result | Condition | Action |
|---|---|---|
| `PASS` | Every selected 1080×1920 H.264/AAC MP4 is 15–20s; correct five-part order; identity/product stable; correct UI locale; one complete Seed Audio narration; readable single subtitles; the same BGM is audible through CTA; CTA/source audio is muted; provenance complete | Deliver to human review |
| `REROLL` | Recoverable node-level face/hand drift, subtitle collision, timing issue, failed download, or literal localization | Retry only that node with the next model |
| `BLOCKED` | Rights/claims unclear, prohibited content, project isolation broken, missing required Marketplace data, subject/product lost, prompt drift, or budget exhausted | Stop and report exact node/error |

Technical QC cannot prove creative truthfulness or locale naturalness. Keep `review.md` as a required publication gate; never auto-activate media spend.

## Outputs

- `final-artifact-<selected-locale>.mp4` for each requested locale
- `plan.json`, `scripts.json`, `prompt_used.md`
- `qc_report.md`, `review.csv`, `review.md`
- `provenance.json`, `performance-plan.json`, `project-binding.json`
