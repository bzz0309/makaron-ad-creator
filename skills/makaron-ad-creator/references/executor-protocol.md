# Cross-Agent executor protocol

## Request lifecycle

`makaron-ad run --executor agent` performs every deterministic node itself. At a generative node it writes one JSON request and returns exit code `3` with `WAITING_FOR_AGENT`.

The executing Agent must:

1. verify `project_id` is explicit and not `auto`;
2. use `makaron chat --project <project_id>` for every generative node except `bgm`; execute `bgm` with exactly one standalone `makaron music create` call;
3. use the request's exact prompt and attached inputs;
4. save the requested artifact locally;
5. call `makaron-ad complete ...` with the node and artifact;
6. resume `makaron-ad run` until `PASS` or `BLOCKED`.

If generation itself fails, call `makaron-ad fail <campaign.json> --node <node-id> --error "<concise cause>"`, then resume. The next request advances from `seedance-fast` to `kling` to `grok` where video routing applies.

Never mark a request complete from prose alone. The artifact must exist and match the required file class.

## Node operations

| Operation | Expected result |
|---|---|
| `generate_json` | UTF-8 JSON with exactly five strings under each selected locale key and no unselected locale keys |
| `generate_image` | One decoded PNG/JPEG/WebP |
| `invoke_skill_video` | One MP4 created by the exact target Marketplace Skill |
| `generate_instrumental_bgm` | One at-least-20-second instrumental audio file plus its generated HTTP(S) source URL; call `complete` with `--source-url` so chat can attach the long BGM without local upload limits |
| `assemble_localized_ad` | One complete localized five-part 1080×1920 H.264/AAC MP4 rendered by one project-bound Makaron chat through internal Remotion; inputs include CTA and BGM, and there is no local final post-process |

## Recovery

Use `makaron-ad status` to inspect the waiting/failed node. Use `makaron-ad retry --node <id>` only after correcting the cause; it resets that node and all downstream nodes while retaining unrelated passed work.

If the same node reaches three failed attempts, preserve state and return `BLOCKED`. Do not switch projects or loosen safety constraints to force completion.
