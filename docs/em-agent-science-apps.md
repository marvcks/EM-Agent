# EM-Agent 科学应用

## EditRetro 单步逆合成

入口：**科学应用 → 反应模型 → EditRetro**（`/canvas/science-apps/editretro`）。输入一个
连通产物的 SMILES（含氢最多 128 原子），可粘贴或上传 `.smi` / `.txt`；示例来自
用户提供的“输入输出示例及Github地址.docx”。返回候选数与输入增强次数均为 1–20。
默认 4 核、4096 MB、20 次增强、最多 20 个候选。固定使用 2D 模型、10 次编辑迭代、
5×4 编辑 beam、seed 1；允许返回少于请求数量的有效候选。

使用用户的 `checkpoint_best.pt`，SHA-256 为
`3a537dc6a8992dd61c02993485d8f89c83a7169e63ccb956dab88b949327daf8`，
与上游 `8e5848e899b4e8ec6be970b9be04881042ed7b55` 严格加载匹配（260 项参数、
词表 3136 项、无缺失/额外参数，`use_3d_features=false`）。CPU 适配将 4 处设备传输改成
`.to(device)`；隔离的 Torch 1.12 CPU 库清除 GNU_STACK 可执行标记以兼容容器 glibc，
修改前脱离 uv 共享缓存的硬链接，不修改模型张量或库指令。

文档分子在宿主机 8 核下约 16 秒、峰值内存约 1.62 GiB；容器实际用户、只读挂载、
4 核运行约 27 秒，返回 20 个有效候选。前两名与文档一致，前 20 个候选有 5 个相同，
未完整复现文档排序。这是示例兼容性验收，不是论文准确率复现。

结果显示排序与反应物 SMILES，`.` 分隔同一候选中的不同反应物。可下载 `result.json`、
`candidates.csv`、`ranked_preds.txt`、原始 `generation.txt` 和 `results.zip`。
候选为单步模型预测；排序不代表校准概率或实验可行性，不评估多步路线或原料库可得性。
运行前校验权重、源码、词表、分词文件和 CPU 库散列，不触发联网下载或训练。

Agent 新对话加载 `editretro` 使用技能，经同一 `/api/science` 队列提交：

```sh
em-reaction submit editretro product.smi --top-k 20 --augmentations 20 --cores 4 --memory-mb 4096
em-reaction status JOB_ID
em-reaction cancel JOB_ID
em-reaction download JOB_ID ./editretro-results
```

沿用串行队列、最多 10 项未结束任务、8 核/8192 MB 申请、停止及历史下载。
手动任务限 900 秒，Agent 提交由 Agent 监控和决定取消。内存申请不是操作系统硬隔离。

## CNT 二维导热

入口：**科学应用 → 传热仿真 → CNT 二维导热**（`/canvas/science-apps/cnt2d`）。
填写二维正方形RVE、CNT外尺寸、实体界面厚度、填料面积分数、取向、三相标量
热导率、左右温度和网格参数；默认1%/10根。可选上传MATLAB制表符 `Corners.txt`，
坐标使用所选m/cm/mm/um/nm单位，不使用XYZ。Gmsh/scikit-fem/SciPy二阶FEM
求解稳态导热，左右恒温、上下绝热，输出X方向有效热导率。

最多64根、50万三角形；面积分数0–0.1，基体网格尺寸为RVE边长1–25%，
界面厚度/分辨率不小于边长0.025%，分辨率1–3；申请内存低于4096MB时最多20万三角形。
沿用串行队列、8核/8192MB申请、手动15分钟和Agent自主监控/取消规则。
成功需完成标记和科学校验，不将热导率放入能量字段。
`results.zip`包含实际参数、角点、PNG、MSH、VTU、完整P2解NPZ和诊断JSON/CSV。
反力守恒小不代表网格收敛；已对照一个5%/50根CNT的COMSOL算例，其他工况仍需检查。

新对话加载 `cnt2d` 技能，通过同一科学服务执行：

```sh
em-cnt2d submit --seed 20260901 --cores 2 --memory-mb 4096
em-cnt2d submit --parameters parameters.json --corners Corners.txt
em-cnt2d status JOB_ID
em-cnt2d cancel JOB_ID
em-cnt2d download JOB_ID ./cnt-results
```

独立CLI源码、数值测试和参数说明在 `CNT2D_COMSOL_20260930/python/`。
服务适配器开放单结构稳态计算，不开放独立CLI的多样本网格扫描任务。

入口：侧栏 **科学应用** → xTB / ORCA / Gaussian / MAGUS。用户上传或粘贴标准 XYZ，配置参数，提交后查看状态、日志并下载输入与输出。手动页面与 Agent 对话独立，不产生模型调用。

## Agent 任务时长与对话附件

- Agent 使用 `em-bde`、`em-magus`、`em-reaction`、`em-mineru` 提交时，CLI 发送 `X-EM-Agent-Source: agent`。服务将 `source` 持久化为任务元数据，Agent 任务不执行平台总时长超时，由 Agent 查询状态并决定取消；原有队列、资源、日志、进程组停止和重启失败规则继续生效。
- 手动科学应用页面不发送该标记，仍执行 900 秒超时；未记录来源的旧任务同样按手动任务处理。来源标记沿用已有 session key 鉴权，是可信单机上的执行策略选择。
- 对话附件单文件最多 50 MiB，一条消息所有附件（含图片）合计最多 100 MiB；选择、拖放及发送校验共用这两个上限。MinerU 科学应用独立的 20 MiB 文档校验不随对话附件上限改变。

## 运行与数据

- 自定义镜像会启动 `tools/science_apps/service.py`（FastAPI + uvicorn），容器内 `127.0.0.1:18002`，同源代理 `/api/science`。
- 服务使用既有运行时 `X-Session-API-Key`。没有密钥会拒绝启动，目录/任务/下载均校验密钥。前端始终访问当前页面所在服务器，与切换到其他 Agent 后端无关。
- 状态目录：`~/.openhands/science-apps/<任务 ID>/`，落在现有 `/opt/openhands/data` 持久卷中。`job.json` 为元数据，输入、日志及顶层输出文件可下载；scratch 会在任务结束后清理。历史页面显示最近 100 项，数据不自动删除。
- 单 worker、最多 10 个未结束任务；单任务最多 8 核/申请 8192 MB、128 原子；手动任务限 15 分钟，Agent 提交无平台总时长上限。Gaussian 内存为总量，ORCA `%maxcore` 按核分配，xTB 由程序自动管理。没有 cgroup 内存硬限制，适合当前可信单机 demo。
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
固定 BFGS 晶格优化（0.05 eV/Å，最多 200 步）。手动页面提交后 15 分钟仍未结束会超时失败，Agent CLI 提交无此时长限制。

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

## 晶体形貌判别（LLM-105/PSI 预训练分类）

入口 **科学应用 → 晶体结构预测 → 晶体形貌判别**。输入是五项结晶工艺参数：
添加剂百分比（%）、反溶剂温度（°C）、搅拌速率（rpm）、浓度（g/ml）、
溶剂/反溶剂比值；可提交单条条件，或上传表头恰为上述五列的 CSV（最多 500 行，
每行数值必须有限且在输入范围内）。输出类别为 其他／球／针 及三类的模型概率。
这是**表格分类模型，不是图像识别或晶体结构预测**。

只加载随附的 `model_results_cache.pkl` 预训练缓存：服务启动/可用性只检查运行时与
缓存存在，任务运行时校验 SHA-256 与类别/特征契约后推理，不触发重训、不生成模拟数据。
`--model auto`（默认）按原代码排序（测试准确率、F1、CV、泛化差距更小）选缓存中的
最佳模型，也可固定 CatBoost/LightGBM/XGBoost/SVM/GradientBoosting/RandomForest。
SVM 使用缓存中的 RobustScaler；树模型使用原始五维数值。线程不超过申请核数
（runner 内限制 affinity 并改写模型的 `n_jobs`）。

概率是未经校准的预训练模型输出；训练集只有所附 LLM-105/PSI 83 条案例。
每行结果带 `in_training_range` 标记，范围之外的行是外推，没有已证明的适用性；
页面结果表逐行显示“范围内／外推”，批量输入时可定位到具体条件。
不得将新体系结果描述为已验证。共用串行队列、8 核/8192 MB 申请、手动页面 900 秒
（Agent 提交无平台总时长上限）。成功要求退出码 0、完成标记且整份结果通过校验。
下载 `predictions.csv`（逐行类别与概率）、`result.json`（含类别计数与范围标记）
与 `results.zip`。

Agent 新对话加载 `crystal-morphology` 使用技能，CLI 与页面共用 `/api/science`：

```sh
em-morphology submit --additive-percent 1.0 --antisolvent-temp-c 10 --stirring-rpm 300 \
  --concentration-g-ml 0.06 --solvent-ratio 0.125
em-morphology submit --table conditions.csv --model CatBoost --cores 2
em-morphology status JOB_ID
em-morphology cancel JOB_ID
em-morphology download JOB_ID ./morphology-results
```

独立运行时位于 `/opt/em-agent-tools/crystal-morphology`（uv + Python 3.11，
锁定 numpy/scikit-learn/xgboost/lightgbm/catboost）；共享解释器在
`/opt/em-agent-tools/python`。`morphology-classify` 选择隔离解释器运行
`morphology_runner.py`。模型缓存、安装记录与验收在 `/root/EM-Agent-Tools/crystal-morphology`。
原代码、权重与案例未修改；训练分支默认的无限占核已被禁用，禁止在服务内触发
完整贝叶斯调参或重训。

## 2026-10-19 开发纪要

- 新 fork 保留现有 OpenHands Agent 能力，补科学应用手动工作台和第三方 Apps 入口收敛；具体需求记在根 `AGENTS.md`。
- 火山容器运行用户真实水分子单点验证：xTB GFN2-xTB、ORCA HF/def2-SVP、Gaussian HF/STO-3G 均正常结束；对应能量约 -5.06577462、-75.95751551、-74.94588512 Eh。方法不同，数值仅作为各自连通性检查，不能跨方法比较。
- 前端及相关导航/MCP/镜像路由回归 117 项通过；科学服务生命周期/校验/鉴权/下载/并行参数 6 项、部署脚本 6 项通过。类型、翻译完整性和生产构建通过。
- 本机 macOS Bash 3.2 对 `set -u` 下的空数组报错，上游 `docker-session-key-policy` 两项本机测试原本会失败；未改变该策略。在火山 Linux Bash 中执行原策略块，默认/禁用/开启三种情况通过。

## AiZynthFinder 与 lcms2yield

反应模型使用独立的 SMILES 表单（`.smi` / `.txt`，32 KiB），不使用 XYZ。
两个入口共用原有串行队列、停止、历史与文件下载；手动任务限 15 分钟，Agent 提交无平台总时长上限。
无效分子的化学解析在隔离 runner 中进行，在模型加载前失败并保留日志。
请求包含氢的原子总数最多 128，不接受多组分盐或反应 SMILES。

- **AiZynthFinder 4.4.1**：一个目标分子；公开 USPTO ONNX 扩展/过滤模型及
  ZINC 原料库。迭代 1–500、搜索 1–600 秒、深度 1–10、返回最多 25 条路线。
  搜索时限不包括模型加载，手动页面总任务受 900 秒限制；Agent 提交无平台总时长上限。`routes.json` 保存路线树，
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

共用串行队列、8 核/8192 MB 申请；手动页面限 900 秒，Agent 提交无平台总时长上限。手动页面用 Psi4 遍历较大分子可能超时，建议
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

## MinerU：数据挖掘与标注 / 文档文本化

入口 **科学应用 → 数据挖掘与标注 → MinerU**，或 `/canvas/science-apps/mineru`。
上传 PDF、DOC 或 DOCX，选择 `vlm`（默认）/`pipeline`、语言以及公式/表格识别，
提交后使用同一任务队列、日志、停止、历史及下载功能。手动页面不调用 Agent/LLM。

此入口调用 [MinerU 官方云 API](https://mineru.net/apiManage/docs)，文件会上传到第三方服务。
本演示单文件限 **20 MiB、200 页**，手动页面任务限 900 秒，Agent 提交无平台总时长上限；页数、加密与解析支持情况由上游检查。
队列仍串行、最多 10 个活动任务。停止结束本地等待/下载；上游没有取消 API，
云端解析可能继续消耗配额。服务重启不自动重传。失败不发布成功结果。

服务器凭据放在持久化 `~/.openhands/mineru/api-token`（0600，运行用户所有），
亦可由 `MINERU_TOKEN_FILE` 指定，或从既有 `MINERU_API_TOKEN` / `MINERU_TOKEN` /
`mineru_key_api` 环境读取。凭据与临时签名 URL 不进入任务、日志、镜像或 Git。
适配器只用 Python 标准库，不安装大模型，不升级 Agent Server 依赖。
可用性只表明程序与凭据存在；凭据过期/配额/网络失败会在任务日志给出错误码。

下载 `document.md` 获取纯文本副本；**完整结果为 `results.zip`**，包含原始 Markdown、
图片与 JSON。解压后保留 `full.md` 周围的相对路径。`result.json` 保存来源文件和解析模型，
`mineru-task.json` 保存上游任务 ID/状态；上传原件也保留在任务目录。成功须满足正常退出、
完成标记、有效 ZIP、唯一非空 `full.md`，解压有路径与总大小限制。

Agent 新对话加载 `mineru` 使用技能，CLI 与手动页面共用 `/api/science`：

```sh
em-mineru submit /absolute/path/paper.pdf --language en
em-mineru submit /absolute/path/report.docx --language ch
em-mineru status JOB_ID
em-mineru cancel JOB_ID
em-mineru download JOB_ID ./mineru-results
```

解析文本须核对原文后用于数据挖掘/标注；此步骤不自动生成科研真值标签。
