from dataclasses import replace
from itertools import combinations

import numpy as np
import pytest
from skfem import MeshTri

from cnt2d.model import (
    Parameters,
    Rectangle,
    generate_rectangles,
    overlaps,
    read_corners,
    save_corners,
)
from cnt2d.mesh import build_mesh
from cnt2d.solver import solve_conduction, solve_cnt


# @spec CNT2D-001 — Reproducible, strictly interior, separated three-phase geometry.
def test_geometry_roundtrip_and_constraints(tmp_path):
    p = Parameters()
    rectangles = generate_rectangles(p, seed=20260901)
    assert len(rectangles) == 10
    assert rectangles == generate_rectangles(p, seed=20260901)
    for r in rectangles:
        assert np.all(r.corners() > 0)
        assert np.all(r.corners() < p.box_size)
    assert not any(overlaps(a, b) for a, b in combinations(rectangles, 2))
    path = tmp_path / "Corners.txt"
    save_corners(rectangles, path)
    restored = read_corners(path, p)
    for a, b in zip(rectangles, restored, strict=True):
        np.testing.assert_allclose(a.corners(), b.corners(), atol=1e-12)
    touching = Rectangle((7, 5), 2, 1, 0)
    assert overlaps(Rectangle((5, 5), 2, 1, 0), touching)


@pytest.mark.parametrize(
    "changes",
    [
        {"surface_width": 0.5},
        {"cnt_k": -1},
        {"t_left": 288},
        {"box_size": float("nan")},
        {"interface_layers": 0},
    ],
)
def test_invalid_parameters(changes):
    with pytest.raises(ValueError):
        replace(Parameters(), **changes).validate()


# @spec CNT2D-002 — Stationary heat equation and signed fluxes match analytic solutions.
@pytest.mark.parametrize("order", [1, 2])
@pytest.mark.parametrize("t_left,t_right", [(308, 288), (288, 308)])
def test_homogeneous_solution(order, t_left, t_right):
    mesh = MeshTri.init_tensor(np.linspace(0, 1, 9), np.linspace(0, 1, 9))
    solution = solve_conduction(
        mesh,
        np.full(mesh.nelements, 0.146),
        t_left,
        t_right,
        physical_size_m=0.1,
        order=order,
    )
    expected = t_left + (t_right - t_left) * solution.basis.doflocs[0]
    np.testing.assert_allclose(solution.temperature, expected, atol=1e-9)
    assert solution.metrics["Keff_X"] == pytest.approx(0.146, rel=1e-10)
    assert solution.metrics["Heatflow_Left"] == pytest.approx(
        -0.146 * (t_left - t_right)
    )
    assert solution.metrics["Avg_HeatFlux_X"] == pytest.approx(
        0.146 * (t_left - t_right) / 0.1
    )
    assert solution.metrics["Energy_Balance_Error"] < 1e-10
    assert solution.metrics["Gradient_Flux_Balance_Error"] < 1e-10


@pytest.mark.parametrize("axis,expected", [(0, 2 / (1 / 0.2 + 1 / 20)), (1, 10.1)])
def test_series_and_parallel_layers(axis, expected):
    mesh = MeshTri.init_tensor(np.linspace(0, 1, 11), np.linspace(0, 1, 11))
    conductivity = np.where(mesh.p[:, mesh.t].mean(axis=1)[axis] < 0.5, 0.2, 20.0)
    solution = solve_conduction(mesh, conductivity, 308, 288, 1e-7, order=2)
    assert solution.metrics["Keff_X"] == pytest.approx(expected, rel=1e-9)
    assert solution.metrics["Keff_Volume_Flux"] == pytest.approx(expected, rel=1e-9)


# @spec CNT2D-003 — Mesh resolves physical phases and remains invariant under unit changes.
def test_three_phase_areas_and_scale_invariance():
    p = Parameters(
        box_size=10,
        cnt_length=4,
        cnt_width=1,
        surface_width=0.1,
        filler_area_fraction_target=0.04,
        bulk_size=1,
        interface_layers=2,
    )
    rectangles = [Rectangle((5, 5), 4, 1, 0.37)]
    mesh, phases = build_mesh(p, rectangles)
    a = solve_cnt(p, rectangles, mesh_data=(mesh, phases))
    b = solve_cnt(replace(p, length_unit="nm"), rectangles, mesh_data=(mesh, phases))
    assert a.metrics["Filler_Area_Fraction_Mesh"] == pytest.approx(0.04, abs=1e-11)
    assert a.metrics["Core_Area_Fraction_Mesh"] == pytest.approx(
        3.8 * 0.8 / 100, abs=1e-11
    )
    assert a.metrics["Keff_X"] == pytest.approx(b.metrics["Keff_X"], rel=1e-10)
    assert a.metrics["Reuss_Bound"] <= a.metrics["Keff_X"] <= a.metrics["Voigt_Bound"]
    assert a.metrics["Free_Residual_Relative"] < 1e-8
    assert np.isfinite(a.temperature).all()
