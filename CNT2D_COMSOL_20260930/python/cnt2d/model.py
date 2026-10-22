"""Input validation, original rectangle rules, and MATLAB corner interchange."""

from dataclasses import asdict, dataclass, fields
from itertools import combinations
import json
import math
from pathlib import Path

import numpy as np


UNIT_TO_M = {"m": 1.0, "cm": 1e-2, "mm": 1e-3, "um": 1e-6, "nm": 1e-9}


@dataclass(frozen=True)
class Parameters:
    box_size: float = 100.0
    cnt_length: float = 10.0
    cnt_width: float = 1.0
    surface_width: float = 0.1
    filler_area_fraction_target: float = 0.01
    angle_min: float = -90.0
    angle_max: float = 90.0
    max_attempts: int = 100000
    length_unit: str = "mm"
    cnt_k: float = 400.0
    pvdf_k: float = 0.146
    surface_k: float = 7.642
    cnt_density: float = 2267.0
    pvdf_density: float = 1780.0
    surface_density: float = 2267.0
    cnt_heatcapacity: float = 500.0
    pvdf_heatcapacity: float = 1170.0
    surface_heatcapacity: float = 500.0
    t_left: float = 308.0
    t_right: float = 288.0
    bulk_size: float = 5.0
    interface_layers: int = 2
    temperature_order: int = 2
    mesh_threads: int = 1

    @property
    def num_cnt(self):
        # MATLAB round for positive values (Python round uses ties-to-even).
        if self.filler_area_fraction_target == 0:
            return 0
        n = (
            self.filler_area_fraction_target
            * self.box_size**2
            / (self.cnt_length * self.cnt_width)
        )
        return max(1, math.floor(n + 0.5))

    @property
    def physical_size_m(self):
        return self.box_size * UNIT_TO_M[self.length_unit]

    def validate(self):
        for f in fields(self):
            if f.name == "length_unit":
                continue
            value = getattr(self, f.name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{f.name} must be a finite number")
        if not isinstance(self.length_unit, str) or self.length_unit not in UNIT_TO_M:
            raise ValueError(f"length_unit must be one of {tuple(UNIT_TO_M)}")
        for name in (
            "box_size",
            "cnt_length",
            "cnt_width",
            "surface_width",
            "bulk_size",
            "cnt_k",
            "pvdf_k",
            "surface_k",
            "cnt_density",
            "pvdf_density",
            "surface_density",
            "cnt_heatcapacity",
            "pvdf_heatcapacity",
            "surface_heatcapacity",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if min(self.cnt_length, self.cnt_width) <= 2 * self.surface_width:
            raise ValueError("CNT length and width must exceed twice surface_width")
        if self.cnt_length > self.box_size or self.cnt_width > self.box_size:
            raise ValueError("CNT dimensions must not exceed box_size")
        if not 0 <= self.filler_area_fraction_target < 1:
            raise ValueError("filler_area_fraction_target must lie in [0, 1)")
        if not -90 <= self.angle_min <= self.angle_max <= 90:
            raise ValueError("require -90 <= angle_min <= angle_max <= 90 (degrees)")
        if min(self.t_left, self.t_right) <= 0 or self.t_left == self.t_right:
            raise ValueError("temperatures must be distinct, positive Kelvin values")
        for name in ("max_attempts", "interface_layers", "mesh_threads"):
            v = getattr(self, name)
            if not isinstance(v, int) or v < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.temperature_order not in (1, 2):
            raise ValueError("temperature_order must be 1 or 2")
        return self

    @classmethod
    def load(cls, path: Path | None):
        data = {} if path is None else json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("parameter JSON must be an object")
        unknown = data.keys() - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown parameter(s): {sorted(unknown)}")
        return cls(**data).validate()

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Rectangle:
    center: tuple[float, float]
    length: float
    width: float
    angle: float  # radians, same convention as rect_corners.m

    def corners(self):
        c, s = math.cos(self.angle), math.sin(self.angle)
        local = np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]])
        local *= [self.length / 2, self.width / 2]
        return local @ np.array([[c, s], [-s, c]]) + self.center

    def core(self, thickness):
        return Rectangle(
            self.center,
            self.length - 2 * thickness,
            self.width - 2 * thickness,
            self.angle,
        )


# @spec CNT2D-001 — SAT rejects both overlap and contact, matching the MATLAB code.
def overlaps(a: Rectangle, b: Rectangle):
    ac, bc = a.corners(), b.corners()
    tolerance = 1e-12 * max(a.length, a.width, b.length, b.width, 1.0)
    for corners in (ac, bc):
        for edge in (corners[1] - corners[0], corners[3] - corners[0]):
            axis = np.array([-edge[1], edge[0]]) / np.linalg.norm(edge)
            pa, pb = ac @ axis, bc @ axis
            if pa.max() < pb.min() - tolerance or pb.max() < pa.min() - tolerance:
                return False
    return True


def validate_rectangles(rectangles, p):
    p.validate()
    tol = max(1e-12, 1e-9 * p.box_size)
    for i, r in enumerate(rectangles, 1):
        coords = r.corners()
        if (
            not np.isfinite(coords).all()
            or not np.all(coords > tol)
            or not np.all(coords < p.box_size - tol)
        ):
            raise ValueError(f"CNT {i} must be strictly inside the box")
        if not np.allclose(
            [r.length, r.width], [p.cnt_length, p.cnt_width], rtol=1e-8, atol=1e-12
        ):
            raise ValueError(f"CNT {i} dimensions disagree with config")
    if any(overlaps(a, b) for a, b in combinations(rectangles, 2)):
        raise ValueError("CNT outer rectangles overlap or touch")
    return rectangles


def generate_rectangles(p: Parameters, seed: int):
    p.validate()
    rng = np.random.default_rng(seed)
    rectangles = []
    tol = max(1e-12, 1e-9 * p.box_size)
    for i in range(p.num_cnt):
        for _ in range(p.max_attempts):
            r = Rectangle(
                tuple(rng.uniform(0, p.box_size, 2)),
                p.cnt_length,
                p.cnt_width,
                math.radians(rng.uniform(p.angle_min, p.angle_max)),
            )
            coords = r.corners()
            if (
                np.all(coords > tol)
                and np.all(coords < p.box_size - tol)
                and not any(overlaps(r, a) for a in rectangles)
            ):
                rectangles.append(r)
                break
        else:
            raise ValueError(
                f"cannot place CNT {i + 1}/{p.num_cnt} after {p.max_attempts} attempts"
            )
    return rectangles


def save_corners(rectangles, path: Path):
    rows = [[i, *r.corners().ravel()] for i, r in enumerate(rectangles, 1)]
    np.savetxt(
        path,
        np.array(rows).reshape(-1, 9),
        delimiter="\t",
        header="CNT_ID\tx1\ty1\tx2\ty2\tx3\ty3\tx4\ty4",
        comments="",
        fmt=["%d"] + ["%.17g"] * 8,
    )


def read_corners(path: Path, p: Parameters):
    """Read the tab-separated output of save_rectangle_corners.m without resampling."""
    data = np.genfromtxt(path, delimiter="\t", names=True, ndmin=1)
    names = ("CNT_ID", "x1", "y1", "x2", "y2", "x3", "y3", "x4", "y4")
    if data.dtype.names != names:
        raise ValueError(
            "corner file requires header CNT_ID x1 y1 x2 y2 x3 y3 x4 y4 (tabs)"
        )
    rectangles = []
    for row in data:
        c = np.array([float(row[name]) for name in names[1:]]).reshape(4, 2)
        e1, e2 = c[1] - c[0], c[3] - c[0]
        length, width = np.linalg.norm(e1), np.linalg.norm(e2)
        if not np.isfinite(c).all() or min(length, width) <= 0:
            raise ValueError("nonfinite or degenerate rectangle in corner file")
        r = Rectangle(
            tuple(c.mean(axis=0)), float(length), float(width), math.atan2(e1[1], e1[0])
        )
        if not np.allclose(c, r.corners(), rtol=0, atol=1e-8 * p.box_size):
            raise ValueError(
                "corner rows must describe counterclockwise rectangular vertices"
            )
        rectangles.append(r)
    return validate_rectangles(rectangles, p)


def geometry_document(rectangles, p, seed):
    return {
        "schema": "cnt2d-geometry-v1",
        "box_size": p.box_size,
        "length_unit": p.length_unit,
        "seed": seed,
        "rng": "numpy.default_rng/PCG64" if seed is not None else "imported corners",
        "rectangles": [asdict(r) for r in rectangles],
    }
