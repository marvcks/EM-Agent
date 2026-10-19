"""Bounded CPU adapters for public retrosynthesis and UV correction-factor models.

Only stdlib is imported by the catalog/service; each calculation imports its own
isolated scientific environment. No network downloads occur during a job.
"""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile

ROOT = Path('/opt/em-agent-tools')
AI_ROOT = ROOT / 'aizynthfinder'
LCMS_ROOT = ROOT / 'lcms2yield'
AI_FILES = ('uspto_model.onnx', 'uspto_templates.csv.gz', 'uspto_filter_model.onnx', 'zinc_stock.hdf5')
LCMS_MODEL = LCMS_ROOT / 'source/model/model_pth/20250721.pth'
REACTION_APPS = {'aizynthfinder', 'lcms2yield'}
LCMS_ELEMENTS = {'C', 'N', 'O', 'S', 'F', 'P', 'Cl', 'Br', 'B', 'H', 'I', 'Si'}


def runtime_available(app_id):
    root = AI_ROOT if app_id == 'aizynthfinder' else LCMS_ROOT
    required = [root / '.venv/bin/python', root / 'manifest.json']
    required += [AI_ROOT / 'models' / name for name in AI_FILES] if app_id == 'aizynthfinder' else [LCMS_MODEL, LCMS_ROOT / 'source/model/predict.py']
    return os.access(required[0], os.X_OK) and all(path.is_file() and path.stat().st_size > 0 for path in required)


def validate_request(request):
    app_id = request.app_id
    task = 'retrosynthesis' if app_id == 'aizynthfinder' else 'correction_factor'
    if request.task != task or request.xyz or request.charge or request.multiplicity != 1:
        raise ValueError('invalid_reaction_input')
    lines = request.smiles.strip().splitlines()
    if not 1 <= len(lines) <= (1 if app_id == 'aizynthfinder' else 16):
        raise ValueError('invalid_smiles')
    for line in lines:
        # No salts, reaction SMILES, titles, whitespace, paths, or executable input.
        if not line or len(line) > 2048 or not re.fullmatch(r'[A-Za-z0-9@+\[\]()=#%/\\*\-]+', line):
            raise ValueError('invalid_smiles')
    return lines


def parse_molecules(smiles, app_id):
    from rdkit import Chem
    molecules = []
    total_atoms = 0
    for line in smiles:
        molecule = Chem.MolFromSmiles(line)
        if molecule is None or molecule.GetNumAtoms() == 0 or len(Chem.GetMolFrags(molecule)) != 1:
            raise ValueError('Invalid SMILES: a single connected molecule is required')
        if any(atom.GetAtomicNum() == 0 for atom in molecule.GetAtoms()):
            raise ValueError('Wildcard atoms are not supported')
        total_atoms += Chem.AddHs(molecule).GetNumAtoms()
        if total_atoms > 128:
            raise ValueError('The request exceeds 128 atoms including hydrogens')
        if app_id == 'lcms2yield' and any(atom.GetSymbol() not in LCMS_ELEMENTS for atom in molecule.GetAtoms()):
            raise ValueError('Unsupported lcms2yield element; use C/N/O/S/F/P/Cl/Br/B/H/I/Si')
        molecules.append(molecule)
    return molecules


def run_aizynth(request):
    from aizynthfinder.aizynthfinder import AiZynthFinder
    models = AI_ROOT / 'models'
    finder = AiZynthFinder(configdict={
        'expansion': {'uspto': [str(models / AI_FILES[0]), str(models / AI_FILES[1])]},
        'filter': {'uspto': str(models / AI_FILES[2])},
        'stock': {'zinc': str(models / AI_FILES[3])},
        'search': {'max_transforms': request['max_transforms'], 'iteration_limit': request['iterations'],
                   'time_limit': request['search_seconds'], 'return_first': False},
        'post_processing': {'min_routes': 1, 'max_routes': request['max_routes']},
    })
    finder.expansion_policy.select('uspto')
    finder.filter_policy.select('uspto')
    finder.stock.select('zinc')
    finder.target_smiles = request['smiles'].strip()
    print('Searching USPTO retrosynthetic templates against public ZINC stock', flush=True)
    finder.tree_search()
    finder.build_routes()
    routes = list(finder.routes.dicts)
    Path('routes.json').write_text(json.dumps(routes, indent=2, allow_nan=False))
    summaries = []
    for index, tree in enumerate(finder.routes.reaction_trees):
        summaries.append(f'Route {index + 1}: solved={tree.is_solved}')
        for reaction in tree.reactions():
            summaries.append('  retrosynthesis: ' + reaction.smiles)
        summaries.append('  precursors: ' + ', '.join(mol.smiles for mol in tree.leafs()))
    Path('routes.txt').write_text('\n'.join(summaries) + '\n')
    return {'route_count': len(routes), 'solved_count': sum(tree.is_solved for tree in finder.routes.reaction_trees),
            'statistics': finder.extract_statistics(), 'stock': 'public ZINC', 'policy': 'USPTO ONNX',
            'note': 'Solved means precursors are in this stock, not experimental validation. No solution within limits is a valid search outcome.'}


def run_lcms(request):
    import torch
    torch.set_num_threads(request['cores'])
    # Import the pinned upstream code; do not modify its model or feature encoding.
    sys.path.insert(0, str(LCMS_ROOT / 'source/model'))
    from predict import predict_by_smiles_list
    lines = request['smiles'].strip().splitlines()
    print('Predicting full-spectrum UV correction factors with upstream 20250721 model', flush=True)
    # pykan saves an initialization checkpoint to ./model. Keep that temporary
    # artifact out of persistent results without changing upstream inference.
    original = Path.cwd()
    with tempfile.TemporaryDirectory(prefix='lcms-inference-') as temporary:
        try:
            os.chdir(temporary)
            values = predict_by_smiles_list(lines, model_pth=str(LCMS_MODEL), batch_size=16)['preds']
        finally:
            os.chdir(original)
    factors = [{'smiles': line, 'cf': float(value)} for line, value in zip(lines, values)]
    if len(factors) != len(lines) or any(not math.isfinite(row['cf']) or row['cf'] <= 0 for row in factors):
        raise ValueError('Model produced invalid correction factors')
    with Path('correction_factors.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['smiles', 'cf'])
        writer.writeheader()
        writer.writerows(factors)
    return {'correction_factors': factors, 'model_sha256': hashlib.sha256(LCMS_MODEL.read_bytes()).hexdigest(),
            'note': 'CF values are UV correction factors, not reaction yields or percentages. Yield quantification additionally requires experimental LC-MS/UV measurements and the matching calibration protocol.'}


def verified_result(result, app_id, expected_count=None):
    if result.get('verified') is not True or result.get('app_id') != app_id:
        return False
    if app_id == 'aizynthfinder':
        count, solved = result.get('route_count'), result.get('solved_count')
        return type(count) is int and type(solved) is int and 0 <= solved <= count <= 25
    factors = result.get('correction_factors')
    return (isinstance(factors, list) and 1 <= len(factors) <= 16
            and (expected_count is None or len(factors) == expected_count)
            and all(isinstance(row, dict) and isinstance(row.get('smiles'), str)
                    and type(row.get('cf')) in (float, int) and math.isfinite(row['cf']) and row['cf'] > 0 for row in factors))


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    app_id = request['app_id']
    if app_id not in REACTION_APPS:
        raise ValueError('Unsupported application')
    if hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:request['cores']])
    parse_molecules(request['smiles'].strip().splitlines(), app_id)
    result = run_aizynth(request) if app_id == 'aizynthfinder' else run_lcms(request)
    result.update(app_id=app_id, verified=True,
                  provenance=json.loads(((AI_ROOT if app_id == 'aizynthfinder' else LCMS_ROOT) / 'manifest.json').read_text()))
    if not verified_result(result, app_id, len(request['smiles'].strip().splitlines())):
        raise ValueError('Incomplete prediction result')
    Path('result.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    with zipfile.ZipFile('results.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ('request.json', 'result.json', 'routes.json', 'routes.txt', 'correction_factors.csv'):
            if Path(name).is_file():
                archive.write(name)
    print(json.dumps(result, allow_nan=False), flush=True)
    print('EM_AGENT_REACTION_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
