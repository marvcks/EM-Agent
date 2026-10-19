---
name: lcms2yield
description: LC-MS/UV 产率定量辅助、UV 校正因子 CF 预测；输入产品 SMILES，用 XtalPi 官方 lcms2yield 权重推理。
---

# lcms2yield UV 校正因子

此项目的公开模型预测全光谱 UV 校正因子 CF，**不是仅根据反应式预测产率的模型**。CF 不是产率或百分比。产率定量还需用户提供实验 LC-MS/UV 测量和匹配的校准协议；没有这些信息时只报告 CF，不能把 CF 乘 100 当作产率，也不要猜测校准公式。

输入文件 `products.smi` 每行一个连通分子 SMILES，不加名称，最多 16 个分子、含氢合计最多 128 原子。不支持盐混合物、反应箭头或原始仪器文件。支持元素 C/N/O/S/F/P/Cl/Br/B/H/I/Si。

```sh
em-reaction submit lcms2yield products.smi --cores 2
em-reaction status JOB_ID
em-reaction cancel JOB_ID
em-reaction download JOB_ID ./cf-results
```

使用官方 `20250721.pth`，CPU、隔离 Python。与手动页面共用串行队列，最多 8 核、申请 8 GB、15 分钟；申请内存不是硬隔离上限。查看 `result.json`、`correction_factors.csv` 或 `results.zip`，按输入 SMILES 一一对应报告 CF，并保留模型来源和适用范围。无效或不支持分子会失败，查看日志后更正，不编造结果。
