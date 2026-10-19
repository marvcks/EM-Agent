"""Homolytic non-ring single-bond BDEs. Heavy dependencies load only in runners."""
import base64
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import zipfile

ROOT = Path('/opt/em-agent-tools/bde')
MODEL_FILES = {'model.tar.gz': 'f1c2b9436f2d18c76b45d95140e6a08c096250bd5f3e2b412492ca27ab38ad0c',
               'preprocessor.json': '412d15ca4d0e8b5030e9b497f566566922818ff355b8ee677a91dd23696878ac'}
BASIS = '6-311+G(d,p)'


def bde_available(mode=None):
    common = (ROOT / 'manifest.json').is_file()
    ml = os.access(ROOT / '.venv/bin/python', os.X_OK) and all((ROOT / 'models' / name).is_file() for name in [*MODEL_FILES, 'model/saved_model.pb'])
    qm = os.access(ROOT / 'psi4/bin/python', os.X_OK) and (ROOT / 'psi4/lib').is_dir()
    return common and (ml if mode == 'ALFABET' else qm if mode == 'Psi4' else ml and qm)


def validate_bde(request):
    if request.xyz or request.task != 'bde' or request.charge != 0 or request.multiplicity != 1 or request.basis:
        raise ValueError('invalid_bde_input')
    if request.input_kind == 'smiles':
        text = request.smiles.strip()
        if request.compound_name or not text or len(text) > 4096 or any(c.isspace() for c in text) or any(c in text for c in '.;>'):
            raise ValueError('invalid_bde_input')
    elif request.smiles or not request.compound_name.strip() or any(ord(c) < 32 for c in request.compound_name):
        raise ValueError('invalid_bde_input')


def resolve_name(name):
    url = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/' + urllib.parse.quote(name.strip(), safe='') + '/property/SMILES/JSON'
    with urllib.request.urlopen(url, timeout=15) as response:
        data = response.read(65537)
    if len(data) > 65536:
        raise ValueError('Name lookup returned too many matches; use SMILES')
    rows = json.loads(data)['PropertyTable']['Properties']
    if len(rows) != 1:
        raise ValueError('Ambiguous compound name; use explicit SMILES')
    row = rows[0]
    return row.get('SMILES') or row['IsomericSMILES'], {'provider': 'PubChem', 'cid': row['CID'], 'url': url}


def parse_molecule(smiles):
    from rdkit import Chem
    mol = Chem.MolFromSmiles(smiles)
    if mol is None or len(Chem.GetMolFrags(mol)) != 1 or any(a.GetSymbol() not in {'C', 'H', 'N', 'O'} or a.GetFormalCharge() or a.GetNumRadicalElectrons() or a.GetIsotope() for a in mol.GetAtoms()):
        raise ValueError('Only connected, neutral, closed-shell, non-isotopic C/H/N/O molecules are supported')
    if Chem.FindMolChiralCenters(mol, includeUnassigned=True) and any(tag == '?' for _, tag in Chem.FindMolChiralCenters(mol, includeUnassigned=True)):
        raise ValueError('Specify tetrahedral stereochemistry in SMILES')
    # Canonicalize BEFORE indexing; ALFABET featurizes the canonical SMILES.
    mol = Chem.AddHs(Chem.MolFromSmiles(Chem.MolToSmiles(mol)))
    if not 2 <= mol.GetNumAtoms() <= 128:
        raise ValueError('Molecule including hydrogens must contain 2–128 atoms')
    return mol


# @spec BDE-002 — Canonical explicit-H bond homolysis
def enumerate_bonds(mol):
    from rdkit import Chem
    rows, fragments = [], {}
    for bond in mol.GetBonds():
        idx, a, b = bond.GetIdx(), bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        row = {'bond_index': idx, 'atom1': a, 'atom2': b, 'bond_type': f'{mol.GetAtomWithIdx(a).GetSymbol()}-{mol.GetAtomWithIdx(b).GetSymbol()}',
               'status': 'unsupported', 'reason': '', 'bde_kcal_mol': None, 'fragments': []}
        rows.append(row)
        if bond.IsInRing():
            row['reason'] = 'ring_bond'
            continue
        if bond.GetBondType() != Chem.BondType.SINGLE:
            row['reason'] = 'multiple_bond'
            continue
        edit = Chem.RWMol(mol)
        edit.RemoveBond(a, b)
        for index in (a, b):
            atom = edit.GetAtomWithIdx(index)
            atom.SetNoImplicit(True)
            atom.SetNumRadicalElectrons(atom.GetNumRadicalElectrons() + 1)
        Chem.SanitizeMol(edit)
        pair = Chem.GetMolFrags(edit, asMols=True)
        if len(pair) != 2 or any(sum(atom.GetNumRadicalElectrons() for atom in m.GetAtoms()) != 1 for m in pair):
            row['reason'] = 'unsupported_radicals'
            continue
        row.update(status='pending', fragments=[Chem.MolToSmiles(Chem.RemoveHs(m)) for m in pair])
        fragments[idx] = pair
    return rows, fragments


def predict_alfabet(smiles, rows, cores):
    import numpy as np
    import nfp
    import tensorflow as tf
    tf.config.threading.set_intra_op_parallelism_threads(cores)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    # Reuse official featurization unchanged; redirect only its preprocessor file
    # lookup to our hash-verified, preinstalled asset. No network at inference.
    import pooch
    for name, digest in MODEL_FILES.items():
        if hashlib.sha256((ROOT / 'models' / name).read_bytes()).hexdigest() != digest:
            raise ValueError('ALFABET asset checksum mismatch: ' + name)
    sys.path.insert(0, str(ROOT / 'source'))
    original = pooch.retrieve
    def local_retrieve(url, known_hash=None, **kwargs):
        if url.rsplit('/', 1)[-1] != 'preprocessor.json':
            raise ValueError('Unexpected model download')
        return str(ROOT / 'models/preprocessor.json')
    try:
        pooch.retrieve = local_retrieve
        from alfabet.preprocessor import get_features
    finally:
        pooch.retrieve = original
    features = get_features(smiles)
    if np.any(features['atom'] == 1) or np.any(features['bond'] == 1):
        raise ValueError('Molecule has atom/bond environments outside ALFABET vocabulary')
    model = tf.keras.models.load_model(str(ROOT / 'models/model'), custom_objects=nfp.custom_objects, compile=False)
    bdes, _ = model({key: tf.constant(np.expand_dims(value, 0)) for key, value in features.items()}, training=False)
    values = np.asarray(bdes).reshape(-1)
    for row in rows:
        if row['status'] == 'pending':
            value = float(values[row['bond_index']])
            if not math.isfinite(value):
                raise ValueError('Non-finite model prediction')
            row.update(status='ok', bde_kcal_mol=value)


def starting_geometry(mol):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    copy = Chem.Mol(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 20261019
    ids = list(AllChem.EmbedMultipleConfs(copy, numConfs=12, params=params))
    if not ids:
        raise ValueError('3D embedding failed')
    if AllChem.MMFFHasAllMoleculeParams(copy):
        optimized = AllChem.MMFFOptimizeMoleculeConfs(copy, numThreads=1, maxIters=500, mmffVariant='MMFF94s')
        index = min(range(len(ids)), key=lambda i: optimized[i][1])
    else:
        index = 0
    conformer = Chem.Conformer(copy.GetConformer(ids[index]))
    copy.RemoveAllConformers()
    copy.AddConformer(conformer)
    return copy


def export_generated_structures(mol):
    from rdkit import Chem
    parent = starting_geometry(mol)
    Path('parent-initial.xyz').write_text(Chem.MolToXYZBlock(parent))
    _, fragments = enumerate_bonds(parent)
    directory = Path('generated-fragments')
    directory.mkdir(exist_ok=True)
    mapping, cache = {}, {}
    for bond_index, pair in fragments.items():
        names = []
        for fragment in pair:
            key = Chem.MolToSmiles(Chem.RemoveHs(fragment))
            if key not in cache:
                name = f'fragment-{len(cache)}.xyz'
                (directory / name).write_text(Chem.MolToXYZBlock(fragment))
                cache[key] = name
            names.append(cache[key])
        mapping[str(bond_index)] = names
    Path('fragment-structures.json').write_text(json.dumps({'note': 'Generated initial coordinates inherited from the parent, not quantum-optimized structures.', 'bond_to_xyz': mapping}, indent=2))


# @spec BDE-003 — Optimized gas-phase dissociation enthalpies
def psi4_enthalpy(mol, label, request):
    import psi4
    from rdkit import Chem
    from rdkit.Geometry import Point3D
    label_dir = Path('structures') / label
    label_dir.mkdir(parents=True, exist_ok=True)
    psi4.core.clean()
    psi4.core.clean_options()
    psi4.core.set_output_file(str(label_dir / 'psi4.log'), False)
    radical = sum(atom.GetNumRadicalElectrons() for atom in mol.GetAtoms())
    if radical not in (0, 1):
        raise ValueError('Only singlet parents and doublet fragments supported')
    geometry = f'0 {radical + 1}\n'
    conf = mol.GetConformer() if mol.GetNumConformers() else None
    for index, atom in enumerate(mol.GetAtoms()):
        p = conf.GetAtomPosition(index) if conf else Point3D(0, 0, 0)
        geometry += f'{atom.GetSymbol()} {p.x:.12f} {p.y:.12f} {p.z:.12f}\n'
    geometry += 'units angstrom\nsymmetry c1\nno_reorient\nno_com\n'
    (label_dir / 'initial.xyz').write_text(Chem.MolToXYZBlock(mol) if conf else f'1\n{label}\n{mol.GetAtomWithIdx(0).GetSymbol()} 0 0 0\n')
    molecule = psi4.geometry(geometry)
    psi4.set_options({'basis': BASIS, 'reference': 'uhf' if radical else 'rhf', 'scf_type': 'df',
                      'e_convergence': 1e-8, 'd_convergence': 1e-8, 'maxiter': 200,
                      'dft_radial_points': 99, 'dft_spherical_points': 590,
                      'geom_maxiter': 100, 't': 298.15, 'p': 101325.0})
    # Psi4 does not support stability root-following for UKS/DFT.
    # Record and check <S^2> below rather than claiming that analysis ran.
    print(f'Psi4 {label}: {mol.GetNumAtoms()} atoms, multiplicity={radical + 1}', flush=True)
    def spin_expectation(wfn):
        import numpy as np
        ca = np.asarray(wfn.Ca_subset('AO', 'OCC'))
        cb = np.asarray(wfn.Cb_subset('AO', 'OCC'))
        sz = 0.5 * (wfn.nalpha() - wfn.nbeta())
        return float(sz * (sz + 1) + wfn.nbeta() - np.sum((ca.T @ np.asarray(wfn.S()) @ cb) ** 2))

    if mol.GetNumAtoms() == 1:
        energy, wavefunction = psi4.energy('m06-2x', molecule=molecule, return_wfn=True)
        spin_squared = spin_expectation(wavefunction)
        enthalpy = float(energy) + 2.5 * 3.166811563e-6 * 298.15
    else:
        _, wavefunction = psi4.optimize('m06-2x', molecule=molecule, return_wfn=True)
        spin_squared = spin_expectation(wavefunction)
        _, wavefunction = psi4.frequency('m06-2x', molecule=molecule, return_wfn=True, ref_wfn=wavefunction)
        omega = wavefunction.frequency_analysis['omega'].data
        if any(abs(complex(value).imag) > 20 for value in omega):
            raise ValueError(f'{label} has imaginary vibrational frequencies')
        enthalpy = float(psi4.variable('ENTHALPY'))
        (label_dir / 'frequencies_cm-1.json').write_text(json.dumps([{'real': float(complex(v).real), 'imag': float(complex(v).imag)} for v in omega]))
    # Check every expected bond, and reject newly formed connections as well.
    import numpy as np
    coords = np.asarray(molecule.geometry()) * psi4.constants.bohr2angstroms
    periodic = Chem.GetPeriodicTable()
    for i in range(mol.GetNumAtoms()):
        for j in range(i):
            distance = float(np.linalg.norm(coords[i] - coords[j]))
            radii = periodic.GetRcovalent(mol.GetAtomWithIdx(i).GetAtomicNum()) + periodic.GetRcovalent(mol.GetAtomWithIdx(j).GetAtomicNum())
            expected = mol.GetBondBetweenAtoms(i, j) is not None
            if expected and distance > radii + 0.4 or not expected and distance < radii + 0.2:
                raise ValueError(f'{label} changed molecular connectivity during optimization')
    optimized = Chem.Mol(mol)
    c = Chem.Conformer(mol.GetNumAtoms())
    for i, xyz in enumerate(coords):
        c.SetAtomPosition(i, xyz.tolist())
    optimized.RemoveAllConformers()
    optimized.AddConformer(c)
    (label_dir / 'optimized.xyz').write_text(Chem.MolToXYZBlock(optimized))
    if abs(spin_squared - (0.75 if radical else 0.0)) > 0.3:
        raise ValueError(f'{label} has excessive spin contamination: {spin_squared}')
    record = {'spin_squared': spin_squared, 'enthalpy_hartree': enthalpy, 'electronic_energy_hartree': float(wavefunction.energy()),
              'multiplicity': radical + 1, 'smiles': Chem.MolToSmiles(Chem.RemoveHs(mol))}
    (label_dir / 'thermochemistry.json').write_text(json.dumps(record, indent=2))
    if not math.isfinite(enthalpy):
        raise ValueError('Non-finite enthalpy')
    return enthalpy


def calculate_psi4(mol, rows, request):
    import psi4
    from rdkit import Chem
    scratch = Path(os.environ.get('TMPDIR', str(Path('scratch').resolve())))
    scratch.mkdir(parents=True, exist_ok=True)
    psi4.core.IOManager.shared_object().set_default_path(str(scratch.resolve()))
    psi4.set_num_threads(request['cores'])
    psi4.set_memory(f"{request['memory_mb']} MB")
    parent = starting_geometry(mol)
    # Fragment parent coordinates so initial radicals inherit the broken geometry.
    _, fragments = enumerate_bonds(parent)
    cache = {}
    parent_h = psi4_enthalpy(parent, 'parent', request)
    for row in rows:
        if row['status'] != 'pending':
            continue
        hs = []
        for fragment in fragments[row['bond_index']]:
            key = Chem.MolToSmiles(Chem.RemoveHs(fragment))
            if key not in cache:
                cache[key] = psi4_enthalpy(fragment, f'fragment-{len(cache)}', request)
            hs.append(cache[key])
        row.update(status='ok', bde_kcal_mol=(sum(hs) - parent_h) * psi4.constants.hartree2kcalmol)
        Path('progress.json').write_text(json.dumps({'bonds': rows}, indent=2))
    return {'parent_enthalpy_hartree': parent_h, 'unique_fragment_count': len(cache), 'temperature_kelvin': 298.15,
            'pressure_pascal': 101325, 'method': 'M06-2X/' + BASIS,
            'conformer_protocol': 'Lowest MMFF94s of 12 ETKDG parent conformers; radical starts inherit parent coordinates; independent DFT relaxation; no exhaustive conformer search.'}


def verified_bde(result):
    if result.get('verified') is not True or result.get('mode') not in {'ALFABET', 'Psi4'} or result.get('unit') != 'kcal/mol' or not result.get('canonical_smiles'):
        return False
    rows = result.get('bonds')
    if not isinstance(rows, list) or not rows or len(rows) > 512 or not all(isinstance(r, dict) and r.get('status') in {'ok', 'unsupported'} and type(r.get('bond_index')) is int for r in rows):
        return False
    indices = [r['bond_index'] for r in rows]
    if len(set(indices)) != len(indices):
        return False
    valid = [r for r in rows if r['status'] == 'ok']
    if not valid or any(type(r.get('bde_kcal_mol')) not in (float, int) or not math.isfinite(r['bde_kcal_mol']) for r in valid):
        return False
    minimum = min(valid, key=lambda r: r['bde_kcal_mol'])
    return result.get('minimum_bond_index') == minimum['bond_index'] and result.get('minimum_bde_kcal_mol') == minimum['bde_kcal_mol']


def write_outputs(mol, result):
    from rdkit.Chem import AllChem, rdMolDescriptors
    from rdkit.Chem.Draw import rdMolDraw2D
    AllChem.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DCairo(1100, 800)
    drawer.drawOptions().addAtomIndices = True
    for bond, row in zip(mol.GetBonds(), result['bonds']):
        bond.SetProp('bondNote', f"B{row['bond_index']}: " + (f"{row['bde_kcal_mol']:.1f}" if row['status'] == 'ok' else 'N/A'))
    drawer.DrawMolecule(mol, highlightAtoms=[], highlightBonds=[result['minimum_bond_index']])
    drawer.FinishDrawing()
    png = drawer.GetDrawingText()
    Path('molecule.png').write_bytes(png)
    result['diagram_png_base64'] = base64.b64encode(png).decode()
    result['formula'] = rdMolDescriptors.CalcMolFormula(mol)
    Path('result.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    with Path('bonds.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['bond_index', 'atom1', 'atom2', 'bond_type', 'status', 'reason', 'bde_kcal_mol', 'fragments'])
        writer.writeheader()
        writer.writerows(result['bonds'])


def archive_outputs():
    top_level = {'request.json', 'molecule.smi', 'parent-initial.xyz', 'fragment-structures.json',
                 'result.json', 'molecule.png', 'bonds.csv', 'progress.json'}
    with zipfile.ZipFile('results.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in Path('.').rglob('*'):
            parts = path.parts
            if not path.is_file() or path.is_symlink():
                continue
            if (len(parts) == 1 and path.name in top_level) or parts[0] in {'structures', 'generated-fragments'}:
                archive.write(path)


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    if hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:request['cores']])
    from rdkit import Chem
    smiles, resolution = (resolve_name(request['compound_name']) if request['input_kind'] == 'name' else (request['smiles'].strip(), None))
    mol = parse_molecule(smiles)
    canonical = Chem.MolToSmiles(Chem.RemoveHs(mol))
    rows, fragments = enumerate_bonds(mol)
    if not fragments:
        raise ValueError('No supported non-ring single bonds')
    export_generated_structures(mol)
    Path('molecule.smi').write_text(canonical + '\n')
    metadata = {}
    if request['method'] == 'Psi4':
        metadata = calculate_psi4(mol, rows, request)
    else:
        predict_alfabet(canonical, rows, request['cores'])
    valid = [row for row in rows if row['status'] == 'ok']
    minimum = min(valid, key=lambda row: row['bde_kcal_mol'])
    result = {'verified': True, 'mode': request['method'], 'unit': 'kcal/mol', 'canonical_smiles': canonical,
              'name_resolution': resolution, 'bonds': rows, 'minimum_bond_index': minimum['bond_index'],
              'minimum_bde_kcal_mol': minimum['bde_kcal_mol'], 'calculation': metadata,
              'provenance': json.loads((ROOT / 'manifest.json').read_text()),
              'scope': 'Neutral closed-shell CHNO; non-ring single-bond homolysis. Minimum over supported bonds only. ALFABET v0.1.1 TF2 weights are an updated model, not the exact 2020 weights. Psi4 values use a different basis and are not a reproduction of the paper.'}
    if not verified_bde(result):
        raise ValueError('Incomplete BDE result')
    write_outputs(mol, result)
    archive_outputs()
    print(f"Minimum supported BDE: bond {minimum['bond_index']}, {minimum['bde_kcal_mol']:.4f} kcal/mol", flush=True)
    print('EM_AGENT_BDE_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
