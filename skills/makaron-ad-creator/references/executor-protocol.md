# Cross-Agent executor protocol

## Request lifecycle

`makaron-ad run --executor agent` performs every deterministic node itself. At a generative node it writes one JSON request and returns exit code `3` with `WAITING_FOR_AGENT`.

The executing Agent must:

1. verify `project_id` is explicit and not `auto`;
2. use `makaron chat --project <project_id>` for every generative node except `bgm`; execute `bgm` with exactly one standalone `makaron music create` call;
3. use the request's exact prompt and attached inputs;
   final requests use public HTTP(S) URLs for every video/audio input. Reuse generated source URLs where present; publish only unavoidable local workflow/CTA assets through `makaron admin upload`. Do not pass local video/audio paths to `makaron chat`;
4. save the requested artifact locally;
5. call `makaron-ad complete ...` with the node and artifact; a `final-*` node must also pass `--timing-manifest` with the contract v2 Caption/scene sidecar requested in JSON;
6. resume `makaron-ad run` until `PASS` or `BLOCKED`.

If generation itself fails, call `makaron-ad fail <campaign.json> --node <node-id> --error "<concise cause>"`, then resume. The next request advances from `seedance-2-0` to `kling` to `grok` where video routing applies.

Never mark a request complete from prose alone. The artifact must exist and match the required file class.

## Node operations

| Operation | Expected result |
|---|---|
| `generate_json` | UTF-8 JSON with exactly five strings under each selected locale key and no unselected locale keys |
| `generate_image` | One decoded PNG/JPEG/WebP |
| `invoke_skill_video` | One continuous 9:16 Effect MP4 created by the exact target Marketplace Skill, targeting 1080×1920 and never below 720×1280; the CLI derives Hook and Result locally as exact non-overlapping ranges |
| `select_exact_effect_keyframe` | One exact decoded source frame selected after full-clip analysis; no fixed percentage and no regeneration |
| `compose_comparison_in_makaron` | One 1080×1920 Before/After image composed in Makaron from locked source pixels |
| `generate_instrumental_bgm` | One at-least-20-second instrumental audio file plus its generated HTTP(S) source URL; call `complete` with `--source-url` so chat can attach the long BGM without local upload limits |
| `assemble_localized_ad` | One complete localized five-part 9:16 H.264/AAC MP4, target 1080×1920/minimum 720×1280, rendered by one project-bound Makaron chat through the `tiktok-video` Remotion builder; Caption JSON timings stay inside assigned scenes and Meta safe zones; inputs include CTA and BGM, with no local final post-process |

Hook, Result, and localized workflow are deterministic CLI nodes, so another Agent never receives separate generation requests for them. The CLI splits one Effect by timestamp and runs bundled v5 `workflow_recording.py synthesize` with the resolved Skill ID and mapped UI locale before emitting the final assembly request.

## Recovery

Use `makaron-ad status` to inspect the waiting/failed node. Use `makaron-ad retry --node <id>` only after correcting the cause; it resets that node and all downstream nodes while retaining unrelated passed work.

If the same node reaches three failed attempts, preserve state and return `BLOCKED`. Do not switch projects or loosen safety constraints to force completion.
