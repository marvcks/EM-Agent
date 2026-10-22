# CNT2D open-source conduction solver

The standalone program in `CNT2D_COMSOL_20260930/python/` replaces the supplied
MATLAB/COMSOL scripts. The fork's independent science service integrates it;
Agent Server contracts and the shared job lifecycle remain unchanged.

- **CNT2D-001 — Geometry.** Fixed-size outer CNT rectangles, finite-thickness
  inward interface, strict containment, and SAT exclusion of touching or overlap.
  Seeds are reproducible in Python; MATLAB geometry is compared by importing
  corners, not by assuming equal random-number sequences.
- **CNT2D-002 — Physics.** Solve divergence(k grad T)=0 with scalar piecewise
  constant conductivity, left/right fixed temperatures and insulated top/bottom.
  Default quadratic conforming FEM. Signed outward boundary heatflow is per unit
  thickness (W/m); effective conductivity is W/(m K). Verify homogeneous and
  series/parallel layered analytic cases, both temperature directions.
- **CNT2D-003 — Mesh.** Gmsh conforming triangles retain core/interface/matrix
  tags and refine the finite interface. Normalize coordinates for conditioning;
  convert gradients to SI. Verify phase areas, positivity, and material bounds.
- **CNT2D-004 — Evidence.** Export input, exact geometry, field data, plots and
  metrics. Record algebraic reaction flux separately from raw gradient flux;
  conservation alone does not establish mesh convergence. Reuse each geometry
  across mesh comparisons and identify the finest tested reference explicitly.
  Failed cases cannot appear as successful results. No COMSOL equivalence claim
  without reference data. Existing output directories must not be overwritten.
- **CNT2D-005 — Shared submission.** `cnt2d` accepts bounded physical parameters
  and optional tab-separated outer rectangle corners; never XYZ, scripts or
  arbitrary paths. Up to 64 CNT and 500,000 triangles; requests below 4096 MB
  allow at most 200,000 triangles. Both manual UI and `em-cnt2d` share the queue,
  cancellation, history, session key and download boundaries.
- **CNT2D-006 — Verified result.** Zero exit, completion marker, validated phase
  areas, finite positive conductivity, small solve residual and signed flux
  balance are necessary. Retain parameters, geometry, mesh and fields. The UI
  reports W/(m K). A solved case is not a convergence proof. Cross-validation
  currently covers one supplied 5%/50-CNT COMSOL example.
- **CNT2D-007 — Deployment.** CPU dependencies are isolated and locked beneath
  `/opt/em-agent-tools/cnt2d`, read-only in the container. Solver source and
  adapters ship in the complete commit image. Compare the candidate lock with
  the runtime manifest; preserve existing data and rollback mounts.
