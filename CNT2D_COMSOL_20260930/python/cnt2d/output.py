"""Portable result files and headless scientific figures."""

import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import matplotlib.tri as mtri
import meshio
import numpy as np


def write_json(path, value):
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    temporary.replace(path)


def write_table(path, rows, delimiter=","):
    if not rows:
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    temporary = Path(str(path) + ".tmp")
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def provenance():
    source = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(source.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    lock = source.parent / "uv.lock"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {
            name: version(name)
            for name in (
                "cnt2d-open",
                "gmsh",
                "scikit-fem",
                "scipy",
                "numpy",
                "matplotlib",
                "meshio",
            )
        },
        "source_sha256": digest.hexdigest(),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()
        if lock.exists()
        else None,
    }


# @spec CNT2D-004 — Preserve P2 DOFs and SI field units independently of plotting formats.
def export_fields(directory, solution, p):
    mesh = solution.basis.mesh
    coordinates_m = mesh.p * p.physical_size_m
    np.savez_compressed(
        directory / "solution.npz",
        coordinates_m=coordinates_m,
        triangles=mesh.t,
        phases=solution.phases,
        dof_coordinates_m=solution.basis.doflocs * p.physical_size_m,
        element_dofs=solution.basis.element_dofs,
        temperature_K=solution.temperature,
        cell_flux_W_m2=solution.cell_flux,
        conductivity_W_mK=solution.conductivity,
    )
    # VTU uses straight triangle geometry, temperatures at vertices and cell-average flux.
    meshio.write_points_cells(
        directory / "fields.vtu",
        np.column_stack([coordinates_m.T, np.zeros(mesh.nvertices)]),
        [("triangle", mesh.t.T)],
        point_data={
            "temperature_K": solution.temperature[solution.basis.nodal_dofs[0]]
        },
        cell_data={
            "phase": [solution.phases],
            "conductivity_W_mK": [solution.conductivity],
            "heat_flux_W_m2": [
                np.column_stack([solution.cell_flux.T, np.zeros(mesh.nelements)])
            ],
        },
    )


def plot_results(directory, solution, rectangles, p):
    plt.rcParams.update({"font.size": 10, "figure.dpi": 140})

    def finish(fig, ax, name):
        ax.set(
            xlabel=f"X ({p.length_unit})", ylabel=f"Y ({p.length_unit})", aspect="equal"
        )
        fig.tight_layout()
        fig.savefig(directory / name)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.set(
        xlim=(0, p.box_size),
        ylim=(0, p.box_size),
        title="CNT / interface / PVDF geometry",
    )
    ax.set_facecolor("#e7edf3")
    for r in rectangles:
        ax.add_patch(
            Polygon(r.corners(), facecolor="#f8bf64", edgecolor="#91622b", lw=0.5)
        )
        ax.add_patch(
            Polygon(r.core(p.surface_width).corners(), facecolor="#335e7e", lw=0)
        )
    finish(fig, ax, "geometry.png")

    # Evaluate quadratic temperatures on a subdivided mesh for accurate contours.
    refined, values = solution.basis.refinterp(solution.temperature, nrefs=1)
    tri = mtri.Triangulation(*(refined.p * p.box_size), triangles=refined.t.T)
    fig, ax = plt.subplots(figsize=(6, 5))
    image = ax.tripcolor(tri, values, shading="gouraud", cmap="inferno")
    fig.colorbar(image, ax=ax, label="Temperature (K)")
    ax.set_title("Steady temperature")
    finish(fig, ax, "temperature.png")

    fig, ax = plt.subplots(figsize=(6, 5))
    contours = ax.tricontour(tri, values, levels=20, cmap="plasma", linewidths=0.7)
    fig.colorbar(contours, ax=ax, label="Temperature (K)")
    ax.set_title("Isotherms")
    finish(fig, ax, "isotherms.png")

    mesh = solution.basis.mesh
    tri = mtri.Triangulation(*(mesh.p * p.box_size), triangles=mesh.t.T)
    fig, ax = plt.subplots(figsize=(6, 5))
    image = ax.tripcolor(
        tri, facecolors=solution.cell_flux[0], shading="flat", cmap="coolwarm"
    )
    fig.colorbar(image, ax=ax, label="X heat flux (W/m²)")
    ax.set_title("Cell-average X heat flux")
    finish(fig, ax, "heat_flux_x.png")

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.triplot(tri, color="#335e7e", lw=0.15)
    ax.set_title(f"Conforming mesh: {mesh.nelements:,} triangles")
    finish(fig, ax, "mesh.png")
