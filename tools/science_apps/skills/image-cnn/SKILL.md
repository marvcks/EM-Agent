---
name: image-cnn
description: Classify supplied-style black/white microstructure PNG images into experimental class 0/1 with a fixed ResNet18 model and five Grad-CAM overlays. Use for image_CN_1030 models, not numerical conductivity simulation or general photographs.
---

Use the shared scientific queue, without retraining or downloading weights:

```sh
em-image-cnn submit microstructure.png --cores 2
em-image-cnn submit --example
em-image-cnn status JOB_ID
em-image-cnn cancel JOB_ID
em-image-cnn download JOB_ID ./image-cnn-results
```

Input: a single PNG ≤512 KiB, 32–5000 pixels each side, ≤20 million pixels.
White-composite transparency; grayscale → 224×224 → RGB → normalize mean/std 0.5,
as in the supplied training script. Fixed CPU checkpoint `cla_5/resnet18_opt1.pth`;
SHA-256 `fe02a72c0013edfa32b6075884b1486753fcf56dd1d9fd6cd8c94dcc74085299`.

Results: class 0/1, uncalibrated P(class 1), cutoff 0.5, five Grad-CAM PNGs
(Conv1, Layer1–4), input.png, result.json and results.zip. All heatmaps target the
positive-class logit, including class-0 predictions; relative attention is not a
causal heat-flow map. Two supplied datasets reuse image IDs with different labels; the checkpoint-to-data-version
mapping is unconfirmed. Do not interpret class 0/1 as confirmed lower/higher thermal
performance. Units and black/white phase identities are also unconfirmed. Do not invent W/(m·K), claim a
conductivity measurement, generalize to arbitrary photos, or cite historic
90.5% accuracy as independent validation of this checkpoint.

Manual page `/canvas/science-apps/image-cnn` shares queue/history/cancel/download.
Respect existing queue and resource limits. Poll the job until terminal state,
inspect logs/result integrity, report model scope and download the outputs.
