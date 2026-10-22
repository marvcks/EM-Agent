# 首版验证记录

记录日期：2026-10-21。运行环境为本机 macOS 15.6 / ARM64、Python 3.12.12，
依赖使用 `uv.lock`。没有使用 MATLAB、COMSOL、模拟数据或预设热导率答案生成仿真结果。
原 MATLAB 文件保持不变。

## 自动检查

执行 `uv run --frozen pytest -q`：**16 项全部通过**。
执行 `uv run --frozen ruff check .`：通过。

包括以下真实代码路径：

- 固定种子结构重现、严格位于框内、互不接触、角点导出与重建。
- 非法参数拒绝。
- 均匀材料：`k = 0.146 W/(m·K)`，线性温度解析解；一／二阶温度单元，
  正向和反向温差。
- 两层材料 `k1 = 0.2`、`k2 = 20`，等厚：
  沿 X 串联时 `k_eff = 2/(1/k1 + 1/k2) = 0.396039603960…`；
  沿 Y 并联时 `k_eff = (k1 + k2)/2 = 10.1`。
- 旋转 CNT 的三相网格面积，有限厚度界面实际存在；mm / nm 结果的尺度关系。
- 真实 CLI 的网格与 NPZ / VTU 导出、旧目录保护、相同几何的网格比较。
- 用受控故障验证参考网格失败时记录失败，不拿其他网格冒充参考。

## 原默认参数的 Python 算例

```bash
uv run --frozen cnt2d run --config examples/default.json --output results/validated-default
```

结果目录：[results/validated-default/sample_001](results/validated-default/sample_001/)。
这是 Python PCG64 种子 `20260901` 对应的随机结构，**不是原 MATLAB 种子下结构的复现**。

| 指标 | 结果 |
|---|---:|
| CNT 根数 | 10 |
| 填料面积分数（网格） | 0.010000000000000042 |
| 芯体 / 界面 / 基体面积分数 | 0.00784 / 0.00216 / 0.99 |
| 三角形 / 二阶自由度 | 68,389 / 136,860 |
| 有效热导率 | **0.1529475790 W/(m·K)** |
| 左侧向外热流 | −3.0589515814 W/m |
| 右侧向外热流 | +3.0589515797 W/m |
| 全域平均 X 热流密度 | 30.5895158035 W/m² |
| 全域平均通量换算热导率 | 0.1529475790 W/(m·K) |
| 能量积分换算热导率 | 0.1529475792 W/(m·K) |
| 弱形式反力守恒相对误差 | 5.28 × 10⁻¹⁰ |
| 自由节点相对残差 | 3.30 × 10⁻¹¹ |
| 直接梯度边界热流守恒相对误差 | 0.007466（约 0.747%） |
| 直接梯度与反力边界热流最大相对差 | 0.007489（约 0.749%） |
| 温度范围 | 288–308 K |
| Reuss / Voigt 界限 | 0.1474681742 / 3.29704672 W/(m·K) |

求解、导出和五张图片总计约 3.5 秒，属于本机本次记录，不代表火山运行性能。
三相结构、温度、等温线和热流图片已目视检查。

反力守恒接近线性求解精度是离散方程的性质，不应解释成局部热流误差只有 10⁻¹⁰。
直接求梯度的边界热流也已单列，避免掩盖粗边界网格带来的差异。

## 18 组网格比较

```bash
uv run --frozen cnt2d converge --config examples/default.json --output results/validated-convergence --no-images
```

三个种子各复用一次生成的几何。远场网格尺寸 `[8, 4, 2]`，界面目标分辨率 `[1, 2]`。
**18/18 组均求解成功**。参考为本列表中的 `bulk_size=2, interface_layers=2`。

| 种子 | 参考网格热导率，W/(m·K) |
|---|---:|
| 20260901 | 0.1529080578 |
| 20260902 | 0.1542472203 |
| 20260903 | 0.1568461987 |

所有组相对各自参考的最大差异：**0.165714%**。
参考组合三结构均值：`0.1546671589 W/(m·K)`；样本标准差 `0.0020023735`。
这三个样本用于程序验证，不构成统计充分的材料性质预测。
默认 `bulk_size=5, interface_layers=2` 的第一个样本相对其上述参考差约 `0.02585%`。

数值表见 [Mesh_Convergence_Summary.csv](results/validated-convergence/Mesh_Convergence_Summary.csv)
和 [Mesh_Convergence_Detail.csv](results/validated-convergence/Mesh_Convergence_Detail.csv)。
本列表最细网格不是解析真解，不能据此宣称所有细化误差已经消失。

## 角点导入检查

把 Python 首次默认计算导出的 `Corners.txt` 通过同一个导入入口重新计算：

```bash
uv run --frozen cnt2d run --config examples/default.json --corners results/default/sample_001/Corners.txt --output results/imported --no-images
```

几何角点在浮点精度内一致，求得 `0.1529427413 W/(m·K)`，
相对首次结果差约 `0.00316%`。原因是角点重建后的浮点微差可以改变 Gmsh 具体网格，
这次检查验证了导入链路，不要求不同网格结果逐位相等。

## 交付边界

- Linux x86_64 所需 wheel 包含在锁文件中；**本次没有在 Linux／火山实际执行**。
- 没有原 COMSOL 的数值结果、MPH 模型或可用运行环境，尚未做 COMSOL 对照验证。
- 开源模型、边界条件和材料参数按所给源码移植；网格生成、反力热流求值方法和
  随机数序列与原工具链有所不同，已在 README 说明。
- 没有修改 EM-Agent API、前端、服务端任务队列或线上容器。
- 本地 `results/`、虚拟环境和缓存已被本目录 `.gitignore` 排除，不进入源码提交。

每个算例的 `manifest.json` 保存实际依赖版本、代码哈希、锁文件哈希和完整输入，
用于追踪本次运行。结果可按上述命令在新目录重新生成。
