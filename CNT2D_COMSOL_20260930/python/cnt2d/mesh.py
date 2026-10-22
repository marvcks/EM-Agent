"""Conforming OpenCASCADE fragments and locally refined linear triangles."""

from pathlib import Path

import gmsh
import numpy as np
from skfem import MeshTri

from .model import validate_rectangles


MATRIX, INTERFACE, CORE = 1, 2, 3


# @spec CNT2D-003 — Fragment shared phase boundaries before meshing, never rasterize CNTs.
def build_mesh(p, rectangles, msh_path: Path | None = None):
    validate_rectangles(rectangles, p)
    if gmsh.isInitialized():
        raise RuntimeError(
            "Gmsh already initialized; use this standalone solver in its own process"
        )
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", p.mesh_threads)
        gmsh.model.add("CNT2D")
        occ = gmsh.model.occ
        box = occ.addRectangle(0, 0, 0, 1, 1)
        tools = []
        for r in rectangles:
            for region in (r, r.core(p.surface_width)):
                coords = region.corners() / p.box_size
                points = [occ.addPoint(float(x), float(y), 0) for x, y in coords]
                lines = [occ.addLine(points[i], points[(i + 1) % 4]) for i in range(4)]
                tools.append((2, occ.addPlaneSurface([occ.addCurveLoop(lines)])))
        if tools:
            _, mapping = occ.fragment([(2, box)], tools)
            all_domains = {tag for dim, tag in mapping[0] if dim == 2}
            outer, core = set(), set()
            for i in range(len(rectangles)):
                outer |= {tag for dim, tag in mapping[1 + 2 * i] if dim == 2}
                core |= {tag for dim, tag in mapping[2 + 2 * i] if dim == 2}
            groups = {MATRIX: all_domains - outer, INTERFACE: outer - core, CORE: core}
        else:
            groups = {MATRIX: {box}, INTERFACE: set(), CORE: set()}
        occ.synchronize()
        for phase, tags in groups.items():
            if tags:
                gmsh.model.addPhysicalGroup(2, sorted(tags), phase)
                gmsh.model.setPhysicalName(
                    2, phase, {1: "PVDF", 2: "Interface", 3: "CNT"}[phase]
                )
        h_bulk = p.bulk_size / p.box_size
        h_fine = min(h_bulk, p.surface_width / p.interface_layers / p.box_size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", h_fine)
        gmsh.option.setNumber("Mesh.MeshSizeMax", h_bulk)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        if rectangles:
            curves = {
                tag
                for dim, tag in gmsh.model.getBoundary(
                    [(2, s) for s in sorted(groups[INTERFACE])],
                    combined=False,
                    oriented=False,
                )
                if dim == 1
            }
            distance = gmsh.model.mesh.field.add("Distance")
            gmsh.model.mesh.field.setNumbers(distance, "CurvesList", sorted(curves))
            gmsh.model.mesh.field.setNumber(
                distance, "Sampling", max(100, int(p.cnt_length / p.surface_width * 2))
            )
            threshold = gmsh.model.mesh.field.add("Threshold")
            for name, value in {
                "InField": distance,
                "SizeMin": h_fine,
                "SizeMax": h_bulk,
                "DistMin": p.surface_width / p.box_size,
                "DistMax": max(5 * p.surface_width, 2 * p.cnt_width) / p.box_size,
            }.items():
                gmsh.model.mesh.field.setNumber(threshold, name, value)
            gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
        else:
            field = gmsh.model.mesh.field.add("MathEval")
            gmsh.model.mesh.field.setString(field, "F", str(h_bulk))
            gmsh.model.mesh.field.setAsBackgroundMesh(field)
        gmsh.model.mesh.generate(2)
        if msh_path is not None:
            gmsh.write(str(msh_path))
        node_tags, coordinates, _ = gmsh.model.mesh.getNodes()
        points = np.asarray(coordinates).reshape(-1, 3)[:, :2]
        order = np.argsort(node_tags)
        sorted_tags = node_tags[order]
        triangles, labels = [], []
        for phase, surfaces in groups.items():
            for surface in sorted(surfaces):
                types, _, nodes = gmsh.model.mesh.getElements(2, surface)
                for kind, conn in zip(types, nodes, strict=True):
                    if kind != 2:
                        raise RuntimeError(
                            f"expected linear triangles, got Gmsh type {kind}"
                        )
                    indices = order[np.searchsorted(sorted_tags, conn)].reshape(-1, 3)
                    triangles.extend(indices)
                    labels.extend([phase] * len(indices))
        mesh = MeshTri(
            np.ascontiguousarray(points.T),
            np.ascontiguousarray(np.array(triangles, dtype=np.int32).T),
        )
        return mesh, np.array(labels, dtype=np.int32)
    finally:
        gmsh.finalize()
