"""Bounded molecular crystal search, executed only by the isolated MAGUS Python."""
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import zipfile

RUNTIME_PYTHON = Path('/opt/em-agent-tools/magus/mace-runner/.venv/bin/python')
MODEL_DIR = Path('/opt/em-agent-tools/mace-off23/models')
OFF23_ELEMENTS = {'H', 'C', 'N', 'O', 'F', 'P', 'S', 'Cl', 'Br', 'I'}


def validate_search(request, atoms):
    if (request['task'] != 'search' or request['charge'] != 0 or request['multiplicity'] != 1
            or not 2 <= len(atoms) or len(atoms) * request['molecules_per_cell'] > 128
            or any(atom.split()[0] not in OFF23_ELEMENTS for atom in atoms)):
        raise ValueError('invalid_magus_molecule')
    if request['volume_max'] <= request['volume_min']:
        raise ValueError('invalid_volume')


def components(atoms):
    import networkx as nx
    from ase.neighborlist import natural_cutoffs, neighbor_list
    graph = nx.Graph()
    graph.add_nodes_from(range(len(atoms)))
    first, second = neighbor_list('ij', atoms, natural_cutoffs(atoms, mult=1.1))
    graph.add_edges_from(zip(first.tolist(), second.tolist()))
    return [atoms[list(ids)].get_chemical_formula() for ids in nx.connected_components(graph)]


def run(request_file):
    import numpy as np
    import torch
    import yaml
    from ase.io import read, write
    from ase.filters import FrechetCellFilter
    from mace.calculators import MACECalculator

    root = Path.cwd()
    request = json.loads(Path(request_file).read_text())
    torch.set_num_threads(request['cores'])
    (root / 'molecule.xyz').write_text(request['xyz'])
    molecule = read(root / 'molecule.xyz')
    validate_search(request, [symbol for symbol in molecule.get_chemical_symbols()])
    if len(components(molecule)) != 1:
        raise ValueError('Provide one connected neutral molecule, not a prebuilt crystal or multiple molecules')
    symbols = list(dict.fromkeys(molecule.get_chemical_symbols()))
    copies = request['molecules_per_cell']
    atom_count = len(molecule) * copies
    # The explicit volume interval is supplied in A^3 for the entire cell.
    # Lattice bounds must allow elongated molecules and avoid contradictory limits.
    span = float(np.ptp(molecule.positions, axis=0).max())
    min_length = 3.0
    max_length = max(10.0, request['volume_max'] ** (1 / 3) * 2, span + 4)
    settings = {
        'formulaType': 'fix', 'structureType': 'bulk', 'pressure': 0,
        'initSize': request['population_size'], 'popSize': request['population_size'],
        'numGen': request['generations'], 'saveGood': 2, 'symbols': symbols,
        'molMode': True, 'inputMols': ['molecule.xyz'], 'formula': [copies],
        'min_n_atoms': atom_count, 'max_n_atoms': atom_count, 'spacegroup': ['2-230'],
        'd_ratio': 1.1, 'volume_ratio': 5, 'rand_ratio': 0.4,
        # MAGUS 2.2 can mutate parent geometry without updating cached energy when enabled.
        'add_sym': False, 'chkMol': True, 'molDetector': 3,
        'MainCalculator': {'calculator': 'mace-noselect', 'jobPrefix': 'MACE',
                           'mode': 'serial', 'eps': 0.05, 'maxStep': 200,
                           'maxMove': 0.1, 'optimizer': 'bfgs', 'relaxLattice': True},
        'distance_matrix': [[2.0] * len(symbols) for _ in symbols],
        'is_molextal': True,
        'check_mol_info': {'mol_formula': [copies], 'mol_cutoff': {},
                           'mol_graphs': [str(root / 'molecule.xyz')]},
        'minVolume': request['volume_min'], 'maxVolume': request['volume_max'],
        'minLattice': [min_length] * 3 + [60] * 3,
        'maxLattice': [max_length] * 3 + [120] * 3,
    }
    (root / 'input.yaml').write_text(yaml.safe_dump(settings, sort_keys=False))
    model = MODEL_DIR / f"MACE-OFF23_{request['model_size']}.model"
    model_settings = root / 'inputFold/MACE'
    model_settings.mkdir(parents=True, exist_ok=True)
    (model_settings / 'mace_setting.yaml').write_text(yaml.safe_dump({
        'modelType': 'ASE', 'model_paths': str(model), 'device': 'cpu', 'default_dtype': 'float64'}))
    executable = RUNTIME_PYTHON.with_name('magus')
    print('Starting MAGUS 2.2 + MACE-OFF23 (CPU); energies eV, cell volumes A^3', flush=True)
    # Inherit the service process group so stop/timeout kills all native workers.
    with (root / 'search.log').open('wb') as stream:
        process = subprocess.Popen([str(executable), 'search', '-i', 'input.yaml', '-ll', 'DEBUG'], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        for line in process.stdout:
            stream.write(line)
            stream.flush()
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()
        if process.wait() != 0:
            raise RuntimeError('Native MAGUS search failed')
    log = (root / 'search.log').read_text(errors='replace')
    generations = sorted(set(map(int, re.findall(r'=+ Generation (\d+) =+', log))))
    if generations != list(range(1, request['generations'] + 1)) or 'Maximum number of generation reached' not in log:
        raise RuntimeError('Search did not complete all requested generations')
    frames = read(root / 'results/good.traj', index=':')
    if not frames:
        raise RuntimeError('No retained crystal candidates')
    calculator = MACECalculator(model_paths=str(model), device='cpu', default_dtype='float64')
    rows = []
    for index, atoms in enumerate(frames):
        if (len(atoms) != atom_count or not atoms.pbc.all() or atoms.get_volume() <= 0
                or sorted(components(atoms)) != sorted(components(molecule) * copies)):
            raise RuntimeError('Retained crystal has invalid molecular composition')
        stored = float(atoms.info['energy'])
        stored_forces = np.asarray(atoms.info['forces'])
        stored_stress = np.asarray(atoms.info['stress'])
        atoms.calc = calculator
        energy = float(atoms.get_potential_energy())
        forces = atoms.get_forces()
        stress = atoms.get_stress()
        if (not math.isfinite(energy) or not np.isfinite(forces).all() or not np.isfinite(stress).all()
                or abs(energy - stored) > 1e-6 or np.max(np.abs(forces - stored_forces)) > 1e-5
                or np.max(np.abs(stress - stored_stress)) > 1e-8):
            raise RuntimeError('Retained crystal energy/force/stress verification failed')
        generalized_force = float(np.linalg.norm(FrechetCellFilter(atoms).get_forces(), axis=1).max())
        rows.append({'frame': index, 'energy_eV': energy, 'energy_per_atom_eV': energy / len(atoms),
                     'volume_A3': atoms.get_volume(), 'generalized_force_eV_A': generalized_force,
                     'converged': generalized_force <= 0.050001})
    rows.sort(key=lambda row: row['energy_eV'])
    converged = sum(row['converged'] for row in rows)
    if not converged:
        raise RuntimeError('No candidate converged within the relaxation limit')
    for rank, row in enumerate(rows, 1):
        row['rank'] = rank
        write(root / f'candidate-{rank}.cif', frames[row['frame']])
        write(root / f'POSCAR-{rank}.vasp', frames[row['frame']], format='vasp', direct=True, sort=True)
    report = {'verified': True, 'model': f"MACE-OFF23_{request['model_size']}",
              'energy_eV': rows[0]['energy_eV'], 'candidate_count': len(rows),
              'converged_count': converged, 'generations': generations, 'candidates': rows,
              'note': 'Small bounded search; does not establish a global minimum or DFT accuracy.'}
    (root / 'result.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    with zipfile.ZipFile(root / 'results.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob('*')):
            if path.is_file() and not path.is_symlink() and path.name not in {
                    'results.zip', 'job.json', 'job.json.next', 'output.log'} and 'scratch' not in path.parts:
                archive.write(path, path.relative_to(root))
    print('EM_AGENT_MAGUS_COMPLETE', flush=True)


if __name__ == '__main__':
    run(sys.argv[1])
