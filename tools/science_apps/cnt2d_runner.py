"""Bounded adapter for the open-source CNT/PVDF stationary conduction solver.

Validation uses only the standard library; heavy FEM imports happen in the
isolated process, never while the shared service imports this module.
"""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile

ROOT = Path('/opt/em-agent-tools/cnt2d')
MAX_CNT = 64
MAX_TRIANGLES = 500000
DEFAULTS = {
    'box_size': 100., 'cnt_length': 10., 'cnt_width': 1., 'surface_width': .1,
    'filler_area_fraction_target': .01, 'angle_min': -90., 'angle_max': 90.,
    'length_unit': 'mm', 'cnt_k': 400., 'pvdf_k': .146, 'surface_k': 7.642,
    't_left': 308., 't_right': 288., 'bulk_size': 5., 'interface_layers': 2,
}


def cnt2d_available(root=ROOT):
    return os.access(root / '.venv/bin/python', os.X_OK) and (root / 'manifest.json').is_file()


def corner_rows(text, p):
    if not text:
        return []
    if len(text.encode()) > 32768:
        raise ValueError('invalid_cnt2d_input')
    reader = csv.reader(io.StringIO(text.lstrip('\ufeff')), delimiter='\t')
    header = ['CNT_ID', 'x1', 'y1', 'x2', 'y2', 'x3', 'y3', 'x4', 'y4']
    if next(reader, None) != header:
        raise ValueError('invalid_cnt2d_input')
    rows, ids = [], set()
    for row in reader:
        if not row:
            continue
        if len(row) != 9 or len(rows) >= MAX_CNT:
            raise ValueError('invalid_cnt2d_input')
        try:
            index = int(row[0])
            values = [float(x) for x in row[1:]]
        except ValueError:
            raise ValueError('invalid_cnt2d_input') from None
        if index < 1 or index in ids or not all(math.isfinite(x) and 0 < x < p['box_size'] for x in values):
            raise ValueError('invalid_cnt2d_input')
        ids.add(index)
        points = list(zip(values[::2], values[1::2]))
        e = [points[1][j] - points[0][j] for j in range(2)]
        f = [points[3][j] - points[0][j] for j in range(2)]
        tol = 1e-8 * p['box_size']
        if (abs(math.hypot(*e) - p['cnt_length']) > tol
                or abs(math.hypot(*f) - p['cnt_width']) > tol
                or abs(e[0]*f[0] + e[1]*f[1]) > tol * p['cnt_length']
                or e[0]*f[1] - e[1]*f[0] <= 0
                or any(abs(points[2][j] - points[1][j] - points[3][j] + points[0][j]) > tol for j in range(2))):
            raise ValueError('invalid_cnt2d_input')
        rows.append(row)
    if not rows:
        raise ValueError('invalid_cnt2d_input')
    return rows


def expected_count(p, corners=''):
    if corners:
        return len(corner_rows(corners, p))
    if p['filler_area_fraction_target'] == 0:
        return 0
    return max(1, math.floor(p['filler_area_fraction_target'] * p['box_size']**2 /
                            (p['cnt_length'] * p['cnt_width']) + .5))


# @spec CNT2D-005 — Explicit geometry and mesh budgets, independent of molecular limits.
def validate_cnt2d(request):
    if (request.task != 'conduction' or request.method != 'FEM-P2' or request.basis
            or request.xyz or request.smiles or request.document_name or request.table_csv
            or request.charge or request.multiplicity != 1):
        raise ValueError('invalid_cnt2d_input')
    supplied = request.cnt_parameters or {}
    if not isinstance(supplied, dict) or supplied.keys() - DEFAULTS.keys():
        raise ValueError('invalid_cnt2d_input')
    p = {**DEFAULTS, **supplied}
    for key, value in p.items():
        if key == 'length_unit':
            if value not in ('m', 'cm', 'mm', 'um', 'nm'):
                raise ValueError('invalid_cnt2d_input')
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('invalid_cnt2d_input')
    if not isinstance(p['interface_layers'], int) or not 1 <= p['interface_layers'] <= 3:
        raise ValueError('invalid_cnt2d_input')
    length, width, surface, box = (p[k] for k in ('cnt_length', 'cnt_width', 'surface_width', 'box_size'))
    if (not 1e-6 <= box <= 1e6 or min(length, width, surface) <= 0
            or min(length, width) <= 2*surface or max(length, width) >= box
            or not -90 <= p['angle_min'] <= p['angle_max'] <= 90
            or not 0 <= p['filler_area_fraction_target'] <= .1
            or not .01 <= p['bulk_size']/box <= .25
            or surface / p['interface_layers'] / box < .00025
            or length/surface > 200
            or any(not 1e-4 <= p[k] <= 1e4 for k in ('cnt_k', 'pvdf_k', 'surface_k'))
            or any(not 1 <= p[k] <= 2000 for k in ('t_left', 't_right'))
            or abs(p['t_left'] - p['t_right']) < 1e-3):
        raise ValueError('invalid_cnt2d_input')
    count = expected_count(p, request.cnt_corners)
    if count > MAX_CNT:
        raise ValueError('invalid_cnt2d_input')
    return p


# @spec CNT2D-006 — Publish only the requested physics, finite metrics and bounded mesh.
def verified_cnt2d(result, request):
    try:
        p = validate_cnt2d(request)
        m = result['metrics']
        numeric = ('Keff_X', 'CNT_Number', 'Triangles', 'Energy_Balance_Error',
                   'Free_Residual_Relative', 'Heatflow_Left', 'Heatflow_Right',
                   'Matrix_Area_Fraction_Mesh', 'Core_Area_Fraction_Mesh', 'Interface_Area_Fraction_Mesh')
        if not all(isinstance(m[k], (int, float)) and not isinstance(m[k], bool) and math.isfinite(m[k]) for k in numeric):
            return False
        return (result.get('verified') is True and result.get('app_id') == 'cnt2d'
                and result.get('unit') == 'W/(m K)' and result['parameters'] == p
                and result.get('seed') == (None if request.cnt_corners else request.cnt_seed)
                and m['CNT_Number'] == expected_count(p, request.cnt_corners)
                and 0 < m['Triangles'] <= MAX_TRIANGLES and m['Keff_X'] > 0
                and 0 <= m['Energy_Balance_Error'] < 1e-5
                and 0 <= m['Free_Residual_Relative'] < 1e-8
                and m['Heatflow_Left'] * (p['t_left'] - p['t_right']) < 0
                and m['Heatflow_Right'] * (p['t_left'] - p['t_right']) > 0
                # Normalized quadrature can sum to 1 + a few ulps for pure matrix.
                and all(-1e-10 <= m[k] <= 1 + 1e-10 for k in numeric[-3:])
                and math.isclose(m['Keff_X'], (abs(m['Heatflow_Left']) + abs(m['Heatflow_Right'])) /
                                 (2 * abs(p['t_left'] - p['t_right'])), rel_tol=1e-7)
                and abs(sum(m[k] for k in numeric[-3:]) - 1) < 1e-8)
    except (KeyError, TypeError, ValueError):
        return False


def main():
    from importlib.metadata import version
    request = SimpleNamespace(**json.loads(Path(sys.argv[1]).read_text()))
    parameters = validate_cnt2d(request)
    source = Path(__file__).resolve().parent
    if not (source / 'cnt2d').is_dir():
        source = source.parents[1] / 'CNT2D_COMSOL_20260930/python'
    sys.path.insert(0, str(source))
    from cnt2d.model import Parameters, generate_rectangles, read_corners, save_corners, geometry_document
    from cnt2d.mesh import build_mesh
    from cnt2d.solver import solve_cnt
    from cnt2d.output import export_fields, plot_results, write_json, write_table
    if hasattr(os, 'sched_getaffinity'):
        allowed = sorted(os.sched_getaffinity(0))
        os.sched_setaffinity(0, allowed[:request.cores])
    p = Parameters(**parameters, mesh_threads=request.cores).validate()
    seed = None if request.cnt_corners else request.cnt_seed
    if request.cnt_corners:
        Path('Corners.txt').write_text(request.cnt_corners)
        rectangles = read_corners(Path('Corners.txt'), p)
    else:
        rectangles = generate_rectangles(p, seed)
        save_corners(rectangles, Path('Corners.txt'))
    write_json(Path('parameters.json'), p.to_dict())
    write_json(Path('geometry.json'), geometry_document(rectangles, p, seed))
    print(f'CNT2D: {len(rectangles)} CNT, {p.length_unit}, quadratic stationary FEM', flush=True)
    mesh_data = build_mesh(p, rectangles, Path('mesh.msh'))
    limit = MAX_TRIANGLES if request.memory_mb >= 4096 else 200000
    if mesh_data[0].nelements > limit:
        raise ValueError(f'Mesh exceeds {limit} triangles; coarsen mesh or increase requested memory to 4096 MB')
    print(f'Mesh: {mesh_data[0].nelements} triangles; solving...', flush=True)
    solution = solve_cnt(p, rectangles, mesh_data=mesh_data)
    export_fields(Path('.'), solution, p)
    plot_results(Path('.'), solution, rectangles, p)
    write_table(Path('Summary.csv'), [solution.metrics])
    result = {'verified': True, 'app_id': 'cnt2d', 'unit': 'W/(m K)',
              'parameters': parameters, 'seed': seed, 'metrics': solution.metrics,
              'solver': 'conforming P2 FEM, Gmsh + scikit-fem + SciPy',
              'versions': {n: version(n) for n in ('numpy', 'scipy', 'gmsh', 'scikit-fem')},
              'geometry_sha256': hashlib.sha256(Path('geometry.json').read_bytes()).hexdigest(),
              'validation_scope': 'One 5%/50-CNT COMSOL example cross-checked; other conditions need convergence checks.',
              'mesh_convergence_proven': False}
    if not verified_cnt2d(result, request):
        raise ValueError('CNT2D result failed verification')
    write_json(Path('result.json'), result)
    with zipfile.ZipFile('results.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(Path('.').iterdir()):
            if path.is_file() and not path.is_symlink() and path.name not in ('results.zip', 'output.log', 'job.json'):
                bundle.write(path, path.name)
    print(f"Keff_X = {solution.metrics['Keff_X']:.12g} W/(m K)", flush=True)
    print('EM_AGENT_CNT2D_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
