# Crystal morphology classification (晶体形貌判别)

- **CM-001 — Shared bounded execution.** The manual workbench and
  `em-morphology` use the same `/api/science` queue, cancellation, logs and
  downloads. No LLM in manual mode.
- **CM-002 — Fixed parameter contract.** Input is exactly the five process
  parameters 添加剂百分比 (%), 反溶剂温度 (°C), 搅拌速率 (rpm), 浓度 (g/ml),
  溶剂/反溶剂比值 — one condition or a CSV batch (exact five-column header, up
  to 500 finite in-range rows). No XYZ, SMILES, charge or basis. Invalid rows
  fail before any model loads.
- **CM-003 — Verified pretrained provenance.** The service loads only the
  supplied `model_results_cache.pkl` after an SHA-256 manifest check, keeps the
  source class order 其他/球/针, and runs the original model selection
  (test accuracy, F1, CV, smaller generalization gap) for `auto`. Threads are
  capped at the requested cores in the runner and in the model objects.
- **CM-004 — Reviewable output.** Per-row classes with the three uncalibrated
  probabilities, class counts and an `in_training_range` flag; downloadable
  CSV/JSON/ZIP. Rows outside the training envelope are flagged as extrapolation.
  Only a fully verified result is published as success.
- **CM-005 — Deployment isolation.** The runtime lives at
  `/opt/em-agent-tools/crystal-morphology` (uv + frozen Python 3.11 lock),
  mounted read-only together with shared `/opt/em-agent-tools/python`; the
  model cache never enters Git or the image. `morphology-classify` selects the
  isolated interpreter; the image label `io.em-agent.crystal-morphology=1`
  gates the deployer checks and mounts.