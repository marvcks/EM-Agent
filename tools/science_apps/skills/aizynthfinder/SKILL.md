---
name: aizynthfinder
description: 多步逆合成、合成路线预测、AiZynthFinder；输入目标分子 SMILES，用 USPTO 模型和公开 ZINC 原料库搜索路线。
---

# AiZynthFinder 逆合成路线

将目标分子的 SMILES 写入 `target.smi`（仅一行，不加名称）。仅接收一个连通分子，不含盐组分或反应箭头，含氢最多 128 原子。CPU 使用公开 USPTO ONNX 扩展/过滤模型和 ZINC 原料库；不下载模型，不接受自定义可执行脚本。

```sh
em-reaction submit aizynthfinder target.smi --iterations 100 --search-seconds 60 --max-transforms 6 --max-routes 10 --cores 2
em-reaction status JOB_ID
em-reaction cancel JOB_ID
em-reaction download JOB_ID ./route-results
```

与科学应用页面共用队列，最多 8 核、申请 8 GB、Agent 提交无平台总时长上限，使用 status 监控并自主决定何时 cancel（手动页面仍限 15 分钟，含模型加载）。申请内存不是硬隔离上限。搜索时长 1–600 秒、迭代 1–500、深度 1–10、返回 1–25 条。新输出目录须不存在同名文件。

查看 `result.json` 的 `route_count` 与 `solved_count`；`routes.txt` 包含逆合成步骤和原料，`routes.json` 保留完整树，`results.zip` 打包输入与结果。solved 表示叶节点在当前原料库中，不代表实验可行或真实可购买。未找到闭合路线也是正常搜索结果，应如实告知，不能编造步骤、产率或实验验证。
