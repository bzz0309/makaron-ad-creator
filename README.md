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

如果系统 npm 全局目录不可写并返回 `EACCES`/`EPERM`，`setup` 会自动回退到 CLI 自己的用户级 prefix，并在可写的用户 bin 创建命令；只有该目录尚未进入 PATH 时才会返回 PATH 提示，不要求默认使用 `sudo npm install`。

`makaron-ad login` 只需执行一次：CLI 会先校验 API key，再保存进当前 Mac 用户的系统钥匙串。此后用户和其他 Agent 执行 `create`、`run`、`credits` 时会自动读取，不会反复询问，也不会把 key 写进项目、配置 JSON、日志或 Git。需要更换账号时运行 `makaron-ad logout`，再重新 `makaron-ad login`。

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

这一条命令会自动：查找 Skill 元数据和 ID、为“Skill ID + 输入图 SHA-256”创建或复用隔离的 Makaron 项目、只生成所选语言的文案、对应 App 操作视频和成片、重试失败节点、做 QC 并打包交付。同一 Skill 与同一张输入图会继续复用；更换输入图不会混用旧素材；媒体数量达到保护阈值时会自动轮换到新一代项目并保留历史绑定。映射固定为 `en→英语录屏`、`ja→日语录屏`、`yue→繁体中文录屏`。After 不再按固定百分比抽帧：Makaron 会分析完整效果视频并导出最精彩且稳定的真实源帧；对比图也由 Makaron 基于锁定的 Before/After 像素排版。

录屏节点直接运行用户提供的 v5 `edit-makaron-app-workflow-recording` 通用 Skill，不再调用不匹配的 `screen-demo`。CLI 传入 Marketplace Skill ID 和所选 UI 语言；v5 自动读取真实目录顺序、Skill 封面、localized label/prompt 与所需输入，确定性生成 4 秒 iOS 操作视频，并要求 keyframe sheet、QC JSON 和 version-2 manifest 同时通过。无需人工录屏。

每条成片固定采用 `Hook 视频 → 对比图 → 录屏视频 → 效果视频 → Logo CTA 视频`。目标 Skill 只生成一次连续 Effect；CLI 从开头提取 Hook，再从后续不重叠区间提取 Result，并在 QC 中核对同一个 Effect SHA-256 和时间范围。节奏会在 15–20 秒内自适应：Hook 通常约 2.5 秒，对比图约 2.5 秒，录屏约 4 秒，效果段保留后续完整 payoff。视频模型优先 Seedance 2.0，失败才依次回退；输出目标为 1080×1920，最低接受 720×1280。

CLI 先用 `makaron music create` 为 campaign 单独生成一条不少于 20 秒的无歌词 BGM；随后每个语言只发一条绑定项目的 `makaron chat`，默认调用内置 `tiktok-video` 的 Remotion composition runtime。运行时先生成 Seed Audio 年轻女声并取得真实 Caption JSON 时间，再按旁白边界安排 Hook/对比图/录屏/效果段，确保第二句完整落在对比图、第三四句完整落在录屏，所有旁白和字幕在 CTA 前结束。全部素材静音，同一 BGM 从头循环到 CTA 结束。字幕只有一组：白字黑描边、无底条、水平居中、最多两行、每行最多 20 个可见字符；模板和回退渲染都会清除手工换行及字面量 `\\n`，由实际宽度自动换行。Meta Reels 默认预留顶部 250px、底部 340px、左侧 90px、右侧 180px，字幕从 y=270 起；旧的距顶 140px 不用于 Meta，因为会被平台 UI 遮挡。

Final 节点不会把本地大视频直接交给 Makaron CLI 的 signed-URL PUT 通道。原生 1080×1920 的权威 source URL 会直接复用；Effect 衍生的 Hook/Result、v5 workflow 与固定 CTA 若来自本地或低分辨率，会先用自适应 CRF 规范为 1080×1920 的上传代理，再通过 `makaron admin upload` 以 CDN URL 引用并按 SHA-256 缓存。它不再为了 4 MiB 限制把全部素材固定降成 720×1280。BGM 和 Makaron 对比图优先复用原始 CDN URL。

CTA 原声不使用，也不再走本地 edge-tts、FFmpeg concat/amix、ASS 字幕或 PIL 最终合成。如果 Makaron 已生成的 Remotion design 因平台 `Forbidden` 无法 materialize，CLI 会保留失败响应中的完整 design，先把其中素材 URL 重新绑定到当前 campaign，再用固定版本 Remotion 渲染这同一份、通过同步字幕/场景边界 contract v2 的 design；不会误用项目旧素材，也不会把上传的 CTA/素材附件当成最终视频。回退 runtime 支持 Remotion `Loop`，保证整条 BGM 铺满成片。

随 npm 包同时内置完整 10 秒 Makaron Logo 动画母版和同源的 3 秒无声投放片段。新 Campaign 使用可跨电脑解析的 `bundled://makaron-logo-cta-3s.mp4`；旧 `bundled://makaron-logo-cta.mp4` 配置仍兼容，并在 final 传输时自动改用同源 3 秒片段。它只有约 207 KB，可通过后端上传限制；其他 Agent 不依赖这台电脑的 Desktop 路径，也不会让模型重画 Logo。

提交图片即表示图片拥有投放素材制作所需的授权、真人为已授权成年人，且不会用生成结果支持虚假 Claim。这不代表授权自动发布广告。

内部仍保留 `run/status/retry/complete` 等恢复命令供 Agent 自动处理故障，但最终用户无需填写这些参数。`run/status` 接受 Campaign ID、Campaign 目录或完整 `campaign.json` 路径。运行状态默认保存在 `~/.makaron-ad-creator/workspace/`；进程异常中断留下的孤儿 `RUNNING` 节点会在下次 `run` 时回到 `PENDING`，不消耗一次虚假重试，也不会重做已 PASS 节点。

检查当前电脑是否安装完整：

```bash
makaron-ad doctor
```

源码开发者仍可运行 `bin/makaron-ad`；普通用户和 Agent 应使用 npm 安装后的 `makaron-ad`。

## Design decisions

- Final ad locales can be any selected subset of English, Japanese, and Hong Kong Cantonese; the default remains all three.
- App UI mapping is fixed: English uses English, Japanese uses Japanese, and Cantonese uses Traditional Chinese.
- Final structure is fixed to an Effect-derived Hook → comparison image → v5 workflow video → later non-overlapping Result from the same Effect → bundled Logo CTA; one project-bound Makaron chat drives the built-in `tiktok-video` Remotion runtime for measured Seed Audio captions, Meta-safe placement, CTA, and the final mix.
- Final duration adapts from 15–20 seconds; the shared timing bounds were calibrated from supplied English, Japanese, and Cantonese finished ads rather than forcing every Skill to 18 seconds.
- The complete 10-second Logo CTA master and a same-source silent 3-second delivery excerpt are bundled for portability. Final transport uses the small excerpt, preserving legacy campaign compatibility, and keeps the campaign BGM playing through it.
- One instrumental BGM is generated per campaign with `makaron music create`, reused for every selected locale, and mixed at relative volume `0.22` from frame zero through the final CTA frame.
- A Skill and exact input-image fingerprint are bound to one persistent Makaron project generation per Agent scope. A different image is isolated, media-capacity rotation preserves binding history, and `--project auto` is rejected.
- No per-asset approval is required after rights, claims, project binding, and offer are configured. Failed nodes retry independently.
- Final nodes accept only newly generated video outputs, never uploaded source attachments. A valid Makaron Remotion design can be rendered by the bundled local Remotion fallback when the platform exporter is unavailable; the same design props, Seed Audio voiceover, captions, and BGM are preserved.
- Publication is never automatic. Delivered review state is `PAUSED` / human approval required.
- Synthetic workflow video is produced by the bundled v5 `edit-makaron-app-workflow-recording` Skill from live Marketplace metadata and locale-specific iOS baselines. Its deterministic QC and manifest are required; it is never labeled as genuine device recording.

## 内部维护命令

```text
make IMAGE SKILL_NAME          与上方二参数入口等价
doctor                         check Python/Pillow/FFmpeg/Makaron/runtime assets
init                           write campaign.json and plan.json
plan <campaign.json>           inspect deterministic DAG
run <id|dir|campaign.json>     execute or resume
status <id|dir|campaign.json>  inspect state and lineage
complete ...                   attach another Agent's artifact; final-* also requires the Remotion timing-manifest JSON
fail ...                       report a failed Agent request and use the next retry
retry --node <id>              reset one node and downstream dependents
```

## Delivery

Successful campaigns place only the selected MP4s and audit package in `<campaign>/deliverables/`. The npm package keeps the original five-Skill directory structure, but only `makaron-ad-creator` is installed as the public Agent entrypoint. The master CLI internally runs the bundled, unmodified v5 `edit-makaron-app-workflow-recording` synthetic workflow for each selected locale.
