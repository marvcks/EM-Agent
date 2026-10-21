---
name: huoshan-science-tools
description: 在 SSH 别名 huoshan 的服务器安装、配置科学软件，并接入 EM-Agent 对话调用和科学工具广场的手动参数页面；用于新工具上架、补接入、部署及验收，不用于日常执行已安装工具的科研计算。
---

# 火山科学工具安装与上架

把科学软件接入当前 EM-Agent fork，交付两条入口：Agent 在对话中通过现有终端能力调用工具；用户在科学应用页面输入参数、提交、看日志、停止并下载结果。手动入口独立运行，不经过 LLM。

本技能是**本地开发/运维技能**，位于当前仓库 `.agents/skills/`。不要把它复制成服务器上面向用户的科研工具技能；后者按工具另写，见接入参考。

## 开始前

1. 读取当前仓库 [AGENTS.md](../../../AGENTS.md)、`tools.md` 的相关工具条目，以及 [科学应用文档](../../../docs/em-agent-science-apps.md)、[部署文档](../../../docs/em-agent-deployment.md)。以当前源码和实际环境为准，历史报告不代表现状。
2. 核对本地工作树、fork/分支与用户已有修改。当前项目为 `EM-Agent-OpenHands` / `marvcks/EM-Agent`，旧 Google ADK 项目仅供界面参考。
3. 按用户本轮范围工作。“先安装”“给安装方案”不等于部署；“接入并部署”则持续做到两个入口和线上验证完成。发现缺少必要授权、许可或输入时，说明具体缺项，同时推进不依赖它的准备工作。
4. 修改对应区域前，加载仓库已有的 `frontend-development`、`frontend-api-contracts`、`local-stack-runtime` 等适用技能；真实 UI 验证与 E2E 按各自技能执行。本技能补充科学工具接入经验，不替代这些约定。

## 按阶段读取

| 当前工作 | 参考 |
|---|---|
| 安装软件、下载模型、隔离 Python、准备容器运行环境 | [installation.md](references/installation.md) |
| 科学服务、Agent CLI/使用技能、目录与参数表单接入 | [integration.md](references/integration.md) |
| 原生计算、两个入口验收、完整提交构建、部署与交接记录 | [verification-deployment.md](references/verification-deployment.md) |
| MAGUS/MACE 的版本兼容、势函数和缓存能量问题 | [magus-lessons.md](references/magus-lessons.md) |

## 贯穿全程的约定

- **一个工具一个目录**：服务器管理文件放 `/root/EM-Agent-Tools/<tool>/`；Python 优先用 uv。可复用模型/环境单独成目录，权重共享，不把依赖全装进系统、base Conda 或 Agent Server 的 Python。
- **先验证运行，再上架**：宿主机 root 能运行不代表容器 `openhands` 用户能运行；命令行成功不代表 Agent 或手动页面已经可用。逐层报告实际证据。
- **一个任务执行入口**：对适合当前单机服务的工具，Agent CLI 和手动页面共用 `/api/science` 队列、状态、停止及下载。不要另起一套不受限制的后台运行链路。
- **保持科研语义**：明确适用体系、方法、模型、单位和收敛条件。成功不能只看退出码或输出文件存在；不把模拟、未收敛或不受模型支持的计算标成真实成功。
- **保留现有能力与数据**：不重写 Agent 编排，不改无关 MCP/Skills/LLM 配置，不覆盖现有工具环境、会话、workspace 和挂载。凭据从既有私有配置/环境取用，不写进代码、提示词、日志或报告。
- **部署可追溯**：应用改动进入 fork 完整 Git 提交，用现有构建/部署脚本发布；不能直接改线上容器源码或覆盖前端。安装器、大型权重、运行环境和凭据不进入 Git。
- **本地保留记录**：安装/接入/部署报告写到当前本地项目，通常为 `<TOOL>-installation-report.txt`、`<TOOL>-EM-Agent-deployment-report.txt`；服务器工具目录可保留副本。不要只写服务器或 Downloads。

## 完成时如何交接

分别说明宿主机原生运行、容器运行、Agent 调用、手动页面、线上部署的完成状态与证据。只安装成功时，明确哪些入口尚未接入；完成上架时，给用户页面链接、新对话加载技能的说明、适用范围和本地记录链接。

如果一个工具超出当前机器或队列能力，保留已完成的安装与验证结果，说明需要改变的具体约束；不要悄悄放宽全局限制。可根据本次真实发现修订这个技能，但不要把某个工具的特殊问题提升成所有软件的统一规则。
