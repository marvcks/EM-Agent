---
name: crystal-morphology
description: Predict crystal morphology classes (其他/球/针) with probabilities from five crystallization process parameters using the pretrained LLM-105/PSI classifier; single condition or CSV batch.
---

# Crystal morphology classification (晶体形貌判别)

Use `em-morphology` through the terminal. It submits to the same bounded serial
queue, logs, stop operation and persistent downloads as the manual scientific
application. Do not run the classifier or the source training code directly.

```sh
em-morphology submit --additive-percent 1.0 --antisolvent-temp-c 10 --stirring-rpm 300 --concentration-g-ml 0.06 --solvent-ratio 0.125
em-morphology submit --table conditions.csv --model CatBoost --cores 2
em-morphology status JOB_ID
em-morphology cancel JOB_ID
em-morphology download JOB_ID ./morphology-results
```

- Input is the five process parameters only, in this fixed order and unit:
  添加剂百分比 (%), 反溶剂温度(°C), 搅拌速率(rpm), 浓度(g/ml), 溶剂/反溶剂比值.
  Batch CSV columns must use exactly these names; up to 500 rows.
- This is a **table classifier**, not an image or crystal-structure model. It
  was trained on the supplied LLM-105/PSI 83-case dataset. Output classes are
  其他 (other), 球 (spherical), 针 (needle-like) with model probabilities.
- Probabilities are uncalibrated pretrained-model outputs, and the original
  holdout is small (CatBoost/LightGBM reached 14/17 on that split). Treat the
  class and probabilities as screening information, not experimental fact.
- Each row reports `in_training_range`. A row outside it is extrapolation with
  no demonstrated applicability. Do not present new-chemistry results as
  validated — the model has no applicability evidence beyond the source
  dataset's solvent/additive system.
- `--model auto` (default) picks the cached best model by the original code's
  ordering (test accuracy, F1, CV, smaller generalization gap). You may pin one
  of CatBoost/LightGBM/XGBoost/SVM/GradientBoosting/RandomForest.
- Resource limits: 8 cores, requested 8 GiB, 900 s on the manual page; Agent
  submissions have no platform duration limit. Scoring is seconds-scale.
- Download `predictions.csv` (per-row class and probabilities), `result.json`
  (full detail incl. class counts and envelope flags) and `results.zip`.
  Success requires the service's verified result; partial output is never a
  completed prediction.