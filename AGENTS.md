# Repository Notes

## EM-Agent 项目交接（优先于下方上游通用约定）

- 当前开发仓库是本目录 `EM-Agent-OpenHands`，fork 为 `marvcks/EM-Agent`，开发分支 `codex/em-agent-ui`。旧 `/Users/xhxu/Documents/EM-Agent` 的 Google ADK 项目仅作界面参考，不再扩展旧后端。
- 产品定位：OpenHands 提供 Agent、工作区、MCP、Skills、终端和文件能力，保留这些功能；前端采用 EM-Agent 的浅色科研工作台外观。隐藏第三方 Apps 管理、扩展页面及原生 Git 账户连接入口；保留自定义 MCP 配置、Skills 和插件。
- “科学应用”是用户手动操作的软件工作台：选应用 → 上传/粘贴 XYZ → 配置参数 → 提交 → 日志/停止/结果下载。它不通过 Agent 或 LLM 调用。用户日后自行编写材料发现等研究流程的 Skills，不要重写 Agent 编排。
- 已接入 xTB、ORCA、Gaussian、MAGUS（MACE-OFF23 分子晶体搜索）与晶体形貌判别（LLM-105/PSI 预训练表格分类），按实际可执行文件与必要运行时/模型检测是否可用。晶体形貌判别输入为五项结晶工艺参数或同表头 CSV，输出“其他/球/针”及未校准概率；训练范围之外的行标记为外推。扩展应用在 `tools/science_apps/service.py` 的目录和输入适配器中添加，并同步请求类型、UI 说明与测试。不得把模拟结果标成真实计算。
- 当前仅面向火山单机演示（SSH 别名 `huoshan`，32 逻辑核、约 64 GB），无需设计复杂多租户/高并发系统。科学任务串行，队列最多 10 项；每项最多 8 核、申请内存 8 GB、最多 128 原子；手动页面任务运行最多 15 分钟，Agent CLI 提交的任务无平台总时长上限，由 Agent 监控并决定停止。xTB 自行管理内存，这不是操作系统内存隔离。
- 手动科学任务属于本 fork 的独立服务 `/api/science`，不改变 SDK/Agent Server API；前端唯一适配器 `src/api/science-apps-service.ts` 使用同源和运行时 session key，不能跟随对话后端切换。此服务是下方仓库所有权/API 规则的明确项目例外。
- 科学应用通过 `docker/EM-Agent.Dockerfile` 启用。`docker/entrypoint.sh` 用 `EM_AGENT_SCIENCE_APPS=1` 启动 loopback 服务 `:18002`，入口代理 `/api/science`，数据保存到已有持久卷 `~/.openhands/science-apps`。重启后未结束任务标为失败，不自动重跑。
- 部署统一从 fork 的完整提交构建镜像：`scripts/em-agent/build-image.sh <40位提交>`；火山 `/opt/openhands/source` 为源码，`scripts/em-agent/deploy-image.py` 做检查、备份、切换与回滚。不要在线直接改容器源码或覆盖前端目录。详见 `docs/em-agent-deployment.md` 与 `docs/em-agent-science-apps.md`。
- 当前已验证公网入口：`https://180.184.134.230/canvas/`（科学应用 `/canvas/science-apps`），Basic Auth 用户 `openhands`；密码只在服务器私有凭据记录中。旧 `openhands.*.sslip.io` 域名被云平台拦截，不再向用户提供。IP 的 Nginx 入口已转发 OpenHands 8000，详见部署文档。
- 保留火山现有对话、workspace、MCP/Skills 配置和科学软件挂载。凭据仅用环境和现有私有配置，严禁提交。用户常用语音输入，按上下文理解转写，不必逐项纠错。

## General

- This repository is the OpenHands Agent Canvas React/TypeScript frontend.

## i18n workflow
- After editing `src/i18n/translation.json`, run `npm run make-i18n` to
  regenerate `src/i18n/declaration.ts` (gitignored, auto-generated) and
  `scripts/check-translation-completeness.cjs` to confirm full locale coverage.
- Removing an i18n key: delete the whole locale block from translation.json,
  then `make-i18n`, then remove any test-mock entries (tests inline a
  `translations` map in the `useTranslation` vi.mock).

## Commit messages
- The persistent shell can garble long multi-line `commit -m` bodies (echo
  loop corrupts the stored message). Use `git commit -F <file>` with a
  written temp file instead of `-m` for any non-trivial message.

- Primary verification commands are `npm run lint`, `npm test`, `npm run build`, and `npm run build:lib`.
- Direct dependencies and dev dependencies are exact-pinned. Use the committed `package-lock.json` with `npm ci`, and update `package.json` and `package-lock.json` together through npm.
- Public skills come from `@openhands/extensions`; project-specific contributor guidance lives under `.agents/skills/`.
- Default working-directory behavior must reuse `DEFAULT_WORKING_DIR` from `src/api/agent-server-config.ts` rather than hardcoding `/workspace/project`.
- All pull requests must comply with [`.agents/skills/custom-codereview-guide.md`](.agents/skills/custom-codereview-guide.md), in addition to the general contribution requirements and CI checks.

## Repository Ownership

Before adding code, confirm that the change belongs in this repository.

| Repository | Owns | Add code there when… |
|---|---|---|
| [`OpenHands/OpenHands`](https://github.com/OpenHands/OpenHands) | Agent Canvas UI, frontend state, backend selection, frontend service integration, and local-stack orchestration. | Changing UI, frontend state, or how Canvas consumes an existing API. |
| [`OpenHands/software-agent-sdk`](https://github.com/OpenHands/software-agent-sdk) | Python SDK, Agent Server, agents/tools, conversations, events, canonical REST/WebSocket API, and `clients/typescript/`. | Adding or changing backend behavior, endpoints, wire contracts, or typed client access. |
| [`OpenHands/extensions`](https://github.com/OpenHands/extensions) | Reusable public skills, automations, plugins, and integrations. | Adding or editing reusable extension content rather than Canvas behavior. |
| [`OpenHands/automation`](https://github.com/OpenHands/automation) | Automation definitions, scheduling, webhooks, run history, and dispatch. | Changing when automations run or their scheduling/webhook lifecycle. |

The normal dependency direction is Agent Server contract → TypeScript client → Agent Canvas. Do not reimplement Agent Server endpoints or contracts in Canvas.

## Shared Frontend Change Checklist

Before changing a shared adapter, conversation builder, setting, state selector, or presentation helper:

- Raise `compatibility.minimumAgentServer` in `config/defaults.json` when Canvas begins requiring a new Agent Server endpoint, field, schema, or behavior.
- Enumerate affected consumers across Local and Cloud backends, OpenHands and ACP agents, standard/planning/delegated conversations, and standalone and embedded Canvas. Test every path with distinct control or data flow without testing an irrelevant Cartesian product.
- Give durable frontend state one named owner and one obvious writer. Handle existing-state hydration or migration and all supported create, update, delete, default, and active-item transitions. Leave destructive transitions in a deterministic valid state or an explicit empty state handled by the UI.

## PR Description Human Check

The `HUMAN:` section in PR descriptions is reserved for human contributors only. AI agents must not add to, edit, move, or remove it. If validation fails because it is missing or empty, stop and ask the human user to update it in their own words. If a human already updated it, report the exact validator error rather than editing it.

## Functionality-Specific Skills

Detailed contributor knowledge is split into skills so it loads only for relevant work. Invoke every applicable skill before changing that area; cross-cutting changes may require several skills.

| Skill | Use for |
|---|---|
| [`huoshan-science-tools`](.agents/skills/huoshan-science-tools/SKILL.md) | 在火山安装科学软件，并接入 EM-Agent 对话与科学工具广场的手动参数页面；包含环境隔离、两个入口、验收及部署交接。 |
| [`telemetry-analytics`](.agents/skills/telemetry-analytics/SKILL.md) | PostHog, telemetry consent/identity, typed tracking events, Cloud funnel observability, and onboarding instrumentation. |
| [`e2e-testing`](.agents/skills/e2e-testing/SKILL.md) | Live or mock-LLM Playwright suites, Docker E2E, E2E CI/reporting, artifacts, and failure diagnosis. |
| [`frontend-api-contracts`](.agents/skills/frontend-api-contracts/SKILL.md) | `src/api`, typed Agent Server calls, Cloud/runtime transport, compatibility, backends, settings, secrets, auth, and conversation contracts. |
| [`local-stack-runtime`](.agents/skills/local-stack-runtime/SKILL.md) | Dev launchers, runtime-services metadata, ingress, automation startup, process shutdown, centralized versions, and Docker. |
| [`desktop-electron`](.agents/skills/desktop-electron/SKILL.md) | Electron startup, branding, packaging, bundled Node/uv, universal macOS builds, and desktop CI. |
| [`frontend-development`](.agents/skills/frontend-development/SKILL.md) | React/UI work, i18n, named identifiers, MSW mock mode, lazy loading, bundle performance, and feature-specific UI invariants. |
| [`pr-design-doc`](.agents/skills/pr-design-doc/SKILL.md) | Writing the PR design document stored in the PR body. |
| [`release`](.agents/skills/release.md) | Cutting and verifying an `@openhands/agent-canvas` release. |
| [`verify-openhands`](.agents/skills/verify-openhands/SKILL.md) | Driving the real app like a user with `control-openhands`, the feature map of every user-facing behavior, and creating or maintaining that map. |

The detailed rules live in each skill's `references/guide.md`; do not copy them back into this file. Update the owning skill whenever an invariant changes.

## Testing Baseline

Create TDD tests for behavioral changes. Keep tests focused on user behavior and real code paths:

- Use Arrange, Act, Assert structure and clear test data.
- Avoid duplicate cases and duplicate assertions.
- Mock an underlying service rather than the hook that consumes it.
- Extend an existing test file when it is a natural home; create a new file only when necessary.
- Avoid brittle presentation-only assertions. Test functional CSS contracts directly when they are behavior.
- Do not mirror literal source, fixture, translation, or class-string definitions in tests. Assert consumer behavior or an actual build/runtime contract instead, and do not export internals solely to make them testable. Preserve coverage for routing, accessibility, async behavior, behavioral contracts, and functional CSS/build contracts.
- Use the minimum number of cases that fully cover the intended behavior and edge cases.

Use the `e2e-testing` skill for suite selection and E2E-specific requirements.

## Specifications and Releases

- Spec files live under `specs/`. Keep spec IDs stable and mark deprecated specs with strikethrough rather than renumbering them.
- Tag implementation code and tests with `// @spec BM-002 — Short title` comments immediately above the relevant block so coverage remains grep-able.
- Follow `.agents/skills/release.md` for release automation. Never hand-edit a release-please branch.

## DigitalOcean Managed Agents

Before changing `scripts/mars-*` / `scripts/tunnel-*`, `src/api/mars/`, the Managed Agents UI (`src/components/features/backends/managed-agents/`) or the MARS hooks, read `src/api/mars/AGENTS.md`.
