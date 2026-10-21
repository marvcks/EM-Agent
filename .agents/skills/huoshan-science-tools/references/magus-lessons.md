# MAGUS / MACE 案例（2026-10-19）

本页记录已经发生的兼容性与科学验证问题，供相似工具排障参考。它不是所有工具的安装模板，也不要求别的工具使用 MACE 或沿用甲烷参数。继续维护 MAGUS 前先核对当前版本是否仍有这些问题。

## 已有实现与记录

- 当前入口：`tools/science_apps/magus_runner.py`、`magus-mace`、`em-magus` 和 `tools/science_apps/skills/magus/SKILL.md`。
- 环境/挂载与验收约定：[部署文档](../../../../docs/em-agent-deployment.md)、[科学应用文档](../../../../docs/em-agent-science-apps.md)。
- 若本地存在，根目录 `MAGUS-2.2.0-installation-report.txt`、`MACE-OFF23-installation-report.txt`、`MAGUS-MACE-test-report.txt`、`MAGUS-EM-Agent-deployment-report.txt` 保存详细历史；这些报告不是技能正常使用的必需依赖。

## 兼容环境与模型共享

MAGUS 源仓库当时需要注册/GitLab 访问，实际使用用户下载的官方 Linux x86_64 安装器安装 2.2.0。原发行版位于 `/opt/em-agent-tools/magus/2.2.0`，管理文件已归入 `/root/EM-Agent-Tools/magus/`，不再散落工具根目录。

MAGUS/gensym 的原生扩展为 CPython 3.10 wheel，不能安装到共享 MACE 的 Python 3.12 或 Agent Server 的 Python 3.13。实际采用：

- 独立共享 MACE 项目：`/root/EM-Agent-Tools/mace-off23/`，uv + Python 3.12。
- MAGUS 专用兼容项目：`/root/EM-Agent-Tools/magus/mace-runner/`，uv + 厂商 Python 3.10。
- 容器运行时：在 `/opt/em-agent-tools/magus/mace-runner/` 用同一锁文件与本地 wheel 重新安装，再将 `/opt/em-agent-tools/magus` 同路径只读挂载。
- 三份权重仍从 `/root/EM-Agent-Tools/mace-off23/models/` 共享，容器映射到 `/opt/em-agent-tools/mace-off23/models/`，没有复制权重。

当时验证的依赖包括 MACE 0.3.16、CPU Torch 2.5.1、ASE 3.29.0、NumPy 1.26.4。火山没有 GPU，官方示例中的 CUDA 与开发者绝对模型路径需要改为实际 CPU/本地权重设置。复用时核对当前锁文件，不因上游发布新版本直接升级已有可用环境。

## “可以算能量”不等于适合作晶体搜索

原 MAGUS 环境的探索曾遇到：

- xtb-python GFN2 周期计算的多极项不可用；GFN1 路径的应力返回零，但体积有限差分不是零。
- tblite GFN1 的应力与有限差分存在偏差；GFN2 在当时 dftd4 组合下发生段错误。
- 依赖降级只做了兼容性预览，没有执行不兼容的降级。

因此不能因为 import 成功或分子单点通过就把周期变胞优化标为可用。为真实调用模式验证应力、SCF 与模型范围；保留失败记录，不把某一种后端的成功推及另一种。

MACE-OFF23 用于中性闭壳层有机分子；当前 MAGUS 页面只开放对应的单组分分子晶体流程。不是面向金属、离子或自由基的通用替代 VASP。预训练势允许不依赖 VASP 进行这个已限定的搜索，但精度与覆盖范围仍须明确。

## 父代坐标与缓存能量不一致

MAGUS 2.2 的 `add_sym: true` 路径会对保留父代执行原地对称化，坐标变化后仍留下旧能量/力/应力。在第一次完成的测试里，一个候选的存储总能量与重算相差约 0.00706 eV；Python 3.10 与独立 Python 3.12 环境对新坐标的重算一致，问题来自结构/缓存错配。

当前适配器固定 `add_sym: false`，不修改上游源码，并在搜索后对保留候选重算能量、力和应力，核对分子完整性及收敛状态后再导出。新版本若修复该问题，应重新验收再决定是否解除规避，不盲目延续或删除它。

## 生成器参数与验收范围

早期测试只设置通用原子距离、或给定过小体积时，生成器会反复拒绝结构。最终采用分子专用完整性检查、显式整个晶胞体积与合理晶格范围。甲烷的四个分子、180–400 Å³ 示例不能直接套用到大分子或其他化合物。

真实验收是四个甲烷、20 原子、三代、种群 6，保留候选全部收敛；还验证了容器运行、Agent CLI、页面提交/停止/下载与持久化。它证明该链路可用，不证明全局最优、大分子晶体或所有模型/方法都达到科研生产标准。

页面验收发现“实际填甲烷，按钮仍写水分子”的文案错误，已通过新提交构建部署修正。以后同时检查示例的内容、名称、参数和结果单位，不只看路由能否打开。
