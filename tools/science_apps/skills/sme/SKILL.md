---
name: sme
description: Predict energetic-molecule properties (density, detonation velocity, impact sensitivity, melting point, ESOL) from SMILES with the SME RGCN models, and attribute each prediction to BRICS/Murcko/functional-group substructures.
---

# SME 分子性质预测与结构掩蔽解释

通过终端调用 `em-sme`。它提交到与“科学应用”页面相同的串行队列，日志、停止和结果下载一致。不要直接运行训练或解释源码。

```sh
em-sme submit --task DV_C --smiles 'Cc1c([N+](=O)[O-])cc([N+](=O)[O-])cc1[N+](=O)[O-]'
em-sme submit --task DV_R --smiles-file molecules.smi --fragmentation all --cores 2
em-sme status JOB_ID
em-sme cancel JOB_ID
em-sme download JOB_ID ./sme-results
```

- 输入是一个或多个分子的连通 SMILES（每行一个，最多 10 个，单分子最多 128 个重原子）；不支持盐、混合物（含 `.`）。先由 RDKit 解析并规范化。
- 任务：`Density_R`（密度）、`DV_R`（爆速）、`DV_C`（爆速分类）、`IS_R`（撞击感度）、`IS_C`（撞击感度分类）、`MP`（熔点）、`ESOL`（水溶解度）。数值按数据包原始定义输出；数据包没有给出单位表，类别 1 对应数据集中标注的正类（配对数据中 DV_C 正类对应 DV_R ≥ 8.8，IS_C 正类对应 IS_R ≥ 7.4，这是从标签推断的，不是官方阈值）。
- 每个任务使用 10 个随机种子模型的预测均值与标准差；分类任务输出 P(类别 1) 和 0.5 阈值类别。
- 解释：SME 依次屏蔽 BRICS 片段、Murcko 骨架/侧链和官能团原子，报告“完整分子预测 − 屏蔽后预测”的平均值（分类任务为概率差），并用 tanh 归一化着色。这是**模型扰动敏感性**，不是化学因果关系，也不能证明该片段在实验中决定性质。
- 无 BRICS 可切键的分子会得到整分子片段（贡献为 0），这是方法本身的定义，不是错误。
- 模型由资料包中的数据与文献超参数重新训练；资料包自带的 `.pth` 权重无法复现其 `result/` 中的报告指标，服务清单记录了重新训练的来源与测试指标。预测值仍是模型估计，未经实验验证。
- 资源：串行队列、最多 10 个未结束任务、8 核/8192 MB 申请；手动页面任务限 900 秒，Agent 提交无平台总时长上限。10 分子 × 3 种划分通常在一分钟内完成。
- 下载 `predictions.csv`（每个分子的预测）、`fragments.csv`（逐片段贡献）、`result.json`、`images/*.png`（按贡献着色的结构图）和 `results.zip`。只有带有完整模型元数据并通过服务校验的结果才算成功。
