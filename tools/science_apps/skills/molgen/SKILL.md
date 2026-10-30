---
name: molgen
description: 分子生成（ChemTSv3+Pareto）：用随附的 RNN 生成模型与 9 个性质预测模型，按密度、爆速、BDE、热分解温度等多目标搜索 CHON 含能分子。
---

# 分子生成（ChemTSv3 Pareto）

本工具用 ChemTSv3 的 MCTS + RNN 在 SMILES 空间生成分子，由 9 个 ChemProp 模型预测密度、爆速（detoD/detoP/detoQ/detoT/detoV）、BDE、生成焓、热分解温度等性质，并用固定筛选规则（C/H/O/N、硝基、芳香环、环拓扑、重原子/支链）和 Pareto 打分引导搜索。不需要提供结构或 SMILES；模型与初始参考池已随运行时安装，不联网下载、不训练。

```sh
em-molgen submit --workers 2 --seconds 600 --seed 20261030 --cores 3 --memory-mb 4096
em-molgen status JOB_ID
em-molgen cancel JOB_ID
em-molgen download JOB_ID ./molgen-results
```

- `--workers` 1–7：搜索进程数；另加 1 个进程定期合并各 worker 的 Pareto 候选池，因此总核数至少为 workers+1，最多 8 核。
- `--seconds` 60–7200：每个 worker 的生成时间预算（秒）。进度受 CPU、筛选通过率和模型预测速度影响；时间越长结果越多，但不保证找到全局最优。
- `--seed`：随机种子；worker i 使用 seed+i。
- 手动页面同样可提交，但页面任务在 15 分钟被平台终止；更长的搜索请在对话中通过本 CLI 提交（Agent 任务无平台总时长上限），由你查询状态并决定何时取消。

结果：`molecules.csv` 是合并后的 Pareto 候选池（含 `source_type=run_generated` 的本次生成分子）；`top_molecules.csv` 与 `result.json.top_molecules` 是按奖励排序的前 10 个分子；`result.json` 还记录各 worker 退出码、生成记录数、唯一分子数、最优奖励和运行时模型散列；`results.zip` 包含各 worker 的原始 CSV、日志、曲线图、检查点、配置和合并日志。

所有性质是模型预测值，不是实验测量；奖励与排序依赖固定的 Pareto 规则，不代表合成可行性、稳定性或能量性能已获验证。有限时间搜索不保证全局最优；引用结果时必须说明模型、时间预算和种子。初始参考池中的 1561 条记录用于打分参照，不计入本次生成分子。
