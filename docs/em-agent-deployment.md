# 从 fork 的指定提交部署 EM-Agent

分析环境与 Claude Code ACP 用户技能接入见
[持久化分析运行时](em-agent-analysis-runtime.md)。带 `io.em-agent.analysis=1`
的镜像发布前须安装对应锁文件的分析环境；部署器保留 Claude 状态并检查运行时散列。

生产代码来源为 `https://github.com/marvcks/EM-Agent`，开发分支为
`codex/em-agent-ui`。每个部署使用完整 Git 提交号及不可变的本地镜像 ID，
不使用 `latest` 选择线上版本。

## 当前访问入口（2026-10-19）

使用 `https://180.184.134.230/canvas/`，科学应用为
`https://180.184.134.230/canvas/science-apps`。`openhands.*.sslip.io` 域名
从公网访问时被火山云拦截，不能再把该域名作为已验证可用的入口提供给用户。
IP 的有效 HTTPS 证书、现有 Basic Auth 均保留，IP 虚拟主机已转发到
`127.0.0.1:8000` 的 OpenHands；旧 EM-Agent 的域名配置继续独立保留。

登录用户名为 `openhands`。凭据记录保存在火山 `/root/openhands-access.json`
（600 权限），密码不得写入仓库。Nginx 配置为
`/etc/nginx/sites-available/em-agent-ip`，修改前备份在
`/opt/openhands/backup/nginx-em-agent-ip-20261019T084212Z.conf`。
已从服务器和本地 Mac 验证带认证的 HTTPS 请求返回 200，并确认返回
OpenHands Canvas 的运行时 HTML；只检查容器内 200 或未认证 401 不足以
证明用户能从公网打开页面。

## 镜像内容

`docker/EM-Agent.Dockerfile` 使用以下已固定摘要的运行环境：

```text
ghcr.io/openhands/agent-canvas:1.27.1@sha256:6f54e27c47c8073d402391495fa869afca807e9154f0d90bfe05f7ada6ec8ee3
```

构建阶段使用该镜像内的 Node.js、`package-lock.json` 和提交中的源码，运行
翻译、类型和生产构建检查。最终镜像替换前端，附带科学应用独立服务、
启动它的入口脚本及 `/opt/em-agent/release.json`。Agent Server 1.54.0、
Automation 1.19.3 沿用该运行环境。科学服务复用固定镜像内的 FastAPI /
uvicorn；不升级 OpenHands 后端。升级后端基线时需要另行检查兼容性。

镜像的 `org.opencontainers.image.source` 标签指向这个 fork，
`org.opencontainers.image.revision` 标签记录完整提交号。依赖目录、未提交
文件、凭据和宿主机数据不会进入 Git archive 构建上下文。

## 获取源码并构建

在 huoshan 首次准备工作目录：

```sh
git clone --single-branch --branch codex/em-agent-ui \
  https://github.com/marvcks/EM-Agent.git /opt/openhands/source
```

每次选定并检查发布提交后，在服务器执行：

```sh
cd /opt/openhands/source
git fetch origin codex/em-agent-ui
release_commit=$(git rev-parse FETCH_HEAD)
git switch --detach "$release_commit"
bash scripts/em-agent/build-image.sh "$release_commit"
```

也可以将 `release_commit` 设为已审核的完整提交号。脚本使用该提交的
`git archive` 构建，工作目录里的其他改动不会被混入镜像。
默认镜像标签为 `em-agent:<完整提交号>`。镜像在部署服务器本地构建和保留，
本流程不依赖向 Docker Hub 或 GHCR 发布镜像。

## 切换生产版本

### MAGUS 运行时准备

MAGUS 含 CPython 3.10 原生扩展，不能装到 Agent Server 的 Python 3.13 或共享 MACE 的
Python 3.12 环境。火山已经安装并验证：

- `/opt/em-agent-tools/magus/2.2.0/`：原有 MAGUS 发行版及 Python 3.10。
- `/opt/em-agent-tools/magus/mace-runner/.venv/`：用 uv 从
  `/root/EM-Agent-Tools/magus/mace-runner/{pyproject.toml,uv.lock}` 安装的独立环境。
- `/root/EM-Agent-Tools/mace-off23/models/`：原有三份已校验共享权重。

重建运行环境可在宿主机执行（保持 wheel 相对目录关系）：

```sh
mkdir -p /opt/em-agent-tools/magus/mace-runner /opt/em-agent-tools/magus/installers/python-wheels
cp /root/EM-Agent-Tools/magus/mace-runner/pyproject.toml /root/EM-Agent-Tools/magus/mace-runner/uv.lock \
  /opt/em-agent-tools/magus/mace-runner/
cp /root/EM-Agent-Tools/magus/installers/python-wheels/*.whl /opt/em-agent-tools/magus/installers/python-wheels/
uv sync --frozen --project /opt/em-agent-tools/magus/mace-runner \
  --python /opt/em-agent-tools/magus/2.2.0/bin/python
```

带 `io.em-agent.magus=1` 标签的新镜像部署时检查这些路径，并自动添加两个只读挂载：
`/opt/em-agent-tools/magus` 同路径挂载；共享 models 目录挂到容器
`/opt/em-agent-tools/mace-off23/models`。容器用户不需要访问宿主机 `/root`。
权重、安装器和运行环境不进入 Git 或应用镜像。旧版本回滚沿用保存的 Compose。

```sh
python3 scripts/em-agent/deploy-image.py deploy \
  --image "em-agent:$release_commit" --commit "$release_commit"
```

脚本验证镜像来源与提交标签、Compose 配置和会话状态。存在运行中的会话时
会停止部署，等待会话结束后重试；已启用科学应用的镜像还会检查科学任务
是否排队/运行，避免更新打断计算。切换需要短暂停止并重建应用容器。

首次切换时，脚本将旧容器中的以下目录复制到宿主机，并添加持久化挂载：

| 宿主机 `/opt/openhands/` 下的目录 | 容器目录 |
| --- | --- |
| `workspace` | `/home/openhands/workspace` |
| `browser-config` | `/home/openhands/.config` |
| `editor-state` | `/home/openhands/.openvscode-server` |

现有的 `data`、`projects`、科学软件及 scratch 挂载继续保留。首次切换还会
移除旧的前端 bind mount，使页面实际由镜像中的前端提供。旧前端目录留在
宿主机用于回滚。密钥继续从服务器的 `runtime.env` 与持久化数据读取。

停止旧容器后，脚本备份数据与 Compose，按原路径挂载会话文件，再启动新
镜像。新容器必须通过健康检查、科学服务鉴权健康检查（启用时）、历史会话 ID 检查和原工作目录文件的 SHA-256
校验；失败时自动恢复上一镜像及持久化挂载。

部署记录保存在：

- `/opt/openhands/current-image.json`：当前提交与镜像 ID。
- `/opt/openhands/image-releases/<时间>-<提交前缀>/release.json`：发布记录。
- 同一发布目录中的 `compose-original.yaml`、`compose-rollback.yaml`、
  `workspace-sha256.json` 和受保护的 `data-backup/`。

## 回滚

使用对应发布目录执行：

```sh
python3 /opt/openhands/source/scripts/em-agent/deploy-image.py rollback \
  /opt/openhands/image-releases/<对应的发布目录>
```

回滚恢复先前镜像与 Compose，保留切换后产生的会话及工作文件。当前固定
后端版本的切换不涉及数据库 schema 升级，脚本不会自动用旧数据库覆盖新
会话。备份数据仅供出现实际数据故障时单独恢复。

## 核对线上版本

```sh
cat /opt/openhands/current-image.json
docker inspect openhands --format '{{.Image}} {{index .Config.Labels "org.opencontainers.image.revision"}}'
docker exec openhands cat /opt/em-agent/release.json
```

三者应对应同一个发布提交与镜像。部署脚本回归测试：

```sh
python3 -m unittest discover -s __tests__/scripts -p test_em_agent_deploy.py -v
```

### 反应模型运行时

带 `io.em-agent.reactions=1` 的镜像独立检查 AiZynthFinder / lcms2yield 的
解释器、manifest 和必需模型，再添加三个同路径只读挂载：
`/opt/em-agent-tools/python`、`/opt/em-agent-tools/aizynthfinder`、
`/opt/em-agent-tools/lcms2yield`。该条件独立于 MAGUS 标签；既有软件挂载不变，
回滚保留上一版本 Compose。Python 3.11 安装在这个容器可见前缀，避免 venv 的
解释器链接指向宿主机 `/root`。权重、运行环境及安装器均不进入应用镜像。

AiZynthFinder 使用官方源码 4.4.1 及 `download_public_data` 列出的 USPTO
ONNX/模板和 ZINC stock；lcms2yield 使用官方源码及仓库内 `20250721.pth`。
每个工具独立 uv 锁文件，CPU Torch 2.3.0 / PyG 2.5.3 / RDKit 2023.9.6
按 lcms2yield 官方依赖准备；不升级 Agent Server 的 Python 包。
实际来源提交、完整模型散列、锁文件、验收输入与日志保存在各工具管理目录，
本地报告记录最终部署提交与镜像。

AiZynthFinder 4.4.1 要求 NumPy <2；当前 PyArrow 26 wheel 运行时要求 NumPy 2，
其依赖元数据未阻止解析出不兼容组合。该独立环境固定 `pyarrow==20.0.0`，
通过完整路线搜索和依赖检查；不要直接更新为最新 PyArrow。阿司匹林测试的
峰值 RSS 约 5.1 GiB，页面和 CLI 默认申请 6144 MB，仍非 OS 硬隔离。

### BDE 运行时

带 `io.em-agent.bde=1` 的镜像独立检查 `/opt/em-agent-tools/bde` 的 ALFABET venv、
Psi4 环境、manifest、官方预处理文件和模型文件，并添加 BDE 与共享 Python 的只读挂载。
`bde-analyze` 根据受控请求的模式选择解释器；`em-bde` 只通过现有科学 API 提交任务。
启动时仅在无同名用户技能时链接 `bde`。模型文件在安装时下载并校验 SHA-256，推理期间
不联网下载权重。版本、源提交、模型散列及 Python/Conda 锁文件保存在工具目录，安装与
部署证据见本地 BDE 报告。不要在线改容器源码或升级 Agent Server 的包来修复科学依赖。

### 晶体形貌判别运行时

带 `io.em-agent.crystal-morphology=1` 的镜像独立检查
`/opt/em-agent-tools/crystal-morphology` 的 venv、manifest 与模型缓存，再添加
crystal-morphology 与共享 Python 的只读挂载。运行时用仓库内
`tools/science_apps/runtime/crystal-morphology/{pyproject.toml,uv.lock}`
（numpy 1.26.4 / scikit-learn 1.5.2 / xgboost 2.1.2 / lightgbm 4.6.0 / catboost 1.2.8 /
threadpoolctl，Python 3.11）在 `/opt/em-agent-tools/crystal-morphology` 重建：

```sh
uv sync --frozen --project /opt/em-agent-tools/crystal-morphology \
  --python /opt/em-agent-tools/python/cpython-3.11-linux-x86_64-gnu/bin/python3
```

模型缓存安装时复制并记录 SHA-256（`manifest.json`），推理期间不联网、不重训。
启动时仅在无同名用户技能时链接 `crystal-morphology`。具体验收见本地
`CRYSTAL-MORPHOLOGY-EM-Agent-deployment-report.txt`。

### MinerU 云端适配

镜像包含标准库适配器 `mineru-parse`、共用队列 CLI `em-mineru` 和 `mineru` 使用技能。
凭据通过已有 data 挂载中的 `/home/openhands/.openhands/mineru/api-token` 提供；
宿主机对应 `/opt/openhands/data/mineru/api-token`。文件权限 0600，目录 0700，
所有者须为容器实际运行用户；不增加模型/环境挂载或修改 Agent Server 的依赖。
启动时存在该凭据文件且无同名技能才链接 bundled skill。保留同名用户技能及禁用偏好。
更新凭据文件无需重建镜像；首次启用技能需容器启动并新建对话。
入口上传最大 20 MiB，已有 Nginx 100m 限制可容纳。转换失败须检查上游凭据/额度/文档限制，
不能用降级模拟结果验收。完整原始结果包与 Markdown 随 science-apps 数据持久保存。
