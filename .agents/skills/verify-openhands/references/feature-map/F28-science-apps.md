# F28 — EM-Agent scientific applications

The manual science workbench submits bounded jobs without LLM calls. Reaction
models accept SMILES; quantum tools and MAGUS retain their XYZ forms.

Source: `src/routes/science-apps.tsx`, `src/components/features/science-apps/`, `src/api/science-apps-service.ts`, `tools/science_apps/`.

## Sub-features

- `F28.catalog`: deployed tools appear with availability and the reaction category.
- `F28.routes`: one target SMILES submits a real bounded retrosynthesis search.
- `F28.cf`: product SMILES submits real UV correction-factor inference.
- `F28.cancel`: stopping an active job ends its process and preserves its log.
- `F28.download`: downloads contain the original input and typed model results.
- `F28.history`: reloading a job URL restores status, log and results.
- `F28.layout`: desktop and phone show usable forms without horizontal overflow.

## How to get to it (user POV)

- Sidebar 科学应用, then an application card.
- Direct `/science-apps/:appId?` (deployed base `/canvas`), with optional `?job=ID`.

## Driving it with control-openhands

Preconditions: a deployment containing the real runtimes/models. Use `attach`
with private credential files, `browser start`, then `doctor`. Always select
this run explicitly. Do not use mocked science responses for these recipes.

- **Catalog (`F28.catalog`).** `browser goto /canvas/science-apps`, `browser wait 'testid=science-app-aizynthfinder'`, `browser click 'role=button[name="反应模型"]'`. AiZynthFinder and lcms2yield cards show available; clicking a card reaches its form.
- **Retrosynthesis (`F28.routes`).** `browser goto /canvas/science-apps/aizynthfinder`, `browser click 'role=button[name="使用 SMILES 示例"]'`, `browser fill 'label=搜索时长（秒）' 10`, `browser click testid=science-submit`. Wait for `testid=science-job-result` to show completed, then inspect returned and stock-solved counts and the log. Completed with zero stock-solved routes is valid, not proof of experimental feasibility.
- **CF (`F28.cf`).** `browser goto /canvas/science-apps/lcms2yield`, `browser click 'role=button[name="使用 SMILES 示例"]'`, `browser click testid=science-submit`. Wait for completed, CF near 1.130069, and the statement that CF is not a yield percentage. No XYZ, charge or multiplicity input should appear.
- **Stop (`F28.cancel`).** Submit an AiZynthFinder search with 600 seconds / 500 iterations. While running, `browser click 'role=button[name="停止任务"]'`. Status becomes cancelled and the server process group ends; verify log retained. Do not cancel an unrelated user job.
- **Download (`F28.download`).** On a completed result, `browser click 'role=button[name="results.zip"]'`, then `browser downloads --inspect`. Check ZIP integrity and its `request.json` / `result.json`; CF has `correction_factors.csv`, routes have `routes.json` / `routes.txt`.
- **History (`F28.history`).** On the completed `?job=ID` URL, `browser reload`, wait for the completed status and previous values. Navigate back to catalog and use that task's history link to restore it.
- **Layout (`F28.layout`).** `browser viewport phone`, inspect both forms and capture a screenshot. `browser eval '({width:innerWidth,document:document.documentElement.scrollWidth})'` must show equal widths. Restore `browser viewport desktop`.

## Gotchas

- UI text depends on locale; use `browser snapshot` before choosing localized names.
- Requested memory is not a hard memory limit. Each job has at most 8 cores,
  8192 MB requested memory, 900 seconds and 128 atoms including H.
- AiZynthFinder uses public USPTO policy and a snapshot of ZINC stock, not current
  commercial inventory. lcms2yield predicts CF; experimental yield quantification
  additionally needs measurements and the matching calibration protocol.
- New conversations discover bundled tool skills. Existing conversation skill
  context does not refresh automatically; CLI verification proves the Agent
  environment can submit jobs, not that an LLM has planned a synthesis correctly.
