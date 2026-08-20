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
    models: [seedance-2-0, kling, grok]
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
| 1 | `seedance-2-0` | Primary Seedance 2.0 Hook/effect/final generation; target 1080p, minimum 720p |
| 2 | `kling` | Retry only the failed node with locked inputs |
| 3 | `grok` | Final retry only for that failed node |

Three failures, identity/product loss, prompt drift, or unresolved policy risk → `BLOCKED`. Never regenerate passed upstream assets merely to create variation.

## Workflow

1. Validate rights, claims, input, locales, output, binaries, and the Skill↔project registry.
2. Write `plan.json` and initialize resumable `state.json`.
3. Generate five-line culturally adapted script JSON for only the selected ad locales.
4. Generate a neutral ordinary Before image. Invoke the target Skill twice: once for a distinct curiosity Hook and once for the complete effect/result payoff. The Hook and result must not reuse the same shot, action, camera path, or source frames. In the bound Makaron project, analyze the complete result video and export its strongest stable decoded frame as the exact After—never use a fixed percentage and never redraw it. Then ask Makaron to compose the locked Before and After pixels on the black side-by-side canvas.
5. For each selected locale, invoke Makaron's public `screen-demo` Skill in the bound project. Supply the authorized input plus the bundled v5 iOS `home-top`, `home-target`, and `detail` UI frames as visual references. Makaron creates the synthetic four-second localized Remotion design: English uses `en`, Japanese uses `ja`, and Cantonese uses `zh-Hant`. Ask Makaron to materialize it first. If composition export is forbidden, encode only the unchanged, validated Makaron design locally; never substitute the legacy local workflow renderer. Do not invoke the non-selectable internal `synthetic-screen-recording` capability directly.
6. Call `makaron music create` once to generate an original instrumental BGM of at least 20 seconds with no early fade-out. Reuse that exact BGM asset for every selected locale.
7. For each locale, invoke the built-in `tiktok-video` builder in one bound-project `makaron chat` request with the distinct Hook, comparison image, effect/result, locale-correct workflow, fixed CTA, BGM, and five script lines. Reuse original Makaron URLs for Hook/effect/BGM/comparison. Publish only local workflow and the bundled upload-safe three-second CTA excerpt through `makaron admin upload`, cache the resulting CDN URLs by content hash, and pass URLs through unchanged; never send local video/audio paths through the signed-URL PUT channel or embed a multi-megabyte comparison as base64 in final. Use Makaron's current Remotion composition runtime to create one continuous Seed Audio young-female TTS take first, derive real Caption JSON timings from that audio, then make scene boundaries contain their assigned spoken lines. Burn one Meta-safe subtitle set, mute every source video, loop the same BGM from frame zero through CTA, and directly export the complete five-part MP4. Accept only a newly generated video result, never an uploaded source attachment. A fallback Remotion design must satisfy composition contract v2 before local rendering. Do not use local edge-tts, FFmpeg concat/amix, ASS subtitle rendering, or PIL final composition.
8. Run technical QC, then package MP4s, BGM source, scripts, plan, prompts, project binding, review gate, provenance, and performance plan. Publication remains human-approved and paused by default.

## CLI protocol

Use the globally installed CLI. If it is missing on a new machine, install the package and this Skill together:

```bash
npx -y makaron-ad-creator-cli setup
makaron-ad login
```

`makaron-ad login` is a one-time Mac setup step: validate the key, save it in macOS Keychain, and let later user or Agent commands load it automatically. Never ask for the key again while the keychain entry is valid. Use `makaron-ad logout` only when the user asks to remove or replace the saved credential. Never place the key in prompts, campaign files, logs, or Git.

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
# For final-* nodes, attach the required Caption/scene contract v2 sidecar:
makaron-ad complete <campaign.json> --node final-en --artifact <file> --response-id <id> --timing-manifest <timing-manifest-en.json>
makaron-ad run <campaign.json> --executor agent
```

Read [executor-protocol.md](references/executor-protocol.md) for request semantics and recovery. Read [campaign-schema.md](references/campaign-schema.md) only when editing campaign JSON directly.

## Locked prompt rule

Use the English templates in `scripts/makaron_ad_creator/prompts.py`. Fill placeholders only. Do not translate, rewrite, reorder, add, or remove template sections before execution. Save every filled prompt under `run/prompts/` and compile them into `deliverables/prompt_used.md`.

The five fixed final beats are: distinct outcome-teaser Hook video → simultaneous Before/After comparison image → truthful localized workflow video → full effect/result video → fixed Makaron Logo CTA video. Keep the same order and timing bounds across locales; allow exact beat lengths to adapt to measured speech. TTS defaults to a natural energetic young-adult female Seed Audio voice and must finish before CTA. Caption line 1 belongs to Hook, line 2 to comparison, lines 3–4 to workflow, and line 5 to result; no line may cross its scene boundary. Every source video is muted. CTA source audio is never used. One separately generated instrumental BGM is looped continuously from 0.0 seconds through the final CTA frame at relative mix volume `0.22`, with only a gentle final fade. On Meta Reels keep key content inside the central safe zone; captions use white text, black outline, no bar, at most two lines and 20 visible characters per line.

Read [reference-editing-rhythm.md](references/reference-editing-rhythm.md) only when changing timing, duration QC, subtitle placement, or CTA selection.

## QC

| Result | Condition | Action |
|---|---|---|
| `PASS` | Every selected 9:16 H.264/AAC MP4 targets 1080×1920 and is never below 720×1280, lasts 15–20s, has distinct Hook/result, a true best source-frame After, Makaron-composed comparison, Makaron `screen-demo` in the correct UI locale, correct five-part order, scene-bound Seed Audio captions inside Meta safe zones, continuous BGM through CTA, muted source audio, and complete provenance | Deliver to human review |
| `REROLL` | Recoverable node-level face/hand drift, subtitle collision, timing issue, failed download, or literal localization | Retry only that node with the next model |
| `BLOCKED` | Rights/claims unclear, prohibited content, project isolation broken, missing required Marketplace data, subject/product lost, prompt drift, or budget exhausted | Stop and report exact node/error |

Technical QC cannot prove creative truthfulness or locale naturalness. Keep `review.md` as a required publication gate; never auto-activate media spend.

## Outputs

- `final-artifact-<selected-locale>.mp4` for each requested locale
- `plan.json`, `scripts.json`, `prompt_used.md`
- `qc_report.md`, `review.csv`, `review.md`
- `provenance.json`, `performance-plan.json`, `project-binding.json`
