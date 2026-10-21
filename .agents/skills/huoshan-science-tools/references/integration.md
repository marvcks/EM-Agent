# 共用执行服务与两个用户入口

以 [科学应用文档](../../../../docs/em-agent-science-apps.md) 和当前实现为准。下面是源码定位与接入边界，不是要求每个工具都复制 MAGUS 的实现。

## 先选最小、真实可用的工作流

明确这次开放的任务类型、输入格式、模型/方法、体系范围、参数与单位、输出和成功条件。一个软件功能很多时，先完成用户所需且已验证的子集，不要把仅验证过的单点或分子模式描述成全功能支持。

当前队列针对火山单机演示：串行、最多 10 个排队/运行任务，每项最多 8 核、申请 8192 MB、128 原子；手动页面任务限 900 秒，Agent CLI 提交无平台总时长上限，由 Agent 监控并决定取消；申请内存不是 OS 硬隔离。新工具需在这些约束内运行。不同输入类型要有自己的严格解析与契约，不要把周期晶胞、多组分或非结构输入伪装成一个普通分子 XYZ。

## 科学服务

| 位置 | 需要核对/扩展的行为 |
|---|---|
| `tools/science_apps/service.py` | `APPLICATIONS`、`JobRequest`、`application_executable`、`prepare_input`、执行参数/环境、成功判据、结果字段 |
| 工具独立 runner / 包装器 | 生成受控原生输入，在专用解释器运行，验证并导出结果 |
| `tools/science_apps/test_service.py` | 严格校验、提交、失败、停止/超时、结果单位、历史与下载边界 |
| `docker/EM-Agent.Dockerfile` | 打包适配器、CLI 和使用技能；不打包大型运行环境或权重 |
| `scripts/em-agent/deploy-image.py` | 所需路径检查、只读挂载、现有卷保留、候选与回滚配置 |

当前 `prepare_input` 的末尾是 Gaussian 输入生成；新增工具必须有明确的适配分支，避免只登记应用 ID 就意外落入该路径。当前 `SCIENCE_MOUNTS` 又受 MAGUS 镜像标签条件控制；其他工具增加挂载时应明确自己的生效条件并验证回滚，不能假定任何安装目录都会自动进容器。

保留以下行为：

- `/api/science` 是本 fork 的独立服务例外，不扩展 SDK/Agent Server API；主服务只绑定 loopback，入口同源代理。纯科学服务新增字段不因此要求提高 Agent Server 兼容版本。
- 目录可用性根据容器内实际程序、必要解释器/权重/许可证条件判断，避免每次刷新目录都下载模型或运行重计算。“可用”也不保证所有方法已验收。
- 输入采用字段白名单、范围、有限数值与科学约束；调用使用参数数组，不接受任意 shell、可执行脚本或未校验原生输入。
- 沿用队列、独立任务目录、进程组终止和日志限制；仅手动任务执行平台超时。用户停止需结束子进程，而不仅是修改数据库状态。
- 成功至少包含退出码、原生终止/收敛标志和对应结果验证。某些工具正常退出仍可能 SCF 失败、候选未收敛或结果不完整，应保留日志并返回真实状态。
- 明确结果单位与归一化范围；不要把 eV 填入 `energy_hartree`，也不要混淆每原子、每分子与整个晶胞的能量。
- 复杂输出可生成 `result.json` 和 ZIP，原生输入、日志与结构可追溯。继续沿用顶层普通文件下载边界，不跟随符号链接或开放任意路径。
- 任务数据存入已有 `~/.openhands/science-apps` 持久卷；重启后的排队/运行任务按当前规则标失败，不暗中重跑。

## Agent 对话入口

通常用**现有终端工具 + 小型 CLI + 工具使用技能**，不需要创建新的 MCP 服务或重写 Agent 编排。优先让 CLI 调用同一个科学队列，使两个入口的资源、日志、历史和取消行为一致。

当前可参考：

- `tools/science_apps/em-magus`：CLI 的提交、查询、取消、下载以及运行时 session key 读取。
- `tools/science_apps/skills/magus/SKILL.md`：科研用户需要知道的适用范围、参数单位、命令和结果解读。
- `docker/entrypoint.sh`：已存在的用户技能发现方式；MAGUS 在无同名用户技能时链接自带技能到 `~/.openhands/skills/magus`。

CLI 对 /jobs、/documents 提交及 /apps 查询应发送 `X-EM-Agent-Source: agent`。服务将来源持久化到 job.json；省略来源（含旧记录）按手动任务处理。此标记是同一可信运行时的执行策略选择，不是鉴权边界。Agent 仍通过同一队列提交、查询和取消，不绕过队列。

新增 CLI 时不要把 API key 写入命令参数、文件样例或技能正文；使用已有运行时环境并避免打印凭据。保留已有同名用户技能或禁用偏好，先处理命名冲突，不静默覆盖。确认 SDK 实际发现技能、新对话能加载，再说 Agent 入口已经接入；旧对话不会自动获得新技能上下文。

面向 EM-Agent 用户的工具技能应简短说明“何时用、如何调、如何判断结果”。安装排障、Docker 发布和本地开发经验属于当前本地 `huoshan-science-tools` 技能，不塞入用户的科研上下文。

## 手动页面

| 位置 | 需要同步的内容 |
|---|---|
| `src/api/science-apps-service.ts` | 应用 ID、目录/请求/结果类型、示例数据；沿用同源和运行时 session key |
| `src/routes/science-apps.tsx` | 应用允许项；当前由 `SCIENCE_APP_IDS` 控制 |
| `src/components/features/science-apps/science-apps-page.tsx` | 卡片/分类、适用说明、参数、任务类型、提交、错误、结果单位及下载 |
| `src/i18n/translation.json` | 所有新增 UI 文案；生成声明并检查全部 locale |
| `__tests__/components/features/science-apps/science-apps-page.test.tsx` | 真实表单参数契约、不可用状态、状态恢复及必要结果行为 |

前端不随对话 backend 切换科学服务地址或凭据，手动页面不发起 LLM 调用。展示科研参数和有意义的说明，避免让用户配置内部 Python 路径、Docker、shell 或开发参数。

工具切换时恢复适合该工具的默认值与示例。检查按钮名称与实际示例一致、单位清楚，模型不支持的电荷/自旋不应仍显示成可任选。不能只加一张“可用”卡片而遗漏真实表单、后端允许项或提交链路。
