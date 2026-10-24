---
name: editretro
description: EditRetro 单步逆合成预测；给定产物 SMILES，使用已验证的 CPU 模型生成排序后的候选反应物。
---

# EditRetro 单步逆合成

将目标产物写入 `product.smi`，仅一行 SMILES，不加名称。接受一个连通分子，含氢最多 128 原子；不接收盐、多分子输入或反应箭头。使用预置 2D 权重在 CPU 上预测，无需下载、训练或调用 LLM 推理。

```sh
em-reaction submit editretro product.smi --top-k 20 --augmentations 20 --cores 4 --memory-mb 4096
em-reaction status JOB_ID
em-reaction cancel JOB_ID
em-reaction download JOB_ID ./editretro-results
```

返回候选数 `--top-k` 和输入增强次数 `--augmentations` 均为 1–20，可能返回少于请求数量的有效候选。解码使用 10 次迭代、5×4 编辑 beam 和固定 seed 1。增强次数影响多样性、排序和耗时。

与手动页面共用科学队列，最多 8 核、申请 8 GB、10 项未结束任务。Agent 提交无平台总时长上限，通过 status 监控并自主决定何时取消；手动页面限 15 分钟。申请内存不是操作系统硬隔离。

`result.json` 的 `candidates` 包含 rank、反应物 SMILES 和分组 reactants，`.` 分隔同一候选中的不同反应物。`candidates.csv`、`ranked_preds.txt` 和 `generation.txt` 可追溯排序及原始编辑输出；`results.zip` 包含输入和结果。

候选是模型的单步预测，排序不代表校准后的概率或实验可行性；不包含多步路线、原料库闭合或产率。CPU 文档示例已通过严格权重加载，前两名与随附示例一致，但前 20 名未完整复现，不能声称与文档所有候选或论文指标一致。只引用本次任务实际输出。
