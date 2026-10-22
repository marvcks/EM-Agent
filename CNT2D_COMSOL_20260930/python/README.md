# CNT2D 开源 Python 版

按同目录上一级的 `Main_Mei_Ver1_0.m`、`Test_Mesh_Convergence_Ver1_0.m`
和 `Comsol_surface_kcalc_Ver1_0.m` 改写的**独立科研程序**。
无需 MATLAB、COMSOL 或它们的许可证，目标为 Linux x86_64 和 macOS 的 CPU 环境。
独立命令行程序的初版数值验证见 VALIDATION.md；EM-Agent 科学服务集成与部署约定见仓库 docs/em-agent-science-apps.md。

## 1. 安装和第一次运行

建议 Python 3.12，支持 Python 3.11–3.13。当前 Gmsh wheel 不包含 Linux ARM64。
依赖固定在 `pyproject.toml`
和跨平台 `uv.lock` 中，环境独立于系统 Python / Agent Server。
已安装 [uv](https://docs.astral.sh/uv/) 后，在本文件所在目录执行：

```bash
uv sync --python 3.12 --frozen
uv run --frozen cnt2d run --config examples/default.json --output results/my-first-run
```

`--output` 必须是**不存在的新目录**，避免覆盖历史结果。
默认运行一个样本，随机种子 `20260901`，包含 10 根 CNT。
要生成多个结构：

```bash
uv run --frozen cnt2d run --config examples/default.json --output results/batch-3 --samples 3 --seed 20260901
```

三个样本的种子依次为 `20260901、20260902、20260903`。
程序串行执行。`mesh_threads` 仅控制 Gmsh，默认 1；稀疏求解器采用 SciPy/SuperLU。
无需 GPU 或显示桌面，出图使用 Matplotlib Agg。

Linux 的 Gmsh 官方 wheel 可能需要动态库。若报 `libGLU.so.1` 缺失，
在 Debian/Ubuntu 上安装 `libglu1-mesa`；若报 `libGL.so.1` 则安装 `libgl1`。
这只是缺失系统库的处理说明，本次未在火山执行安装。

## 2. 与原模型保持一致的内容

- 二维正方形 RVE，稳态、无热源固体导热：`div(k grad T) = 0`。
- 三相为 PVDF、CNT 芯体、包围芯体的有限厚度界面层，均使用标量常数热导率。
- CNT **外矩形**表示“芯体 + 界面层”；芯体长、宽各减去 `2 × surface_width`。
- 所有外矩形四角严格位于 RVE 内；SAT 检查禁止重叠、边接触和角接触。
- 左右固定温度，上下自然热绝缘；材料界面温度连续、法向热流以弱形式连续。
- 默认二阶连续温度有限元，贴合三相边界的直边三角形；也支持一阶单元。
- 外矩形面积计入填料面积分数；CNT 数量按原 MATLAB 的正数四舍五入规则计算。
  特别允许 `filler_area_fraction_target = 0`，用于纯基体解析解验证。
- 不增加 CNT 热导率各向异性、周期性边界、接触热阻、瞬态或 Y 方向热导率计算。

| 物理参数 | 默认值 |
|---|---|
| 区域边长 | 100 mm |
| CNT 外长 × 外宽 | 10 × 1 mm |
| 界面层厚度 | 0.1 mm |
| 填料目标面积分数 | 0.01（1%），默认恰为 10 根 |
| 角度范围 | −90° 到 90°，均匀分布 |
| CNT / 界面 / PVDF 热导率 | 400 / 7.642 / 0.146 W/(m·K) |
| 左 / 右温度 | 308 / 288 K |

源代码的长度单位确实是 **mm**，这里忠实保留。如果研究体系实际需要 nm，
请修改配置中的 `length_unit`，不要把文件名中的 CNT 理解成已有纳米单位。
对相似几何、常数导热率的这个稳态问题，统一缩放尺寸不改变有效热导率，
但会改变热流密度，程序按 SI 正确换算。

原代码的密度、热容仍记录在参数中；当前稳态方程没有储热项，因此它们不参与求解。

## 3. 参数文件

`examples/default.json` 可复制后修改。JSON 只需写要覆盖的参数，未写的沿用
`cnt2d/model.py` 中的默认值。未知键、非有限数、不合法几何或相同边界温度会报错。

| Python 键 | 原 MATLAB 参数 / 含义 |
|---|---|
| `box_size` | `BOX_SIZE` |
| `cnt_length`, `cnt_width` | `CNT_LENGTH`, `CNT_WIDTH`（外尺寸） |
| `surface_width` | `SURFACE_WIDTH` |
| `filler_area_fraction_target` | `FILLER_AREA_FRACTION_TARGET` |
| `angle_min`, `angle_max` | 生成结构的角度范围，单位度 |
| `max_attempts` | 每根 CNT 最多放置尝试数，默认 100000 |
| `length_unit` | `m`, `cm`, `mm`, `um`, `nm` |
| `cnt_k`, `pvdf_k`, `surface_k` | 三相热导率，W/(m·K)，必须大于 0 |
| `t_left`, `t_right` | 边界温度，K |
| `temperature_order` | 1 或 2，默认 2 |
| `bulk_size` | 基体远场目标网格尺寸，与输入几何单位相同；默认 5 |
| `interface_layers` | 界面网格目标分辨率，正整数；默认 2 |
| `mesh_threads` | Gmsh 线程数，默认 1 |
| `cnt_density`, `pvdf_density`, `surface_density` | 密度，kg/m³，仅记录 |
| `cnt_heatcapacity`, `pvdf_heatcapacity`, `surface_heatcapacity` | 比热，J/(kg·K)，仅记录 |

Gmsh 先用 OpenCASCADE 布尔分割建立共享边界，保留三相标签，再在界面边界附近加密。
界面目标边长为 `min(bulk_size, surface_width / interface_layers)`，离开界面后逐渐过渡。
`interface_layers` 是网格尺寸控制，并不强制每条截线恰好包含该数量的三角形。
**这些参数不等价于 COMSOL 的网格等级或 narrow-region 参数**，必须重新做网格比较。
薄界面、高填料率和更细网格都会增加内存与时间。

## 4. 输出内容

每个样本一个子目录 `sample_001/`，顶层 `All_Summary.csv` 在各样本后更新。

| 文件 | 内容 |
|---|---|
| `parameters.json` | 本次全部物理与网格参数 |
| `geometry.json` | 精确中心、外尺寸、弧度角、单位、随机来源 |
| `Corners.txt` | 与原 `save_rectangle_corners.m` 一致的制表符格式 |
| `result.json`, `Summary.txt` | 热导率、热流、几何面积、误差、网格规模、耗时 |
| `manifest.json` | 状态、版本、代码和锁文件哈希、几何哈希、单位、起止时间 |
| `mesh.msh` | Gmsh 网格和三相物理组；**坐标归一化，RVE 边长为 1** |
| `solution.npz` | 完整 FEM 自由度，包括二阶边中点温度；坐标单位 m |
| `fields.vtu` | 可用 ParaView 打开；坐标 m、顶点温度 K、单元平均热流 W/m² |
| `geometry.png`, `mesh.png` | 三相结构、网格 |
| `temperature.png`, `isotherms.png`, `heat_flux_x.png` | 温度、等温线、单元平均 X 热流 |
| `error.log` | 仅失败时写出详细错误；结果标记为 `FAILED` |

加 `--no-images` 可跳过 PNG，仍保存网格、完整数值场和汇总。
VTU 顶点温度是方便可视化的线性表示；完整二阶解以 NPZ 为准。
温度图片由二阶解在细分网格上求值，热流图片使用单元平均量。
程序不生成 `.mph` 文件，也不将自有网格面积命名为 `...COMSOL`。

`SOLVED` 表示线性方程成功求解并导出结果，**不代表已证明网格收敛或与实验吻合**。
失败退出码为 1；正常求解退出码为 0。若进程被强制终止，`RUNNING` manifest
应视为未完成，该目录不能当作成功结果。

## 5. 热流、单位与可信度

二维热流按单位面外厚度计算：左右边界外法向热流 `Heatflow_Left/Right` 的单位
为 W/m。308 K 左边、288 K 右边时，左侧负、右侧正。
对正方形，`Keff_X = (|Q_left| + |Q_right|) / (2 |ΔT|)`，单位 W/(m·K)。

主结果用有限元弱形式的 Dirichlet 边界反力求积分热流，减少直接求导在粗网格上的误差。
同时保留以下诊断：

- `Keff_Volume_Flux`：全域平均 X 热流换算的热导率。
- `Keff_Energy`：耗散积分换算的热导率。
- `Energy_Balance_Error`：反力热流的有符号守恒误差，通常接近求解容差。
- `Gradient_Heatflow_Left/Right`：直接积分离散温度梯度得到的边界热流。
- `Gradient_Flux_Balance_Error` 和 `Gradient_vs_Reaction_Relative_Error`：
  直接梯度热流的守恒误差及其与反力热流的差异，**数值为比例，乘 100 才是百分数**。
- `Free_Residual_Relative`：自由节点的线性方程残差。
- `Reuss_Bound` / `Voigt_Bound`：按真实相面积计算的调和／算术材料界限。

反力守恒、全域通量和能量积分之间存在离散方程恒等关系，彼此接近不能独立证明精度。
程序另外核查三相网格面积、解析解测试、材料界限，并提供网格比较。
默认算例中直接梯度边界热流仍有约 0.75% 的差异，不能把接近机器精度的反力守恒
误差解释成所有局部热流都已精确。

## 6. 网格收敛比较

```bash
uv run --frozen cnt2d converge --config examples/default.json --output results/mesh-study --no-images
```

默认三个种子 × `bulk_size = 8, 4, 2` × `interface_layers = 1, 2`，共 18 次。
每个种子只生成一次结构，所有网格复用它。

自定义范围，例如一个结构的更细检查：

```bash
uv run --frozen cnt2d converge --config examples/default.json --output results/finer-study --seeds 20260901 --bulk-sizes 2 1 --interface-layers 2 3 --tolerance-percent 0.1 --no-images
```

输出 `Mesh_Convergence_Detail.csv`、`Mesh_Convergence_Summary.csv`、`convergence.json`
及各工况完整数据。相对误差以**列表内最小 bulk_size + 最大 interface_layers**
为参考；默认容许相对误差 1%。`Within_Reference_Tolerance` 只是相对于该参考的比较，
并非真解误差保证，参考工况自身留空。统计标准差使用样本标准差（至少两个有效样本）。
若参考失败，保留失败记录，其余工况的误差也留空，不偷偷更换参考。
超过比较容差不改变求解退出码；要判断分辨率是否足够，应读取比较列。
最细网格仍可能不够细，重要研究应进一步细化和增加随机结构数量。

## 7. 导入原 MATLAB 几何进行公平对照

```bash
uv run --frozen cnt2d run --config examples/default.json --output results/matlab-geometry --corners /absolute/path/to/Ser1-Len10-Wid1-VF0.0100-Corners.txt
```

输入为原 `save_rectangle_corners.m` 导出的带表头制表符文本，格式为
`CNT_ID x1 y1 x2 y2 x3 y3 x4 y4`，每根矩形的四角沿逆时针排列。
几何单位、区域尺寸、外矩形长宽和界面厚度须由配置与原计算保持一致。
允许导入根数不同于目标面积分数推算值的结构，汇总会记录实际根数和面积偏差。

Python 使用 NumPy PCG64，原代码使用 MATLAB twister；**相同种子不表示相同结构**。
精确比较应导入角点，不应仅对齐随机种子。角点重建的浮点舍入也可能改变 Gmsh
生成的具体网格，因此相同物理几何下的结果应在网格误差范围内比较，不要求逐位相等。

## 8. 测试、实现与边界

```bash
uv run --frozen pytest -q
uv run --frozen ruff check .
```

测试覆盖纯材料线性温度、双向温差、一／二阶单元、串联与并联分层解析解、
三相面积、长度尺度不变性、随机结构与角点往返、材料界限、CLI 导出、失败参考处理
及禁止覆盖旧输出。第一次开发验证记录见 [VALIDATION.md](VALIDATION.md)。

源码组织：`model.py` 参数和几何，`mesh.py` 网格，`solver.py` 导热，
`output.py` 导出与绘图，`cli.py` 批量与网格比较。
依赖的官方资料：[Gmsh](https://gmsh.info/)、
[scikit-fem](https://scikit-fem.readthedocs.io/en/latest/)、
[SciPy 稀疏求解](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.spsolve.html)。
依赖包保留各自开源许可证；本目录没有打包或分发 MATLAB/COMSOL 组件。

**尚未与原 COMSOL 数值结果交叉验证**，因为输入文件夹没有参考数值或 MPH 模型，
当前也没有相应商业软件运行环境。当前实现不包含断点续算、自动参数反演、
三维模型、瞬态、界面接触电阻或服务端任务队列。
