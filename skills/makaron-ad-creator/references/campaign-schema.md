# Campaign schema

## Stable fields

- `version`: `1`.
- `campaign_id`: stable filesystem-safe label.
- `input_image`: absolute path after validation.
- `target_skill`: exact `id`, human `name`, factual `core`, and optional `transformation_type`.
- `project_binding`: `strategy=one_skill_one_persistent_project`, matching `skill_id`, and explicit non-`auto` `project_id`.
- `rights`: all three booleans must be true before generation.
- `offer`: substantiated value proposition, CTA, and optional destination URL.
- `locales`: exactly `en→en`, `ja→ja`, `yue→zh-Hant` for the default package.
- `automation.executor`: `makaron` for direct unattended execution or `agent` for request handoff.
- `automation.max_attempts`: maximum `3`.
- `automation.builder_skill_id`: optional installed Marketplace builder Skill; empty uses a bound-project chat assembly brief.
- `output`: exact 1080×1920 MP4 and 15–18 seconds.

`catalog_json` is optional. When supplied, synthetic workflow generation is offline and reproducible. Without it, the workflow renderer reads the live Marketplace catalog with `makaron skills list --json`.

Do not store API keys, tokens, passwords, or private URLs in campaign JSON.

