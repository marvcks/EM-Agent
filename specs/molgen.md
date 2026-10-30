# ChemTSv3 Pareto molecular generation

| ID | Contract |
| --- | --- |
| MG-001 | Run the user-supplied Pareto_Mul_2 workflow with the bundled ChemTSv3 engine, RNN model and nine ChemProp property models. One merge process combines per-worker pending pools every five minutes; each search worker is single-threaded and bounded by an explicit generation budget. All processes share one `/api/science` job directory; no LLM call is involved. |
| MG-002 | Accept only bounded generation parameters: 1–7 workers, 60–7200 s per worker, a seed and total cores from workers + 1 up to 8. Reject structures, SMILES, native config files, shell fragments and unknown fields. The fixed scientist-supplied filters, reward and reference pool are not editable from the request. |
| MG-003 | Publish a result only when every worker exits 0 with a DONE marker, at least one molecule was generated and merged, and `result.json`, `molecules.csv` and `results.zip` are present and consistent. Show counts, top molecules by reward, units and the model-prediction caveat. |
| MG-004 | Mount the isolated Python 3.11 runtime and bundled application read-only, matching the candidate image's exact lock. Verify the application file manifest and model identities before each job. Discover the bundled `molgen` Agent skill without overwriting user skills; preserve existing tools, conversations and data through deployment and rollback. |

Validation covers the user-supplied migration package manifest, an isolated runtime import of both the engine and all nine property models, and a real generation run on the deployment host and inside the container. Generated properties are model predictions; finite stochastic search does not establish a global optimum or experimental performance.
