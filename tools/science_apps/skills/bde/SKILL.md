---
name: bde
description: Analyze homolytic bond dissociation enthalpies from SMILES or a standard name, generate radical products and a numbered molecule graph, and identify the lowest supported BDE using ALFABET or Psi4.
---

# Bond dissociation analysis

Use `em-bde` through the terminal. It uses the same bounded serial queue, logs,
stop operation and persistent downloads as the manual scientific application.
Do not bypass the queue with direct runner execution.

```sh
em-bde submit --smiles 'CCO' --mode ALFABET --cores 2
em-bde submit --name 'water' --mode Psi4 --cores 4 --memory-mb 4096
em-bde status JOB_ID
em-bde cancel JOB_ID
em-bde download JOB_ID ./bde-results
```

- Accept one connected, neutral, closed-shell, non-isotopic C/H/N/O molecule.
  Include assigned tetrahedral stereochemistry where applicable. Names resolve
  through PubChem; confirm the canonical SMILES and graph in the result.
- Atom and bond indices start at 0 in the explicit-H canonical molecule. All
  bonds are listed; only non-ring single bonds (including X–H) are supported.
  Report unsupported bonds explicitly. The minimum is over supported bonds.
- ALFABET uses official v0.1.1 TensorFlow 2 weights, an update after the 2020
  paper, trained against M06-2X/def2-TZVP. It is a surrogate estimate. Unknown
  atom/bond vocabulary fails rather than returning an unsupported prediction.
- Psi4 uses M06-2X/6-311+G(d,p), equivalent to 6-311+G**, with independent
  parent/fragment relaxation and frequencies, 298.15 K gas-phase enthalpies.
  Singlet parent and doublet radicals; imaginary modes or connectivity changes
  fail. One MMFF-selected parent conformer; no exhaustive conformer search.
  This basis and protocol do not reproduce the paper's DFT dataset.
- BDE = H(fragment 1) + H(fragment 2) − H(parent), in kcal/mol. Do not confuse
  electronic energy differences, free energies, measured BDEs or ML estimates.
- Resource limits: 8 cores, requested 8 GiB, 128 atoms with H.
  Agent submissions have no platform duration limit; monitor with `status` and
  decide when to stop with `cancel`. The manual page retains its 900-second limit.
  Start with very small molecules for Psi4. Never interpret a partial/timed-out
  `progress.json` as a completed minimum across the molecule.
- `molecule.png`, `bonds.csv`, `result.json`, `results.zip` and Psi4 structure/
  thermochemistry records are downloadable. Success requires the service's
  verified result; inspect logs for failures. Never invent missing bond values.

Reference: https://www.nature.com/articles/s41467-020-16201-z
