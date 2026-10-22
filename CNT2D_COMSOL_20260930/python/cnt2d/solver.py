"""Galerkin FEM for div(k grad T)=0 on a normalized unit square."""

from dataclasses import dataclass
import warnings

import numpy as np
from scipy.sparse.linalg import MatrixRankWarning, spsolve
from skfem import (
    Basis,
    BilinearForm,
    ElementTriP1,
    ElementTriP2,
    FacetBasis,
    asm,
    condense,
)
from skfem.helpers import dot, grad

from .mesh import CORE, INTERFACE, MATRIX, build_mesh


@dataclass
class Solution:
    basis: Basis
    temperature: np.ndarray
    conductivity: np.ndarray
    cell_flux: np.ndarray  # cell averages, W/m^2, x/y components
    metrics: dict
    phases: np.ndarray | None = None


@BilinearForm
def conduction(u, v, w):
    return w.k * dot(grad(u), grad(v))


# @spec CNT2D-002 — Reactions yield signed outward flux per unit out-of-plane thickness.
def solve_conduction(mesh, conductivity, t_left, t_right, physical_size_m, order=2):
    k = np.asarray(conductivity, dtype=float)
    if k.shape != (mesh.nelements,) or not np.isfinite(k).all() or np.any(k <= 0):
        raise ValueError("one positive finite conductivity per triangle is required")
    if order not in (1, 2) or not np.isfinite([t_left, t_right, physical_size_m]).all():
        raise ValueError("invalid order, temperature or physical size")
    if physical_size_m <= 0 or t_left == t_right:
        raise ValueError("positive size and nonzero temperature difference required")
    element = ElementTriP2() if order == 2 else ElementTriP1()
    basis = Basis(mesh, element, intorder=4)
    left_facets = mesh.facets_satisfying(
        lambda x: np.abs(x[0]) < 1e-10, boundaries_only=True
    )
    right_facets = mesh.facets_satisfying(
        lambda x: np.abs(x[0] - 1) < 1e-10, boundaries_only=True
    )
    left, right = (
        basis.get_dofs(facets=left_facets).all(),
        basis.get_dofs(facets=right_facets).all(),
    )
    if not len(left) or not len(right):
        raise ValueError("mesh must span x=0 and x=1")
    matrix = asm(conduction, basis, k=k[:, None])
    # Solve excess temperature, avoiding cancellation from the Kelvin offset.
    theta = np.zeros(basis.N)
    theta[left] = t_left - t_right
    reduced, rhs, theta, free = condense(
        matrix, np.zeros(basis.N), x=theta, D=np.union1d(left, right)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", MatrixRankWarning)
        theta[free] = spsolve(reduced, rhs)
    if not np.isfinite(theta).all():
        raise RuntimeError("nonfinite temperature solution")
    residual = matrix @ theta
    relative_residual = np.linalg.norm(residual[free]) / max(
        np.linalg.norm(rhs), np.finfo(float).tiny
    )
    if relative_residual > 1e-8:
        raise RuntimeError(f"linear solve residual too large: {relative_residual:g}")
    q_left, q_right = -float(residual[left].sum()), -float(residual[right].sum())
    delta = abs(t_left - t_right)
    mean_q = (abs(q_left) + abs(q_right)) / 2
    if q_left * (t_left - t_right) >= 0 or q_right * (t_left - t_right) <= 0:
        raise RuntimeError(
            "boundary heatflow direction inconsistent with temperature gradient"
        )
    field = basis.interpolate(theta)
    flux_normalized = -k[None, :, None] * field.grad
    cell_areas = basis.dx.sum(axis=1)
    cell_flux = (
        (flux_normalized * basis.dx[None]).sum(axis=2)
        / cell_areas[None]
        / physical_size_m
    )
    avg_qx = float(np.sum(cell_flux[0] * cell_areas) / cell_areas.sum())
    gradient_flows = []
    for facets in (left_facets, right_facets):
        fb = FacetBasis(mesh, element, facets=facets, intorder=4)
        grad_theta = fb.interpolate(theta).grad
        outward = -k[fb.tind, None] * np.sum(grad_theta * fb.normals, axis=0)
        gradient_flows.append(float(np.sum(outward * fb.dx)))
    g_left, g_right = gradient_flows
    metrics = {
        "Keff_X": mean_q / delta,
        "Heatflow_Left": q_left,
        "Heatflow_Right": q_right,
        "Mean_Boundary_Heatflow": mean_q,
        "Avg_HeatFlux_X": avg_qx,
        "Delta_T": delta,
        "Keff_Volume_Flux": abs(avg_qx) * physical_size_m / delta,
        "Keff_Energy": float(theta @ (matrix @ theta)) / delta**2,
        "Energy_Balance_Error": abs(q_left + q_right) / mean_q,
        "Gradient_Heatflow_Left": g_left,
        "Gradient_Heatflow_Right": g_right,
        "Gradient_Flux_Balance_Error": abs(g_left + g_right)
        / max((abs(g_left) + abs(g_right)) / 2, np.finfo(float).tiny),
        "Gradient_vs_Reaction_Relative_Error": max(
            abs(g_left - q_left), abs(g_right - q_right)
        )
        / mean_q,
        "Free_Residual_Relative": float(relative_residual),
        "Triangles": int(mesh.nelements),
        "DOFs": int(basis.N),
        "Temperature_Min_K": float((theta + t_right).min()),
        "Temperature_Max_K": float((theta + t_right).max()),
    }
    return Solution(basis, theta + t_right, k, cell_flux, metrics)


# @spec CNT2D-003 — Check phase area, material bounds and unit-independent conductivity.
def solve_cnt(p, rectangles, mesh_data=None, msh_path=None):
    p.validate()
    mesh, phases = (
        build_mesh(p, rectangles, msh_path) if mesh_data is None else mesh_data
    )
    conductivity = np.choose(phases - 1, [p.pvdf_k, p.surface_k, p.cnt_k])
    solution = solve_conduction(
        mesh, conductivity, p.t_left, p.t_right, p.physical_size_m, p.temperature_order
    )
    solution.phases = phases
    area = solution.basis.dx.sum(axis=1)
    fractions = {
        label: float(area[phases == label].sum()) for label in (MATRIX, INTERFACE, CORE)
    }
    expected_outer = sum(r.length * r.width for r in rectangles) / p.box_size**2
    expected_core = (
        sum(
            (r.length - 2 * p.surface_width) * (r.width - 2 * p.surface_width)
            for r in rectangles
        )
        / p.box_size**2
    )
    if not np.allclose(
        [area.sum(), fractions[CORE], fractions[CORE] + fractions[INTERFACE]],
        [1, expected_core, expected_outer],
        rtol=1e-8,
        atol=1e-11,
    ):
        raise RuntimeError("meshed phase areas do not match the specified geometry")
    voigt = float(np.sum(area * conductivity) / area.sum())
    reuss = float(area.sum() / np.sum(area / conductivity))
    keff = solution.metrics["Keff_X"]
    if not reuss * (1 - 1e-7) <= keff <= voigt * (1 + 1e-7):
        raise RuntimeError(
            f"effective conductivity {keff:g} outside Reuss/Voigt bounds"
        )
    solution.metrics.update(
        {
            "Filler_Area_Analytical": expected_outer * p.box_size**2,
            "Filler_Area_Fraction_Target": p.filler_area_fraction_target,
            "Filler_Area_Fraction_Analytical": expected_outer,
            "Filler_Area_Fraction_Error": expected_outer
            - p.filler_area_fraction_target,
            "Filler_Area_Fraction_Step": p.cnt_length * p.cnt_width / p.box_size**2,
            "Filler_Area_Mesh": (fractions[CORE] + fractions[INTERFACE])
            * p.box_size**2,
            "Filler_Area_Fraction_Mesh": fractions[CORE] + fractions[INTERFACE],
            "Core_Area_Fraction_Mesh": fractions[CORE],
            "Interface_Area_Fraction_Mesh": fractions[INTERFACE],
            "Matrix_Area_Fraction_Mesh": fractions[MATRIX],
            "CNT_Number": len(rectangles),
            "Reuss_Bound": reuss,
            "Voigt_Bound": voigt,
        }
    )
    return solution
