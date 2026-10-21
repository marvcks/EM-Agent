# 持久化分析环境与 Agent 技能

## 使用

新对话的 bash 终端默认使用
`/opt/em-agent-tools/analysis/.venv/bin/python`（Python 3.11.15）。已有项目显式
激活的虚拟环境优先。Agent Server、automation 和科学服务仍使用镜像原有 Python。
Claude ACP 启动器只给自己的 CLI 子进程设置分析环境，因此通过 `sh` 执行的
ACP 终端同样使用新解释器，不依赖 Bash 的启动文件。

`em-env --json` 返回实际解释器、已安装包版本和科学 CLI 路径；同一份环境说明通过
现有 runtime-services 元数据进入新对话，包含使用入口和可写性说明。

分析包包括 NumPy、SciPy、pandas、Matplotlib、scikit-learn、RDKit、ASE、spglib、
pypdf、PyMuPDF、pdfplumber、openpyxl、python-docx。直接和间接依赖由
`tools/em_agent_runtime/pyproject.toml`、`uv.lock` 锁定。环境只读；额外依赖在项目
自己的 `.venv` 安装。不要修改 Agent Server Python 或其他科学工具的独立环境。

镜像提供 `pdftotext`、`pdftoppm`、`pdfinfo`。本地快速读 PDF 可直接用这些工具或
分析环境的 PDF 库；科研文献完整提取仍可使用既有 MinerU 技能和 `em-mineru`。

## 安装与部署

在火山的完整发布提交中执行：

```sh
bash scripts/em-agent/install-analysis-runtime.sh
bash scripts/em-agent/build-image.sh FULL_COMMIT
python3 scripts/em-agent/deploy-image.py deploy --image em-agent:FULL_COMMIT --commit FULL_COMMIT
```

安装器使用已有的容器可见 Python 3.11.15，`uv sync --frozen` 创建环境并保存
`manifest.json`。已存在 manifest 时拒绝静默覆盖，应先检查现有安装及升级方案。
镜像带 `io.em-agent.analysis=1`，部署器检查安装及锁文件散列，再添加只读挂载。
安装器、环境和依赖缓存不进入 Git。镜像中的 Poppler 包版本记录在
`/opt/em-agent/pdf-runtime.txt`，完整系统包清单在相邻
`pdf-runtime-packages.tsv`。PDF 依赖放在独立的镜像缓存层；固定 Poppler 版本，通过
清华 Debian 镜像和 Debian 原有签名密钥验证安装。临时安装源不会替换镜像原有软件源。

分析环境与共享解释器在宿主机持久保存，重建容器后继续挂载。Claude 状态新增保存到
宿主机 `/opt/openhands/claude-state`，挂载为 `/home/openhands/.claude`；首次部署
迁移原目录，回滚继续保留该挂载和既有工作区。

## Claude Code ACP 技能同步

OpenHands 继续通过自己的用户技能机制加载。Claude ACP 启动包装器在原适配器启动
前，把 `~/.openhands/skills` 中启用的 AgentSkills 链接到 Claude 原生技能目录。
Claude 可以使用原生 `Skill`，无需猜测 OpenHands 专属的 `invoke_skill`。

启停设置仍由 Canvas 的 `misc_settings.app_preferences.disabled_skills` 管理。
启动时读取最新设置；缺失该字段时才兼容旧 agent-context 的禁用列表。新会话刷新技能，
既有运行会话保持其已加载快照。包装器遵循 `CLAUDE_CONFIG_DIR`，支持 SDK 的配置隔离。

同名原生用户技能优先，绝不覆盖；同步状态只记录自己创建的符号链接，技能禁用或源
删除时只清理这些链接。公共技能目录不会被额外复制，MCP 和模型凭据配置保持原样。
配置损坏时拒绝启动同步，避免忽略禁用设置后错误暴露技能。

## 验证

```sh
uv run --python 3.13 --with pyyaml==6.0.3 python -m unittest discover -s __tests__/scripts -p test_em_agent_runtime.py -v
python3 -m unittest discover -s __tests__/scripts -p test_em_agent_deploy.py -v
npx vitest run __tests__/scripts/runtime-services-info.test.ts
```

上线还要以实际容器用户验证：新任务终端的 `python`/`pip` 路径、项目虚拟环境优先、
科学 CLI、真实 PDF 文本与页面渲染、画图和无害分子结构处理；再分别用原生 OpenHands
和 Claude ACP 新会话验证解释器、技能发现和调用。安装成功不能替代自然语言调用验收。
