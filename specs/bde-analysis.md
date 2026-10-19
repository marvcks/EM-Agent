# Bond dissociation analysis

- **BDE-001 — Shared bounded execution.** Manual UI and `em-bde` use the same
  `/api/science` queue, cancellation, logs and downloads. No LLM in manual mode.
- **BDE-002 — Chemical scope and indexing.** One connected neutral closed-shell
  non-isotopic CHNO molecule, up to 128 atoms including H. Input is SMILES or a
  PubChem-resolved standard name. Canonicalize before explicit-H indexing.
  Enumerate every bond; only non-ring single bonds yield two doublet radicals.
  Unsupported bonds have no numeric BDE. Minimum considers supported bonds only.
- **BDE-003 — Scientific provenance.** Official ALFABET v0.1.1 TF2 weights with
  verified hashes and original featurization. Unknown vocabulary fails. Psi4
  M06-2X/6-311+G(d,p) independently optimizes parent/fragments and computes
  298.15 K enthalpies including ZPE/thermal corrections. Atoms use E + 5RT/2.
  Nonconvergence, imaginary frequencies above 20i cm−1 or changed connectivity
  fail. Model and quantum basis differences and conformer limitations are visible.
- **BDE-004 — Reviewable output.** Numbered explicit-H graph, per-bond table,
  radical SMILES, minimum and kcal/mol units; downloadable PNG/CSV/JSON/ZIP and
  quantum geometries/logs. Partial jobs never publish a completed minimum.
