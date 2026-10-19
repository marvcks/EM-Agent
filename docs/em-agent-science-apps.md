# EM-Agent 科学应用

入口：侧栏 **科学应用** → xTB / ORCA / Gaussian / MAGUS。用户上传或粘贴标准 XYZ，配置参数，提交后查看状态、日志并下载输入与输出。手动页面与 Agent 对话独立，不产生模型调用。

## 运行与数据

- 自定义镜像会启动 `tools/science_apps/service.py`（FastAPI + uvicorn），容器内 `127.0.0.1:18002`，同源代理 `/api/science`。
- 服务使用既有运行时 `X-Session-API-Key`。没有密钥会拒绝启动，目录/任务/下载均校验密钥。前端始终访问当前页面所在服务器，与切换到其他 Agent 后端无关。
- 状态目录：`~/.openhands/science-apps/<任务 ID>/`，落在现有 `/opt/openhands/data` 持久卷中。`job.json` 为元数据，输入、日志及顶层输出文件可下载；scratch 会在任务结束后清理。历史页面显示最近 100 项，数据不自动删除。
- 单 worker、最多 10 个未结束任务；单任务最多 8 核/申请 8192 MB、15 分钟、128 原子。Gaussian 内存为总量，ORCA `%maxcore` 按核分配，xTB 由程序自动管理。没有 cgroup 内存硬限制，适合当前可信单机 demo。
- 仅接受 XYZ 与列举的参数，生成原生输入文件；不接收任意 shell 或软件脚本。下载只允许任务顶层普通文件，不跟随符号链接。
- 成功要求退出码为 0 且包含各软件正常终止标志；只有成功输出的能量才作为结果展示。失败或超时可看日志，停止会终止整个进程组。服务重启将遗留排队/运行任务标为失败，需要用户重新提交。
- 状态可用表示 `xtb` / `orca` / `g16` 可执行文件能在服务 PATH 找到，不代表所有方法和许可证都已通过验收。真实小分子验收记录见开发纪要。

## 本地开发

Node 24 + 已锁定的 npm 依赖。科学服务使用镜像已有的 FastAPI 0.143.0 / uvicorn 0.54.0；不用修改 OpenHands SDK。

```sh
uv run --python 3.13 --with fastapi==0.143.0 --with uvicorn==0.54.0 \
  python -m uvicorn tools.science_apps.service:app --host 127.0.0.1 --port 18002
```

## MAGUS + MACE-OFF23

MAGUS 2.2.0 的首个工作流是单组分、中性闭壳层有机分子晶体预测。输入是**一个连通分子**的 XYZ，
支持 H/C/N/O/F/P/S/Cl/Br/I。设置晶胞内分子数（1–8）、种群（4–12）、代数（1–10）、
整个晶胞的体积范围（Å³）和 small/medium/large 模型；晶胞总计不超过 128 原子。
默认四个甲烷、6 个体、3 代、180–400 Å³，其他分子的体积须相应调整。零压力、CPU float64、
固定 BFGS 晶格优化（0.05 eV/Å，最多 200 步）。15 分钟仍未结束会超时失败。

`magus_runner.py` 在隔离 Python 中生成原生 MAGUS 输入并运行。保留结构须通过分子完整性、
能量/力/应力重算一致性检查，且至少一个候选收敛，才返回成功。能量单位为整个晶胞的 eV；
`result.json` 记录每个候选的收敛状态，最低能量候选仍须查该字段。输出提供各候选 CIF/POSCAR、
`results.zip`（含原生输入、日志和轨迹）。有限搜索不能保证全局最低点，也不等同于 DFT 精度。
MAGUS 2.2 的 `add_sym` 会原地改变父代坐标并留下旧能量，因此固定为 false。

运行时挂载见部署文档。独立 uv 环境安装 MAGUS/gensym 的 CPython 3.10 扩展及 MACE，
不改原 MAGUS 环境或共享 Python 3.12 MACE 环境，也不复制模型权重。
可用性检测检查 `magus-mace`、运行时 Python 和三份本地权重；不在目录请求时下载模型。

Agent 使用镜像提供的 `em-magus` CLI，经同一个 `/api/science` 服务提交和管理任务，
因此与手动页面共用串行队列和历史。CLI 从运行时环境读取 session key，不打印密钥。
镜像启动时在不存在同名用户技能的情况下，链接自带的 `magus` 技能到
`~/.openhands/skills/magus`。新对话自动发现；已有对话需要新建对话才能加载新技能。
不需要扩展 SDK 工具协议、MCP 或重写 Agent 编排。

```sh
em-magus submit molecule.xyz --molecules-per-cell 4 --population-size 6 --generations 3 \
  --volume-min 180 --volume-max 400 --model-size medium --cores 2
em-magus status JOB_ID
em-magus cancel JOB_ID
em-magus download JOB_ID ./magus-results
```

运行前在私有环境设置 `SCIENCE_SESSION_API_KEY`，可用 `SCIENCE_APPS_DATA_DIR` 指定独立测试数据目录。服务只应绑定 loopback。若本地前端需要单独预览，请让现有静态服务增加 `--route /api/science=http://127.0.0.1:18002`，前端继续使用相同运行时 session key。标准上游 `npm run dev` 不自动启动科学服务。

```sh
uv run --python 3.13 --with fastapi==0.143.0 --with httpx --with uvicorn==0.54.0 \
  python -m unittest tools.science_apps.test_service
npx vitest run __tests__/components/features/science-apps/science-apps-page.test.tsx
```

## 后续接入软件

1. 安装到火山并通过 compose 持久挂载程序、依赖及必要许可证；先用容器运行用户身份完成原生小输入验证。
2. 在 `APPLICATIONS` 增加目录项，扩展 `JobRequest` 和 `prepare_input` 的严格输入生成、命令参数、成功标志、能量解析。调用始终使用参数数组，禁止 shell 拼接。
3. 同步 `src/api/science-apps-service.ts` 类型、路由允许项、应用说明翻译及表单字段，增加真实输入/任务生命周期测试。需要文件类型变化时专门实现验证，不直接开放任意原生输入。
4. 从 fork 的指定提交构建镜像后部署；保留现有会话、工作区及科学应用任务目录。并发、权限隔离及大型作业调度留到实际需要时设计。

第三方 Canvas Apps 的桌面/移动导航、动态页面入口被隐藏，旧 `/apps` 与 `/extensions/*` 链接重定向科学应用；MCP 安装页不提供原生 Git 账户连接，但保留标准 MCP 服务配置与 Skills/插件功能。此修改是产品界面取舍，不删除服务器已有账户或凭据。

## 2026-10-19 开发纪要

- 新 fork 保留现有 OpenHands Agent 能力，补科学应用手动工作台和第三方 Apps 入口收敛；具体需求记在根 `AGENTS.md`。
- 火山容器运行用户真实水分子单点验证：xTB GFN2-xTB、ORCA HF/def2-SVP、Gaussian HF/STO-3G 均正常结束；对应能量约 -5.06577462、-75.95751551、-74.94588512 Eh。方法不同，数值仅作为各自连通性检查，不能跨方法比较。
- 前端及相关导航/MCP/镜像路由回归 117 项通过；科学服务生命周期/校验/鉴权/下载/并行参数 6 项、部署脚本 6 项通过。类型、翻译完整性和生产构建通过。
- 本机 macOS Bash 3.2 对 `set -u` 下的空数组报错，上游 `docker-session-key-policy` 两项本机测试原本会失败；未改变该策略。在火山 Linux Bash 中执行原策略块，默认/禁用/开启三种情况通过。
