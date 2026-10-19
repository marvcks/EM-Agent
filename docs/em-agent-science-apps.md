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

## AiZynthFinder 与 lcms2yield

反应模型使用独立的 SMILES 表单（`.smi` / `.txt`，32 KiB），不使用 XYZ。
两个入口共用原有串行队列、15 分钟上限、停止、历史与文件下载。
无效分子的化学解析在隔离 runner 中进行，在模型加载前失败并保留日志。
请求包含氢的原子总数最多 128，不接受多组分盐或反应 SMILES。

- **AiZynthFinder 4.4.1**：一个目标分子；公开 USPTO ONNX 扩展/过滤模型及
  ZINC 原料库。迭代 1–500、搜索 1–600 秒、深度 1–10、返回最多 25 条路线。
  搜索时限不包括模型加载，总任务仍受 900 秒限制。`routes.json` 保存路线树，
  `routes.txt` 保存逆合成步骤和原料；`result.json` 区分返回路线数与原料库闭合数。
  闭合仅表示原料在这个公开库中，不等于实验验证或实时可采购。零闭合路线也可能
  是正常完成的搜索，不能把任务成功解释为一定找到可执行路线。
- **lcms2yield**：每行一个分子，最多 16 个，官方 `20250721.pth` CPU 推理。
  支持 C/N/O/S/F/P/Cl/Br/B/H/I/Si，输出 `correction_factors.csv` 与 `result.json`。
  模型输出是全光谱 UV 校正因子 **CF，不是产率或百分比**。产率定量还需实验
  LC-MS/UV 测量和匹配的校准协议；本入口不接受原始仪器文件或猜测校准公式。

```sh
em-reaction submit aizynthfinder target.smi --search-seconds 60 --iterations 100 --cores 2
em-reaction submit lcms2yield products.smi --cores 2
em-reaction status JOB_ID
em-reaction cancel JOB_ID
em-reaction download JOB_ID ./reaction-results
```

独立运行时位于 `/opt/em-agent-tools/{aizynthfinder,lcms2yield}`；共享解释器在
`/opt/em-agent-tools/python`。各工具有 `pyproject.toml`、`uv.lock`、`.venv`、
固定来源的 `source` 和包含版本/模型散列的 `manifest.json`。可用性要求解释器、
程序、模型及 manifest 都存在，不在刷新目录或提交时联网下载。各 runner 限制
CPU affinity，沿用申请内存语义。服务器管理记录在 `/root/EM-Agent-Tools/<tool>`。
镜像自带 `aizynthfinder` / `lcms2yield` 用户技能，无同名技能时链接到持久化技能目录；
已有对话需新建才能加载。Agent CLI 真正调用共用 API；这不等同于已验收 LLM 的
自然语言规划行为。

反应任务的临时目录由服务创建在 `/tmp/em-science-*`（私有权限），而非长的
持久化任务路径下；PyTorch 多进程使用 Unix socket，长 TMPDIR 会触发
`AF_UNIX path too long` 并使上游加载器等待。成功、失败、停止和超时均由
Manager 的 finally 清理这个短临时目录，持久化输入/日志/结果路径保持原样。

## 化学键 BDE 解析

入口 **科学应用 → BDE**。输入单个 SMILES 或标准名（联网通过 PubChem 解析，结果需核对
canonical SMILES 和分子图）。支持中性闭壳层、无同位素 C/H/N/O 分子，含氢最多 128 原子。
先规范化 SMILES，再加显式氢和编号；遍历全部键，对非环单键（含 X–H）生成两个双重态
自由基。环键、双/三键显示“不支持”，不生成虚构数值。最低 BDE 仅在支持键中比较。

- **ALFABET**：官方 v0.1.1 TensorFlow 2 权重与原始特征编码，参考 M06-2X/def2-TZVP；
  是论文后的模型更新版，不宣称逐字复现 2020 原始权重。未知原子/键特征词汇拒绝预测。
- **Psi4**：M06-2X/6-311+G(d,p)，即用户要求的 6-311+G**；母体和自由基分别优化，频率
  提供 ZPE 和 298.15 K、1 atm 热焓修正，按 H(A·)+H(B·)−H(AB) 计算 kcal/mol。
  原子无振动自由度，使用 E+5RT/2。母体从 12 个 ETKDG/MMFF94s 构象选最低者，自由基
  从母体断键构型开始；不是全局构象穷尽。检查优化收敛、明显虚频（>20i cm⁻¹）与连接关系。
  与代理模型的基组不同，两者不能当作同一计算协议的逐键复现。

共用串行队列、8 核/8192 MB 申请、900 秒全任务时限。Psi4 遍历较大分子可能超时，建议
从水、甲烷等小分子开始；未完成不发布成功结果或全分子最低 BDE。可下载 `molecule.png`、
`bonds.csv`、`result.json`、`results.zip`，量化模式另有初始/优化 XYZ、频率和焓记录。
分子图/表/CSV 的原子、键编号均从 0 开始。`parent-initial.xyz` 与 ZIP 中的
`generated-fragments/` 提供生成坐标，`fragment-structures.json` 记录逐键映射；这些初始
坐标不标为量化优化结果。Psi4 的 `structures/*/optimized.xyz` 才是通过检查的优化结构。

Agent 新对话发现 `bde` 使用技能，CLI 与页面共用服务：

```sh
em-bde submit --smiles 'CCO' --mode ALFABET --cores 2
em-bde submit --name 'water' --mode Psi4 --cores 4 --memory-mb 4096
em-bde status JOB_ID
em-bde cancel JOB_ID
em-bde download JOB_ID ./bde-results
```

参考论文：https://www.nature.com/articles/s41467-020-16201-z 。
用户提供的正文、SI PDF 和自由基 XYZ 用于协议核对；本地 MOESM2 DOCX 内容与论文不符，
不参与计算或模型构建。权重、环境、安装器及论文附件均不进入应用镜像。
