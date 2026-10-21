# 验收、部署与交接

## 验收层级

只执行用户当前授权范围内的步骤。后续阶段未完成时记录“尚未接入/未测”，不要用前一阶段代替后面的证据。

| 层级 | 有效证据 | 尚不能证明 |
|---|---|---|
| 宿主机 | 官方/用户输入的最小真实计算，原始输出及科学检查 | 容器或页面可用 |
| 容器 | 目标镜像、实际运行用户、最终路径/只读挂载下完成原生小计算 | Agent 发现或页面提交成功 |
| Agent | SDK 发现使用技能；同一 Agent 容器中的 CLI 真正提交、查询、停止/下载 | LLM 已按自然语言正确完成调用，除非实际验证过 |
| 手动页面 | 从真实页面输入/上传、提交、观察真实计算状态、停止和下载 | 未测试的工具方法或体系都可靠 |
| 线上发布 | 完整提交/镜像一致、健康与数据校验、公网两个认证层及真实入口 | 科学结论达到生产科研精度 |

科学验证随工具选择：分子完整性、电子数与自旋、SCF/优化收敛、有限能量/力/应力、周期边界等。MLIP 可用独立重算、有限差分检查力/应力，以及平移不变性。不要把 MAGUS 的每项检查机械要求于所有软件。

保留输入、版本、模型来源/散列、资源参数、原生日志、输出和验证摘要。失败尝试若说明关键限制或上游问题，应与最终成功测试分目录保存，清楚标记原因，不混入最终模板。

## 测试与 UI 验证

行为改动先写聚焦测试，再实现。优先扩展现有测试文件；测试实际请求/结果行为，不镜像源码和文案。单元测试中的模拟进程是契约测试，不能计为真实科学验收。

根据改动选取命令，必要时扩大到仓库要求的检查；Python/FastAPI 版本应先核对当前文档和镜像，不把下面示例当永久版本锁：

```sh
uv run --python 3.13 --with fastapi==0.143.0 --with httpx --with uvicorn==0.54.0 \
  python -m unittest tools.science_apps.test_service
python3 -m unittest discover -s __tests__/scripts -p test_em_agent_deploy.py -v
npx vitest run __tests__/components/features/science-apps/science-apps-page.test.tsx \
  src/api/no-direct-agent-server-calls.test.ts
npm run make-i18n
npm run check-translation-completeness
npm run typecheck
npm run build
npm run build:lib
```

如依赖目录尚未准备，用仓库锁文件安装；不要临时升级全局 Node 或 npm 包。项目需要 Node 24+；本机 Homebrew 的可执行文件曾因 dylib 损坏无法运行，可检查已提供的可用 bundled runtime。

真实页面验收至少覆盖入口可见、参数与示例正确、真实提交成功、日志、运行中停止、结果下载/单位和历史恢复；桌面/窄屏按变更检查。通过浏览器点击的下载应检查文件/ZIP 完整性，必要时与服务器原文件散列比对。不要用拦截接口或伪造科学结果凑成功截图。

网页刚导航时 React 数据可能尚未加载；等待目标状态后再判断故障。部署重启过程出现的短暂 502 与部署完成后仍存在的错误分别记录。浏览器配置中的 Basic Auth 和页面内 session key 都是私有信息；截图/快照需避开设置或 onboarding 中的凭据字段。

macOS 的旧 Bash 与 Linux 行为可能不同。既有 `docker-session-key-policy` 测试曾因本机 Bash 环境失败；应核对具体错误、在目标 Linux 验证原策略，准确记录未通过项，而不是改鉴权策略来使本机测试变绿。

## 发布流程

详情以 [部署文档](../../../../docs/em-agent-deployment.md) 与当前脚本为准。

1. 代码与必要文档进入用户授权发布的 fork 提交；只加入本次文件，不把用户其他未提交文件、安装器、权重或凭据混入。非简单提交信息用 `git commit -F`。
2. 火山 `/opt/openhands/source` 获取该完整提交；先检查远端工作树，保留其已有修改，不强制重置。
3. 对确切的 40 位提交执行 `bash scripts/em-agent/build-image.sh COMMIT`。脚本用 `git archive` 构建并核对最终镜像导入；未提交文件不会进入镜像。
4. 确认新工具运行时路径/权限与挂载准备好，使用 `python3 scripts/em-agent/deploy-image.py deploy --image em-agent:COMMIT --commit COMMIT`。
5. 部署脚本会检查活动对话与科学任务，备份并保留既有卷、核对会话及工作区文件、健康检查，失败回滚。遇到活动任务等待空闲后重试，不擅自取消用户任务或绕过检查。
6. 对照 `/opt/openhands/current-image.json`、容器 revision/image ID、`/opt/em-agent/release.json`。再验证公网页面与最终工具调用；只在容器内得到 200 不足以证明发布完成。

当前公网入口在 `docs/em-agent-deployment.md`，2026-10-19 验证为 `https://180.184.134.230/canvas/`。使用现有 Basic Auth，不回退到被拦截的旧 sslip.io 域名。科学 API 还需运行时 `X-Session-API-Key`；带 Basic Auth 的页面 200 与缺少 session key 的 API 401 各有含义，不能混作健康证据。

更新前保留既有工作区、对话、MCP/Skills、LLM 配置、科学任务目录和软件挂载。不要在线 `docker exec` 改应用源码作为发布，也不要为新工具升级无关 SDK 或自动化版本。发布后的额外文案/代码改动也须构建新提交镜像；重新部署前等待验收任务结束。

## 本地交接记录

在当前本地项目保存报告，服务器工具目录可镜像副本。报告包含：

- 安装与最终运行路径、版本、来源/锁文件/模型散列、依赖和已知限制。
- 各层验收状态与真实任务 ID、输入/结果位置；已测和未测范围。
- 应用入口、Agent 使用技能/CLI、是否需要新建对话，以及结果单位和适用体系。
- 发布完整提交、镜像 ID、release/rollback 目录、数据保留校验及测试结果。

不要把 MAGUS 历史的“6 个对话、75 个文件”等数量写成下一次的预期常数。每次读取真实基线，比较实际保留情况。也不要把过去的完整提交号作为今后发布目标。
