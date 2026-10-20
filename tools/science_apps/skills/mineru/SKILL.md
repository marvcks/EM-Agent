---
name: mineru
description: 使用 MinerU 将用户指定的 PDF、DOC、DOCX 转为 Markdown，供文献数据挖掘和标注；通过 EM-Agent 共用科学任务队列提交、查询、停止和下载。
---

# MinerU 文档文本化

用户要求解析 PDF/Word、文档转 Markdown、为文献挖掘准备文本时使用。
文件会上传到 **MinerU 官方云服务**，使用服务器已有凭据；不要读取、展示或复制凭据。
仅处理用户指定的文件。单份不超过 20 MB、200 页。Agent 提交的任务无平台总时长上限，使用 status 监控并自主决定何时 cancel；手动页面仍限 15 分钟。
加密、损坏或超限文档可能失败；失败不能作为成功提取。

```sh
em-mineru submit /absolute/path/paper.pdf --language en
em-mineru submit /absolute/path/report.docx --language ch
em-mineru status JOB_ID
em-mineru cancel JOB_ID
em-mineru download JOB_ID /absolute/path/new-output-directory
```

PDF/DOC/DOCX 直接提交，无需先转 PDF。默认 `--method vlm`，可选 `pipeline`。
默认识别公式与表格，可用 `--no-formula`、`--no-table` 关闭；默认中英混合识别，
英文建议 `--language en`，中文建议 `--language ch`。

同一队列串行执行，最多 10 个排队/运行任务。提交返回任务 ID 后每隔至少 5 秒查询。
只有 `status=succeeded` 才可宣告转换完成；查看日志、下载并检查标题、段落、公式、
表格及图片引用，再将 Markdown 用于后续挖掘或标注，不将解析文本自动当成标注真值。

`document.md` 是方便预览的纯 Markdown；**`results.zip` 是完整原始结果包**，
解压后在 `full.md` 所在目录保留图片等相对路径资产。不要只移动 Markdown 后声称图片完整。
`result.json` 记录来源文件与模型，`mineru-task.json` 记录上游任务 ID/状态。
停止结束本地等待/下载并标记取消；上游 API 无取消接口，云端解析可能继续且消耗配额。
服务重启后未完成任务标失败，不自动重传。新建对话才能加载此技能。
