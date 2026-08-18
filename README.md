# makaron-ad-creator

用户只需要提供两个值：一张输入图和一个 Makaron Marketplace Skill 名称。系统自动输出三条竖屏投放视频（英文、日文、香港粤语）。

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

Agent 也可以用更短的二参数形式：

```bash
makaron-ad /absolute/path/input.jpg "Marketplace Skill 名称"
```

这一条命令会自动：查找 Skill 元数据和 ID、首次创建或后续复用该 Skill 的专属 Makaron 项目、生成三语言文案与素材、生成三套 App 操作视频、合成成片、重试失败节点、做 QC 并打包交付。

提交图片即表示图片拥有投放素材制作所需的授权、真人为已授权成年人，且不会用生成结果支持虚假 Claim。这不代表授权自动发布广告。

内部仍保留 `run/status/retry/complete` 等恢复命令供 Agent 自动处理故障，但最终用户无需填写这些参数。运行状态默认保存在 `~/.makaron-ad-creator/workspace/`，可以中断后继续。

检查当前电脑是否安装完整：

```bash
makaron-ad doctor
```

源码开发者仍可运行 `bin/makaron-ad`；普通用户和 Agent 应使用 npm 安装后的 `makaron-ad`。

## Design decisions

- Final ad locales are English, Japanese, and Hong Kong Cantonese.
- App UI locales are English, Japanese, and Traditional Chinese; Cantonese voiceover uses the Traditional-Chinese UI asset.
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

Successful campaigns place the three MP4s and audit package in `<campaign>/deliverables/`. The npm package keeps the original five-Skill directory structure, but only `makaron-ad-creator` is installed as the public Agent entrypoint. `edit-makaron-app-workflow-recording` is the user-supplied v5 iOS package copied unchanged.
