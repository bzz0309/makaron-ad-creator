# makaron-ad-creator

用户只需要提供一张输入图和一个 Makaron Marketplace Skill 名称，并可选需要的语言。系统可以只输出英文、日文或香港粤语，也可以输出任意组合；不传语言时默认输出三语。

The CLI owns orchestration, state, retries, project isolation, deterministic composition, workflow synthesis, QC, and provenance. Makaron or another Agent owns only the generative nodes described by the CLI. This prevents a large Skill document from becoming an unreliable hidden state machine.

## 安装（和音乐库 CLI 一样）

前置条件：Node.js 18+ 和 Python 3.11+。`setup` 会自动管理 Python 虚拟环境与 Pillow，用户无需手工安装媒体库。

```bash
npx -y makaron-ad-creator-cli setup
makaron-ad login
```

`setup` 会一次完成：安装全局 `makaron-ad` 命令、安装 Makaron CLI 与 FFmpeg/FFprobe 运行依赖、建立私有 Python/Pillow 环境，并把唯一入口 Skill `makaron-ad-creator` 安装到当前 Agent。无需手工复制本仓库，也无需把五个子 Skill 分别装一遍。

## 唯一公开用法

```bash
makaron-ad create --image /absolute/path/input.jpg --skill "Marketplace Skill 名称"
```

只生成粤语投放视频：

```bash
makaron-ad create --image /absolute/path/input.jpg --skill "Marketplace Skill 名称" --locale yue
```

生成英语和日语：

```bash
makaron-ad create --image /absolute/path/input.jpg --skill "Marketplace Skill 名称" --locale en,ja
```

Agent 也可以用更短的二参数形式：

```bash
makaron-ad /absolute/path/input.jpg "Marketplace Skill 名称"
```

这一条命令会自动：查找 Skill 元数据和 ID、首次创建或后续复用该 Skill 的专属 Makaron 项目、只生成所选语言的文案、对应 App 操作视频和成片、重试失败节点、做 QC 并打包交付。映射固定为 `en→英语录屏`、`ja→日语录屏`、`yue→繁体中文录屏`。

每条成片固定采用 `Hook 视频 → 对比图 → 录屏视频 → 效果视频 → Logo CTA 视频`，但节奏会根据 Skill 动作复杂度在 15–20 秒内自适应：Hook 默认 2.5 秒、复杂动作最多 5 秒，对比图约 2.5 秒，录屏约 4 秒，效果段保留完整 payoff。TTS 默认使用目标语言的自然年轻女生声；随 npm 包内置完整 Makaron Logo 动画源片，默认由 CLI 用 FFmpeg 把源片 0–3 秒原样内容拼到结尾，不让生成模型重画 Logo。Campaign 使用可跨电脑解析的 `bundled://makaron-logo-cta.mp4`，所以其他 Agent 在新电脑执行一次 `setup` 后也会拥有同一份 CTA 资源，不依赖这台电脑的 Desktop 路径。

提交图片即表示图片拥有投放素材制作所需的授权、真人为已授权成年人，且不会用生成结果支持虚假 Claim。这不代表授权自动发布广告。

内部仍保留 `run/status/retry/complete` 等恢复命令供 Agent 自动处理故障，但最终用户无需填写这些参数。运行状态默认保存在 `~/.makaron-ad-creator/workspace/`，可以中断后继续。

检查当前电脑是否安装完整：

```bash
makaron-ad doctor
```

源码开发者仍可运行 `bin/makaron-ad`；普通用户和 Agent 应使用 npm 安装后的 `makaron-ad`。

## Design decisions

- Final ad locales can be any selected subset of English, Japanese, and Hong Kong Cantonese; the default remains all three.
- App UI mapping is fixed: English uses English, Japanese uses Japanese, and Cantonese uses Traditional Chinese.
- Final structure is fixed to Hook video → comparison image → workflow video → effect/result video → bundled Logo CTA; default TTS is a young-adult female voice in the selected locale.
- Final duration adapts from 15–20 seconds; the shared timing bounds were calibrated from supplied English, Japanese, and Cantonese finished ads rather than forcing every Skill to 18 seconds.
- The complete 10-second Logo CTA source is bundled for portability; local deterministic post-processing appends only the configured continuous 2–3 second excerpt.
- A Skill is bound to one persistent Makaron project per Agent scope. `--project auto` is rejected.
- No per-asset approval is required after rights, claims, project binding, and offer are configured. Failed nodes retry independently.
- Publication is never automatic. Delivered review state is `PAUSED` / human approval required.
- Synthetic workflow generation comes from the supplied v5 iOS implementation and live/offline Marketplace metadata. It is never labeled as genuine screen recording.

## 内部维护命令

```text
make IMAGE SKILL_NAME          与上方二参数入口等价
doctor                         check Python/Pillow/FFmpeg/Makaron/runtime assets
init                           write campaign.json and plan.json
plan <campaign.json>           inspect deterministic DAG
run <campaign.json>            execute or resume
status <campaign.json>         inspect state and lineage
complete ...                   attach another Agent's generated artifact
fail ...                       report a failed Agent request and use the next retry
retry --node <id>              reset one node and downstream dependents
```

## Delivery

Successful campaigns place only the selected MP4s and audit package in `<campaign>/deliverables/`. The npm package keeps the original five-Skill directory structure, but only `makaron-ad-creator` is installed as the public Agent entrypoint. `edit-makaron-app-workflow-recording` is the user-supplied v5 iOS package copied unchanged.
