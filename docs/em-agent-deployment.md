# 从 fork 的指定提交部署 EM-Agent

生产代码来源为 `https://github.com/marvcks/EM-Agent`，开发分支为
`codex/em-agent-ui`。每个部署使用完整 Git 提交号及不可变的本地镜像 ID，
不使用 `latest` 选择线上版本。

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
