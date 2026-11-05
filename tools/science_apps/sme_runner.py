"""Structure-Mask Explanation (SME) property prediction and fragment attribution.

The service imports this module without PyTorch or RDKit; heavy imports happen
only inside ``run_job``. Model files and the training manifest live under
``/opt/em-agent-tools/sme`` and are mounted into the science container.

SME masks a molecular substructure (atoms set to zero in the readout) and
reports how much the model prediction changes. Attribution is a perturbation
sensitivity of the trained model, not a causal chemical statement.
"""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path(os.environ.get('EM_AGENT_SME_ROOT', '/opt/em-agent-tools/sme'))
APP_ID = 'sme'
MARKER = 'EM_AGENT_SME_COMPLETE'
MAX_MOLECULES = 10
MAX_SMILES_LENGTH = 5000
MAX_ATOMS = 128
MAX_FRAGMENTS_PER_SCHEME = 80
FRAGMENTATIONS = ('brics', 'murcko', 'fg')
TASKS = {
    'Density_R': {'label': '密度', 'kind': 'regression'},
    'DV_R': {'label': '爆速', 'kind': 'regression'},
    'DV_C': {'label': '爆速分类', 'kind': 'classification'},
    'IS_R': {'label': '撞击感度', 'kind': 'regression'},
    'IS_C': {'label': '撞击感度分类', 'kind': 'classification'},
    'MP': {'label': '熔点', 'kind': 'regression'},
    'ESOL': {'label': '水溶解度', 'kind': 'regression'},
}
# Functional-group SMARTS from the supplied package's build_data.py; the
# catalog groups carry a redundant attachment carbon, so a second match
# without that carbon determines the atoms actually masked.
FG_SMARTS = [
    '[N;D2]-[C;D3](=O)-[C;D1;H3]', 'C(=O)[O;D1]', 'C(=O)[O;D2]-[C;D1;H3]',
    'C(=O)-[H]', 'C(=O)-[N;D1]', 'C(=O)-[C;D1;H3]', '[N;D2]=[C;D2]=[O;D1]',
    '[N;D2]=[C;D2]=[S;D1]', '[N;D3](=[O;D1])[O;D1]', '[N;R0]=[O;D1]', '[N;R0]-[O;D1]',
    '[N;R0]-[C;D1;H3]', '[N;R0]=[C;D1;H2]', '[N;D2]=[N;D2]-[C;D1;H3]', '[N;D2]=[N;D1]',
    '[N;D2]#[N;D1]', '[C;D2]#[N;D1]', '[S;D4](=[O;D1])(=[O;D1])-[N;D1]',
    '[N;D2]-[S;D4](=[O;D1])(=[O;D1])-[C;D1;H3]', '[S;D4](=O)(=O)-[O;D1]',
    '[S;D4](=O)(=O)-[O;D2]-[C;D1;H3]', '[S;D4](=O)(=O)-[C;D1;H3]', '[S;D4](=O)(=O)-[Cl]',
    '[S;D3](=O)-[C;D1]', '[S;D2]-[C;D1;H3]', '[S;D1]', '[S;D1]', '[#9,#17,#35,#53]',
    '[C;D4]([C;D1])([C;D1])-[C;D1]',
    '[C;D4](F)(F)F', '[C;D2]#[C;D1;H]', '[C;D3]1-[C;D2]-[C;D2]1', '[O;D2]-[C;D2]-[C;D1;H3]',
    '[O;D2]-[C;D1;H3]', '[O;D1]', '[O;D1]', '[N;D1]', '[N;D1]', '[N;D1]']


def sme_available(root=ROOT):
    manifest_path = root / 'manifest.json'
    if not os.access(root / '.venv/bin/python', os.X_OK) or not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return False
    tasks = manifest.get('tasks')
    if not isinstance(tasks, dict) or not tasks:
        return False
    for task in tasks.values():
        seeds = task.get('seeds') if isinstance(task, dict) else None
        if not isinstance(seeds, list) or not seeds:
            return False
        if any(not (root / 'models' / str(seed.get('file', ''))).is_file() for seed in seeds):
            return False
    return True


# @spec SME-002 — Bounded SMILES-only contract, one property task per job
def validate_sme(request):
    if (request.task != 'prediction' or request.method not in ('', 'RGCN')
            or request.basis or request.xyz or request.document_name
            or request.table_csv or request.input_mode != 'single'
            or request.charge or request.multiplicity != 1
            or request.compound_name or request.input_kind != 'smiles'
            or request.sme_task not in TASKS
            or request.sme_fragmentation not in ('all', *FRAGMENTATIONS)):
        raise ValueError('invalid_sme_input')
    lines = [line.strip() for line in request.smiles.splitlines() if line.strip()]
    if not 1 <= len(lines) <= MAX_MOLECULES:
        raise ValueError('invalid_sme_input')
    if len(set(lines)) != len(lines):
        raise ValueError('invalid_sme_input')
    if any(len(line) > MAX_SMILES_LENGTH or ' ' in line for line in lines):
        raise ValueError('invalid_sme_input')


def selected_fragmentations(request):
    choice = request.get('sme_fragmentation') if isinstance(request, dict) else request.sme_fragmentation
    return list(FRAGMENTATIONS) if choice == 'all' else [choice]


def request_smiles(request):
    if isinstance(request, dict):
        text = request.get('smiles', '')
    else:
        text = request.smiles
    return [line.strip() for line in text.splitlines() if line.strip()]


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(root=ROOT, verify_task=None):
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest.get('app_id') != APP_ID or manifest.get('format') != 1:
        raise ValueError('unsupported SME manifest')
    tasks = manifest.get('tasks')
    if not isinstance(tasks, dict) or verify_task not in tasks:
        raise ValueError('task_unavailable')
    task = tasks[verify_task]
    if task.get('kind') != TASKS[verify_task]['kind'] or not isinstance(task.get('seeds'), list):
        raise ValueError('invalid SME manifest')
    for seed in task['seeds']:
        model_path = root / 'models' / str(seed.get('file', ''))
        if Path(seed.get('file', '')).name != seed.get('file') or not model_path.is_file():
            raise ValueError('missing SME model file')
        if sha256_file(model_path) != seed.get('sha256'):
            raise ValueError('SME model checksum mismatch')
    return manifest, task


def _atom_features(atom, Chem):
    symbols = ['B', 'C', 'N', 'O', 'F', 'Si', 'P', 'S', 'Cl', 'As', 'Se', 'Br', 'Te', 'I', 'At', 'other']
    hybridization = [Chem.rdchem.HybridizationType.SP, Chem.rdchem.HybridizationType.SP2,
                     Chem.rdchem.HybridizationType.SP3, Chem.rdchem.HybridizationType.SP3D,
                     Chem.rdchem.HybridizationType.SP3D2, 'other']

    def one_of_k_unk(value, allowed):
        if value not in allowed:
            value = allowed[-1]
        return [value == item for item in allowed]

    features = one_of_k_unk(atom.GetSymbol(), symbols)
    features += [atom.GetDegree() == degree for degree in range(7)]
    features += [atom.GetFormalCharge(), atom.GetNumRadicalElectrons()]
    features += one_of_k_unk(atom.GetHybridization(), hybridization)
    features += [bool(atom.GetIsAromatic())]
    features += one_of_k_unk(atom.GetTotalNumHs(), [0, 1, 2, 3, 4])
    try:
        features += one_of_k_unk(atom.GetProp('_CIPCode'), ['R', 'S'])
    except KeyError:
        features += [False, False]
    features += [atom.HasProp('_ChiralityPossible')]
    if len(features) != 40:
        raise ValueError('unexpected atom feature size')
    return features


def _bond_type_index(bond, Chem):
    types = [bond.GetBondType() == Chem.rdchem.BondType.SINGLE,
             bond.GetBondType() == Chem.rdchem.BondType.DOUBLE,
             bond.GetBondType() == Chem.rdchem.BondType.TRIPLE,
             bond.GetBondType() == Chem.rdchem.BondType.AROMATIC]
    if not any(types):
        raise ValueError('unsupported bond type')
    index = types.index(True)
    stereo = str(bond.GetStereo())
    stereo_index = ['STEREONONE', 'STEREOANY', 'STEREOZ', 'STEREOE'].index(stereo) \
        if stereo in ('STEREONONE', 'STEREOANY', 'STEREOZ', 'STEREOE') else 3
    return index + (4 if bond.GetIsConjugated() else 0) + (8 if bond.IsInRing() else 0) + 16 * stereo_index


def _graph_arrays(mol, Chem, th):
    import numpy as np
    features = np.asarray([_atom_features(atom, Chem) for atom in mol.GetAtoms()], dtype=np.float32)
    src, dst, etype = [], [], []
    for bond in mol.GetBonds():
        begin, end = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        bond_type = _bond_type_index(bond, Chem)
        src += [begin, end]
        dst += [end, begin]
        etype += [bond_type, bond_type]
    return (th.from_numpy(features), th.tensor(src, dtype=th.long),
            th.tensor(dst, dtype=th.long), th.tensor(etype, dtype=th.long))


def _tensor_params(state, th):
    layers = []
    index = 0
    while f'rgcn_gnn_layers.{index}.graph_conv_layer.linear_r.W' in state:
        prefix = f'rgcn_gnn_layers.{index}.'
        weight = state[prefix + 'graph_conv_layer.linear_r.W']
        coeff = state[prefix + 'graph_conv_layer.linear_r.coeff']
        per_type = (coeff @ weight.reshape(weight.shape[0], -1)).reshape(weight.shape)
        layers.append({
            'weight': per_type,
            'h_bias': state[prefix + 'graph_conv_layer.h_bias'],
            'loop': state[prefix + 'graph_conv_layer.loop_weight'],
            'res_w': state[prefix + 'res_connection.weight'],
            'res_b': state[prefix + 'res_connection.bias'],
            'bn_w': state[prefix + 'bn_layer.weight'], 'bn_b': state[prefix + 'bn_layer.bias'],
            'bn_mean': state[prefix + 'bn_layer.running_mean'],
            'bn_var': state[prefix + 'bn_layer.running_var']})
        index += 1
    if not layers:
        raise ValueError('unsupported SME model')
    fcs = []
    for name in ('fc_layers1', 'fc_layers2', 'fc_layers3'):
        fcs.append({'w': state[name + '.1.weight'], 'b': state[name + '.1.bias'],
                    'bn_w': state[name + '.3.weight'], 'bn_b': state[name + '.3.bias'],
                    'bn_mean': state[name + '.3.running_mean'], 'bn_var': state[name + '.3.running_var']})
    return {'layers': layers,
            'aw_w': state['readout.atom_weighting.0.weight'][0],
            'aw_b': state['readout.atom_weighting.0.bias'][0],
            'fcs': fcs,
            'pred_w': state['predict.0.weight'][0], 'pred_b': state['predict.0.bias'][0]}


def _predict(params, graph, smask, th):
    features, src, dst, etype = graph
    h = features
    for layer in params['layers']:
        previous = h
        msg = th.bmm(h[src].unsqueeze(1), layer['weight'][etype]).squeeze(1)
        agg = th.zeros(h.shape[0], msg.shape[1], dtype=h.dtype).index_add_(0, dst, msg)
        h = th.relu(agg + layer['h_bias'] + previous @ layer['loop'])
        h = h + th.relu(previous @ layer['res_w'].t() + layer['res_b'])
        h = (h - layer['bn_mean']) / th.sqrt(layer['bn_var'] + 1e-5) * layer['bn_w'] + layer['bn_b']
    weight = th.sigmoid(h @ params['aw_w'] + params['aw_b'])
    graph_feature = (h * (weight * smask)[:, None]).sum(0)
    x = graph_feature
    for fc in params['fcs']:
        x = th.relu(x @ fc['w'].t() + fc['b'])
        x = (x - fc['bn_mean']) / th.sqrt(fc['bn_var'] + 1e-5) * fc['bn_w'] + fc['bn_b']
    return float((x @ params['pred_w'] + params['pred_b']).item())


def _components_with_cut_bonds(mol, cut_bonds):
    adjacency = {atom.GetIdx(): [] for atom in mol.GetAtoms()}
    for bond in mol.GetBonds():
        pair = tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())))
        if pair in cut_bonds:
            continue
        adjacency[pair[0]].append(pair[1])
        adjacency[pair[1]].append(pair[0])
    seen, components = set(), []
    for start in adjacency:
        if start in seen:
            continue
        stack, component = [start], []
        seen.add(start)
        while stack:
            atom = stack.pop()
            component.append(atom)
            for neighbor in adjacency[atom]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return sorted(components)


def _brics_fragments(mol, Chem):
    from rdkit.Chem import BRICS
    cut = {tuple(sorted(pair)) for pair, _ in BRICS.FindBRICSBonds(mol)}
    return _components_with_cut_bonds(mol, cut)


def _murcko_fragments(mol, Chem):
    from rdkit.Chem.Scaffolds import MurckoScaffold
    scaffold = MurckoScaffold.GetScaffoldForMol(mol)
    if scaffold.GetNumAtoms() == 0:
        return [sorted(atom.GetIdx() for atom in mol.GetAtoms())]
    scaffold_atoms = set(mol.GetSubstructMatch(scaffold))
    cut = {tuple(sorted((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())))
           for bond in mol.GetBonds()
           if (bond.GetBeginAtomIdx() in scaffold_atoms) != (bond.GetEndAtomIdx() in scaffold_atoms)}
    return _components_with_cut_bonds(mol, cut)


# @spec SME-003 — Package functional-group matching with subsumption cleanup
def _fg_fragments(mol, Chem):
    from rdkit import RDConfig
    from rdkit.Chem import FragmentCatalog
    catalog_path = os.path.join(RDConfig.RDDataDir, 'FunctionalGroups.txt')
    catalog = FragmentCatalog.FragCatParams(1, 6, catalog_path)
    groups_with_carbon = [catalog.GetFuncGroup(i) for i in range(len(FG_SMARTS))]
    without_carbon = [Chem.MolFromSmarts(smarts) for smarts in FG_SMARTS]
    names = [group.GetProp('_Name') for group in groups_with_carbon]
    name_by_match = {}
    for cap_group, group_mol, name in zip(groups_with_carbon, without_carbon, names):
        with_carbon = mol.GetSubstructMatches(cap_group)
        without = mol.GetSubstructMatches(group_mol)
        for match in without:
            if any(set(match).issubset(set(parent)) for parent in with_carbon):
                name_by_match.setdefault(tuple(sorted(match)), name)
    # Keep only atom sets not contained in a larger matched group; this drops
    # the tiny overlapping matches that the catalog's carbon-capped groups add.
    remaining = []
    for match in sorted(name_by_match, key=len, reverse=True):
        if not any(set(match).issubset(set(kept)) for kept in remaining):
            remaining.append(match)
    return [list(match) for match in remaining], [name_by_match[match] for match in remaining]


def accumulate_fragments(mol, scheme, Chem):
    if scheme == 'brics':
        fragments = _brics_fragments(mol, Chem)
        labels = [Chem.MolFragmentToSmiles(mol, atomsToUse=fragment) for fragment in fragments]
    elif scheme == 'murcko':
        from rdkit.Chem.Scaffolds import MurckoScaffold
        fragments = _murcko_fragments(mol, Chem)
        scaffold = MurckoScaffold.GetScaffoldForMol(mol)
        if scaffold.GetNumAtoms() == 0:
            labels = ['whole molecule']
        else:
            scaffold_atoms = set(mol.GetSubstructMatch(scaffold))
            labels, side_chains = [], 0
            for fragment in fragments:
                if set(fragment) == scaffold_atoms:
                    labels.append('scaffold')
                else:
                    side_chains += 1
                    labels.append(f'side chain {side_chains}')
    else:
        fragments, labels = _fg_fragments(mol, Chem)
    seen, unique_fragments, unique_labels = set(), [], []
    for fragment, label in zip(fragments, labels):
        key = tuple(fragment)
        if key in seen:
            continue
        seen.add(key)
        unique_fragments.append(fragment)
        unique_labels.append(label)
    return unique_fragments, unique_labels


def _color(value):
    stops = [(-1.0, (0.0, 0.0, 0.3)), (-0.5, (0.0, 0.0, 0.9)), (0.0, (1.0, 1.0, 1.0)),
             (0.5, (0.9, 0.0, 0.0)), (1.0, (0.5, 0.0, 0.0))]
    value = max(-1.0, min(1.0, value))
    for (left, left_color), (right, right_color) in zip(stops, stops[1:]):
        if value <= right:
            ratio = 0.0 if right == left else (value - left) / (right - left)
            return tuple(a + (b - a) * ratio for a, b in zip(left_color, right_color))
    return stops[-1][1]


def render_attribution(smiles, fragments, attributions, path, Chem):
    from rdkit.Chem.Draw import rdMolDraw2D
    from rdkit.Chem import rdDepictor
    mol = Chem.MolFromSmiles(smiles)
    rdDepictor.Compute2DCoords(mol)
    atom_colors = {}
    atom_radii = {}
    for fragment, attribution in zip(fragments, attributions):
        color = [tuple(_color(attribution))]
        for atom in fragment:
            atom_colors[atom] = color
            atom_radii[atom] = 0.4
    drawer = rdMolDraw2D.MolDraw2DCairo(900, 700)
    options = drawer.drawOptions()
    options.useBWAtomPalette()
    options.clearBackground = True
    drawer.DrawMoleculeWithHighlights(mol, '', atom_colors, {}, atom_radii, {})
    drawer.FinishDrawing()
    path.write_bytes(drawer.GetDrawingText())


def _verify_structures(molecules, task, schemes):
    if not isinstance(molecules, list) or not 1 <= len(molecules) <= MAX_MOLECULES:
        return False
    for molecule in molecules:
        if not isinstance(molecule, dict) or not isinstance(molecule.get('smiles'), str):
            return False
        atom_count = molecule.get('atom_count')
        if type(atom_count) is not int or not 1 <= atom_count <= MAX_ATOMS:
            return False
        prediction = molecule.get('prediction')
        if not isinstance(prediction, dict) or not all(
                type(prediction.get(key)) in (int, float) and math.isfinite(prediction[key])
                for key in ('mean', 'std')):
            return False
        if task['kind'] == 'classification':
            label = molecule.get('label')
            probability = molecule.get('probability_class1')
            if (type(label) is not int or label not in (0, 1)
                    or type(probability) not in (int, float) or not 0 <= probability <= 1):
                return False
        result_schemes = molecule.get('schemes')
        if not isinstance(result_schemes, dict) or list(result_schemes) != schemes:
            return False
        for scheme in schemes:
            entry = result_schemes[scheme]
            fragments = entry.get('fragments') if isinstance(entry, dict) else None
            if not isinstance(fragments, list) or not 1 <= len(fragments) <= MAX_FRAGMENTS_PER_SCHEME:
                return False
            if not isinstance(entry.get('image'), str) or not entry['image'].endswith('.png'):
                return False
            for fragment in fragments:
                atoms = fragment.get('atoms')
                if (not isinstance(atoms, list) or not atoms
                        or any(type(atom) is not int or not 0 <= atom < atom_count for atom in atoms)):
                    return False
                if not all(type(fragment.get(key)) in (int, float) and math.isfinite(fragment[key])
                           for key in ('attribution', 'attribution_std', 'attribution_normalized')):
                    return False
                if not -1.0 <= fragment['attribution_normalized'] <= 1.0:
                    return False
    return True


# @spec SME-004 — Verified per-molecule predictions and fragment attributions
def verified_sme(result, request, directory=None):
    if (result.get('verified') is not True or result.get('app_id') != APP_ID
            or result.get('task') not in TASKS):
        return False
    task = result['task']
    if result.get('kind') != TASKS[task]['kind']:
        return False
    seed_count = result.get('seed_count')
    if type(seed_count) is not int or seed_count < 1:
        return False
    schemes = selected_fragmentations(request)
    if result.get('fragmentations') != schemes:
        return False
    molecules = result.get('molecules')
    if not _verify_structures(molecules, TASKS[task], schemes):
        return False
    if [molecule.get('index') for molecule in molecules] != list(range(1, len(molecules) + 1)):
        return False
    if len(molecules) != len(request_smiles(request)):
        return False
    if directory is not None:
        for molecule in molecules:
            for scheme in schemes:
                image = Path(directory) / molecule['schemes'][scheme]['image']
                if image.is_symlink() or not image.is_file():
                    return False
        if not (Path(directory) / 'results.zip').is_file():
            return False
    return True


def write_outputs(result, directory):
    directory = Path(directory)
    (directory / 'images').mkdir(exist_ok=True)
    with (directory / 'predictions.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        header = ['index', 'smiles', 'prediction_mean', 'prediction_std']
        if result['kind'] == 'classification':
            header += ['probability_class1', 'predicted_label']
        writer.writerow(header)
        for molecule in result['molecules']:
            row = [molecule['index'], molecule['smiles'],
                   f"{molecule['prediction']['mean']:.6g}", f"{molecule['prediction']['std']:.6g}"]
            if result['kind'] == 'classification':
                row += [f"{molecule['probability_class1']:.6g}", molecule['label']]
            writer.writerow(row)
    with (directory / 'fragments.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['molecule_index', 'smiles', 'scheme', 'fragment_index', 'fragment_label',
                         'atom_count', 'atoms', 'attribution', 'attribution_std',
                         'attribution_normalized', 'masked_prediction_mean'])
        for molecule in result['molecules']:
            for scheme, entry in molecule['schemes'].items():
                for fragment in entry['fragments']:
                    writer.writerow([molecule['index'], molecule['smiles'], scheme, fragment['index'],
                                     fragment['label'], fragment['atom_count'],
                                     ' '.join(str(atom) for atom in fragment['atoms']),
                                     f"{fragment['attribution']:.6g}", f"{fragment['attribution_std']:.6g}",
                                     f"{fragment['attribution_normalized']:.6g}",
                                     f"{fragment['masked_prediction_mean']:.6g}"])
    (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    with zipfile.ZipFile(directory / 'results.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ('request.json', 'result.json', 'predictions.csv', 'fragments.csv'):
            path = directory / name
            if path.is_file():
                archive.write(path, name)
        for image in sorted(directory.glob('mol_*_*.png')):
            archive.write(image, 'images/' + image.name)


def run_job(request_path, root=ROOT):
    import torch as th
    import numpy as np
    from rdkit import Chem

    request = json.loads(Path(request_path).read_text())
    options = type('Options', (), request)
    validate_sme(options)
    directory = Path.cwd()
    (directory / 'images').mkdir(exist_ok=True)
    manifest, task_entry = load_manifest(Path(root), request['sme_task'])
    task = TASKS[request['sme_task']]
    schemes = selected_fragmentations(options)
    smiles_list = request_smiles(request)
    print(f"SME task {request['sme_task']} ({task['kind']}), {len(smiles_list)} molecule(s), "
          f"{len(task_entry['seeds'])} seed model(s), schemes: {', '.join(schemes)}", flush=True)

    models = []
    for seed in task_entry['seeds']:
        state = th.load(Path(root) / 'models' / seed['file'], map_location='cpu', weights_only=True)
        models.append(_tensor_params(state['model_state_dict'], th))
    th.set_num_threads(max(1, min(int(request.get('cores', 2)), 8)))

    molecules, expected = [], {
        'app_id': APP_ID, 'verified': True, 'task': request['sme_task'],
        'task_label': task['label'], 'kind': task['kind'],
        'fragmentations': schemes, 'seed_count': len(models),
        'model_metrics': task_entry.get('metrics', {}),
        'provenance': {
            'manifest_created_at': manifest.get('created_at'),
            'training_source': manifest.get('source', {}),
            'note': ('Models were retrained from the supplied package data with the documented '
                     'RGCN hyperparameters; predictions are model estimates, and fragment '
                     'attributions are perturbation sensitivities, not causal chemistry.')}}
    for index, smiles in enumerate(smiles_list, 1):
        mol = Chem.MolFromSmiles(smiles)
        if mol is None or '.' in smiles:
            raise ValueError('invalid_sme_input')
        canonical = Chem.MolToSmiles(mol)
        atom_count = mol.GetNumAtoms()
        if not 1 <= atom_count <= MAX_ATOMS:
            raise ValueError('invalid_sme_input')
        graph = _graph_arrays(mol, Chem, th)
        full_mask = th.ones(atom_count)
        full_predictions = []
        for params in models:
            raw = _predict(params, graph, full_mask, th)
            full_predictions.append(1.0 / (1.0 + math.exp(-raw)) if task['kind'] == 'classification' else raw)
        mean_prediction = float(np.mean(full_predictions))
        molecule = {
            'index': index, 'smiles': canonical, 'atom_count': atom_count,
            'prediction': {'mean': mean_prediction, 'std': float(np.std(full_predictions)),
                           'seeds': [float(value) for value in full_predictions]},
            'schemes': {}}
        if task['kind'] == 'classification':
            molecule['probability_class1'] = mean_prediction
            molecule['label'] = int(mean_prediction >= 0.5)
        for scheme in schemes:
            fragments, labels = accumulate_fragments(mol, scheme, Chem)
            if not 1 <= len(fragments) <= MAX_FRAGMENTS_PER_SCHEME:
                raise ValueError('input_too_large')
            rows, vis_fragments, vis_attributions = [], [], []
            for fragment_index, (atoms, label) in enumerate(zip(fragments, labels), 1):
                mask = full_mask.clone()
                mask[atoms] = 0.0
                masked_predictions = []
                for params in models:
                    raw = _predict(params, graph, mask, th)
                    masked_predictions.append(1.0 / (1.0 + math.exp(-raw))
                                              if task['kind'] == 'classification' else raw)
                per_seed = [full - masked for full, masked in zip(full_predictions, masked_predictions)]
                attribution = float(np.mean(per_seed))
                rows.append({
                    'index': fragment_index, 'label': label, 'atoms': atoms,
                    'atom_count': len(atoms), 'attribution': attribution,
                    'attribution_std': float(np.std(per_seed)),
                    'attribution_normalized': math.tanh(attribution),
                    'masked_prediction_mean': float(np.mean(masked_predictions))})
                vis_fragments.append(atoms)
                vis_attributions.append(math.tanh(attribution))
            image_name = f'mol_{index:02d}_{scheme}.png'
            render_attribution(canonical, vis_fragments, vis_attributions, directory / image_name, Chem)
            molecule['schemes'][scheme] = {'fragments': rows, 'image': image_name}
            print(f'[{index}/{len(smiles_list)}] {scheme}: {len(rows)} fragment(s) attributed', flush=True)
        molecules.append(molecule)
    expected['molecules'] = molecules
    if not verified_sme(expected, options):
        raise ValueError('incomplete SME result')
    write_outputs(expected, directory)
    if not verified_sme(expected, options, directory):
        raise ValueError('incomplete SME output files')
    summary = {'task': request['sme_task'], 'molecules': len(molecules),
               'schemes': schemes, 'seed_count': len(models)}
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    print(MARKER, flush=True)


if __name__ == '__main__':
    run_job(sys.argv[1])
