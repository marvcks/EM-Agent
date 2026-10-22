"""Serial standalone batch runs and mesh comparisons, without MATLAB or COMSOL."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time
import traceback

from .model import (
    Parameters,
    generate_rectangles,
    geometry_document,
    read_corners,
    save_corners,
)
from .output import export_fields, plot_results, provenance, write_json, write_table
from .solver import solve_cnt


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def new_output(path):
    # Atomic ownership: never share an existing directory, even if it looks empty.
    path.mkdir(parents=True, exist_ok=False)


# @spec CNT2D-004 — A case becomes SOLVED only after solving and exporting all requested artifacts.
def run_case(directory, p, rectangles, seed, images):
    new_output(directory)
    started = time.perf_counter()
    geometry = geometry_document(rectangles, p, seed)
    geometry_hash = hashlib.sha256(
        json.dumps(geometry, sort_keys=True).encode()
    ).hexdigest()
    manifest = {
        "status": "RUNNING",
        "started_utc": utc_now(),
        "parameters": p.to_dict(),
        "geometry_sha256": geometry_hash,
        **provenance(),
        "units": {
            "Heatflow_Left": "W/m",
            "Heatflow_Right": "W/m",
            "Keff_X": "W/(m K)",
            "Avg_HeatFlux_X": "W/m^2",
            "mesh.msh": "normalized coordinates: one box side = 1",
            "fields.vtu": "coordinates in m; vertex temperatures and cell-average flux",
            "solution.npz": "coordinates in m; all FEM DOFs, including P2 mid-edge DOFs",
        },
        "flux_method": "weak-form boundary reactions; gradient flux independently reported",
        "comsol_comparison": "not validated against COMSOL reference data",
    }
    write_json(directory / "manifest.json", manifest)
    row = {
        "Status": "FAILED",
        "RNG_Seed": seed,
        "Bulk_Size": p.bulk_size,
        "Interface_Layers": p.interface_layers,
        "Temperature_Order": p.temperature_order,
        "Length_Unit": p.length_unit,
        "Geometry_SHA256": geometry_hash,
    }
    try:
        write_json(directory / "parameters.json", p.to_dict())
        write_json(directory / "geometry.json", geometry)
        save_corners(rectangles, directory / "Corners.txt")
        solution = solve_cnt(p, rectangles, msh_path=directory / "mesh.msh")
        export_fields(directory, solution, p)
        if images:
            plot_results(directory, solution, rectangles, p)
        row.update(solution.metrics)
        row.update(
            Status="SOLVED", Error_Message="", Runtime_s=time.perf_counter() - started
        )
        write_json(directory / "result.json", row)
        write_table(directory / "Summary.txt", [row], delimiter="\t")
        manifest["status"] = "SOLVED"
        print(
            f"{directory.name}: k_eff,x={row['Keff_X']:.10g} W/(m K), "
            f"{row['Triangles']} triangles, {row['Runtime_s']:.2f} s",
            flush=True,
        )
    except Exception as exc:
        row.update(Error_Message=str(exc), Runtime_s=time.perf_counter() - started)
        write_json(directory / "result.json", row)
        (directory / "error.log").write_text(traceback.format_exc())
        manifest.update(status="FAILED", error=str(exc))
        print(f"{directory.name}: FAILED: {exc}", file=sys.stderr, flush=True)
    manifest.update(finished_utc=utc_now(), runtime_s=time.perf_counter() - started)
    write_json(directory / "manifest.json", manifest)
    return row


def run_batch(args, p):
    if args.samples < 1 or args.seed < 0:
        raise ValueError("samples must be positive and seed nonnegative")
    if args.corners and args.samples != 1:
        raise ValueError("--corners requires --samples 1")
    imported = read_corners(args.corners, p) if args.corners else None
    new_output(args.output)
    rows = []
    for index in range(args.samples):
        seed = None if imported is not None else args.seed + index
        rectangles = imported if imported is not None else generate_rectangles(p, seed)
        row = run_case(
            args.output / f"sample_{index + 1:03d}",
            p,
            rectangles,
            seed,
            not args.no_images,
        )
        rows.append({"Series_ID": index + 1, **row})
        write_table(args.output / "All_Summary.csv", rows)
    return int(any(row["Status"] != "SOLVED" for row in rows))


def convergence_summary(rows):
    summary = []
    combinations = sorted(
        {(r["Bulk_Size"], r["Interface_Layers"]) for r in rows}, reverse=True
    )
    for bulk, layers in combinations:
        cases = [
            r
            for r in rows
            if r["Bulk_Size"] == bulk and r["Interface_Layers"] == layers
        ]
        solved = [r for r in cases if r["Status"] == "SOLVED"]
        values = [r["Keff_X"] for r in solved]
        errors = [
            r["Keff_Relative_Error_Percent"]
            for r in solved
            if r["Keff_Relative_Error_Percent"] is not None
        ]
        checks = [r["Within_Reference_Tolerance"] for r in cases]
        summary.append(
            {
                "Bulk_Size": bulk,
                "Interface_Layers": layers,
                "Total_Cases": len(cases),
                "Solved_Cases": len(solved),
                "Failed_Cases": len(cases) - len(solved),
                "Mean_Keff_X": statistics.mean(values) if values else None,
                "Std_Keff_X": statistics.stdev(values) if len(values) > 1 else None,
                "Max_Relative_Error_Percent": max(errors) if errors else None,
                "All_Within_Reference_Tolerance": all(checks)
                if all(c is not None for c in checks)
                else None,
            }
        )
    return summary


# @spec CNT2D-004 — Fixed geometry per seed; a failed reference is never replaced silently.
def run_convergence(args, p):
    if (
        not all(s >= 0 for s in args.seeds)
        or len(set(args.seeds)) != len(args.seeds)
        or len(set(args.bulk_sizes)) != len(args.bulk_sizes)
        or len(set(args.interface_layers)) != len(args.interface_layers)
    ):
        raise ValueError(
            "seeds must be nonnegative; seeds and mesh lists must have no duplicates"
        )
    if args.tolerance_percent <= 0 or not math.isfinite(args.tolerance_percent):
        raise ValueError("tolerance-percent must be positive and finite")
    for bulk in args.bulk_sizes:
        for layers in args.interface_layers:
            replace(p, bulk_size=bulk, interface_layers=layers).validate()
    if len(args.bulk_sizes) * len(args.interface_layers) < 2:
        raise ValueError("a mesh comparison requires at least two mesh combinations")
    new_output(args.output)
    reference = (min(args.bulk_sizes), max(args.interface_layers))
    rows = []
    for seed in args.seeds:
        rectangles = generate_rectangles(p, seed)
        seed_rows = []
        for bulk in args.bulk_sizes:
            for layers in args.interface_layers:
                current = replace(p, bulk_size=bulk, interface_layers=layers)
                name = f"Seed{seed}-H{bulk:g}-Layers{layers}"
                row = run_case(
                    args.output / name, current, rectangles, seed, not args.no_images
                )
                row.update(
                    Is_Reference=(bulk, layers) == reference,
                    Reference_Available=False,
                    Keff_Reference=None,
                    Keff_Relative_Error_Percent=None,
                    Within_Reference_Tolerance=None,
                    Tolerance_Percent=args.tolerance_percent,
                )
                seed_rows.append(row)
                # Persist partial progress; comparisons remain unavailable until reference completes.
                write_table(
                    args.output / "Mesh_Convergence_Detail.csv", rows + seed_rows
                )
                write_json(args.output / "convergence.json", rows + seed_rows)
        ref = next(r for r in seed_rows if r["Is_Reference"])
        if ref["Status"] == "SOLVED":
            for row in seed_rows:
                row.update(Reference_Available=True, Keff_Reference=ref["Keff_X"])
                if row["Status"] == "SOLVED":
                    error = 100 * abs(row["Keff_X"] - ref["Keff_X"]) / ref["Keff_X"]
                    row["Keff_Relative_Error_Percent"] = error
                    if not row["Is_Reference"]:
                        row["Within_Reference_Tolerance"] = (
                            error <= args.tolerance_percent
                        )
        rows.extend(seed_rows)
        write_table(args.output / "Mesh_Convergence_Detail.csv", rows)
        write_json(args.output / "convergence.json", rows)
        write_table(
            args.output / "Mesh_Convergence_Summary.csv", convergence_summary(rows)
        )
    return int(any(r["Status"] != "SOLVED" for r in rows))


def parser():
    root = argparse.ArgumentParser(
        description="Open-source 2D CNT/PVDF/interface stationary conduction"
    )
    commands = root.add_subparsers(dest="command", required=True)
    for command in ("run", "converge"):
        sub = commands.add_parser(command)
        sub.add_argument(
            "--config",
            type=Path,
            help="JSON overrides; omitted keys use original physical defaults",
        )
        sub.add_argument(
            "--output",
            type=Path,
            required=True,
            help="new output directory (must not exist)",
        )
        sub.add_argument(
            "--no-images",
            action="store_true",
            help="skip PNGs; field data is still exported",
        )
        if command == "run":
            sub.add_argument("--seed", type=int, default=20260901)
            sub.add_argument("--samples", type=int, default=1)
            sub.add_argument(
                "--corners",
                type=Path,
                help="import MATLAB tab-separated Corners.txt instead of generating CNTs",
            )
        else:
            sub.add_argument(
                "--seeds", type=int, nargs="+", default=[20260901, 20260902, 20260903]
            )
            sub.add_argument(
                "--bulk-sizes", type=float, nargs="+", default=[8.0, 4.0, 2.0]
            )
            sub.add_argument("--interface-layers", type=int, nargs="+", default=[1, 2])
            sub.add_argument("--tolerance-percent", type=float, default=1.0)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        p = Parameters.load(args.config)
        return run_batch(args, p) if args.command == "run" else run_convergence(args, p)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
