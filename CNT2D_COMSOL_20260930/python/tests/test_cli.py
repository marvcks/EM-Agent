import json

import meshio
import numpy as np

from cnt2d.cli import main


# @spec CNT2D-004 — Actual CLI exports reloadable results and refuses overwrites.
def test_run_exports_and_protects_existing_output(tmp_path):
    config = tmp_path / "input.json"
    config.write_text(json.dumps({"filler_area_fraction_target": 0, "bulk_size": 20}))
    output = tmp_path / "results"
    args = ["run", "--config", str(config), "--output", str(output), "--no-images"]
    assert main(args) == 0
    case = output / "sample_001"
    result = json.loads((case / "result.json").read_text())
    assert result["Status"] == "SOLVED"
    assert abs(result["Keff_X"] - 0.146) < 1e-10
    manifest = json.loads((case / "manifest.json").read_text())
    assert manifest["status"] == "SOLVED"
    assert manifest["geometry_sha256"]
    field = meshio.read(case / "fields.vtu")
    assert np.all(np.isfinite(field.point_data["temperature_K"]))
    saved = np.load(case / "solution.npz")
    assert saved["temperature_K"].shape == (result["DOFs"],)
    before = (case / "manifest.json").read_bytes()
    assert main(args) == 1
    assert (case / "manifest.json").read_bytes() == before


def test_convergence_reuses_geometry_and_marks_reference(tmp_path):
    config = tmp_path / "input.json"
    config.write_text(json.dumps({"filler_area_fraction_target": 0}))
    output = tmp_path / "convergence"
    assert (
        main(
            [
                "converge",
                "--config",
                str(config),
                "--output",
                str(output),
                "--seeds",
                "7",
                "--bulk-sizes",
                "20",
                "10",
                "--interface-layers",
                "1",
                "--no-images",
            ]
        )
        == 0
    )
    details = json.loads((output / "convergence.json").read_text())
    assert len(details) == 2
    assert sum(r["Is_Reference"] for r in details) == 1
    assert all(r["Reference_Available"] for r in details)
    assert all(r["Keff_Relative_Error_Percent"] < 1e-7 for r in details)
    hashes = {
        json.loads(p.read_text())["geometry_sha256"]
        for p in output.glob("Seed*/manifest.json")
    }
    assert len(hashes) == 1


def test_failed_reference_is_recorded_without_fallback(tmp_path, monkeypatch):
    import cnt2d.cli as cli

    actual = cli.solve_cnt

    def fail_fine_mesh(p, *args, **kwargs):
        if p.bulk_size == 10:
            raise RuntimeError("test: mesher failed")
        return actual(p, *args, **kwargs)

    monkeypatch.setattr(cli, "solve_cnt", fail_fine_mesh)
    config = tmp_path / "input.json"
    config.write_text(json.dumps({"filler_area_fraction_target": 0}))
    output = tmp_path / "failed"
    assert (
        main(
            [
                "converge",
                "--config",
                str(config),
                "--output",
                str(output),
                "--seeds",
                "7",
                "--bulk-sizes",
                "20",
                "10",
                "--interface-layers",
                "1",
                "--no-images",
            ]
        )
        == 1
    )
    details = json.loads((output / "convergence.json").read_text())
    assert {r["Status"] for r in details} == {"SOLVED", "FAILED"}
    assert all(not r["Reference_Available"] for r in details)
    assert all(r["Keff_Relative_Error_Percent"] is None for r in details)
