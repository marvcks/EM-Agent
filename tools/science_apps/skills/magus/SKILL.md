---
name: magus
description: Predict molecular crystal candidates with MAGUS and MACE-OFF23 on this EM-Agent server; submit, inspect, stop, and download bounded searches through the shared science queue.
---

Use `em-magus` in the terminal. It authenticates from the existing runtime environment
and uses the same serial queue and history as the manual scientific workbench.
No credentials need to be copied or printed.

The supported workflow takes **one connected, neutral, closed-shell molecule** as XYZ
and a number of copies per periodic cell. Supported elements are H, C, N, O, F, P,
S, Cl, Br, I. MACE-OFF23 is an organic molecular potential; use a different method
for metals, ionic or radical systems. A pretrained search needs no VASP and no retraining.

```sh
em-magus apps
em-magus submit molecule.xyz --molecules-per-cell 4 --population-size 6 --generations 3 --model-size medium --volume-min 180 --volume-max 400 --cores 2
em-magus status JOB_ID
em-magus cancel JOB_ID
em-magus download JOB_ID ./magus-results
```

The volume bounds are Å³ for the **whole cell**. The example bounds suit four methane
molecules; estimate or ask for bounds appropriate to a different molecule. The limits
are 128 atoms in the cell, 1–8 copies, population 4–12, 1–10 generations, 1–8 CPU
threads, requested memory up to 8 GiB, and at most 10 queued/running jobs.
Agent submissions have no platform duration limit; use `status` to monitor and
`cancel` when appropriate. The manual page retains its 15-minute limit.
Memory is a request, not an OS enforced limit. Poll an active job at sensible intervals.

Results include candidate CIF/POSCAR, `result.json` and `results.zip` with native
inputs, trajectories and logs. Energies are **eV for the entire cell**. Read each
candidate's `converged` field before recommending it; do not compare raw total energies
between cells of different composition. A completed small search does not prove the
global minimum or DFT accuracy. Report failures and timeouts as such.

MAGUS 2.2's parent symmetrization can invalidate cached energies. The integration
sets `add_sym: false` and recomputes retained energies, forces and stress before success.
Use the shared queue rather than starting a separate unbounded native search.
If this skill was installed after the current conversation started, start a new
conversation to load it automatically.
