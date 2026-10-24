"""CPU single-step EditRetro adapter. Catalog imports use only the stdlib."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace
import zipfile

ROOT = Path('/opt/em-agent-tools/editretro')
MODEL_SHA256 = '3a537dc6a8992dd61c02993485d8f89c83a7169e63ccb956dab88b949327daf8'
UPSTREAM_COMMIT = '8e5848e899b4e8ec6be970b9be04881042ed7b55'


def editretro_available(root=ROOT):
    files = ('manifest.json', 'checkpoint_best.pt', 'source/interactive/databin/dict.src.txt',
             'source/interactive/databin/dict.tgt.txt', 'source/preprocess/SPE_ChEMBL.txt')
    return (os.access(root / '.venv/bin/python', os.X_OK)
            and os.access(root / '.venv/bin/fairseq-interactive', os.X_OK)
            and all((root / name).is_file() and (root / name).stat().st_size > 0 for name in files))


# @spec ER-002 — Bounded single-product input; inference stays outside the service Python.
def validate_editretro(request):
    if (request.task != 'retrosynthesis' or request.method not in ('', '2D') or request.basis
            or request.xyz or request.charge or request.multiplicity != 1
            or request.compound_name or request.input_kind != 'smiles'
            or request.document_name or request.table_csv):
        raise ValueError('invalid_reaction_input')
    if not re.fullmatch(r'[A-Za-z0-9@+\[\]()=#%/\\*\-]{1,2048}', request.smiles.strip()):
        raise ValueError('invalid_smiles')


def verified_editretro(result, request):
    candidates = result.get('candidates')
    if (result.get('verified') is not True or result.get('app_id') != 'editretro'
            or result.get('device') != 'cpu' or result.get('model_sha256') != MODEL_SHA256
            or result.get('input_smiles') != request.smiles.strip()
            or result.get('top_k') != request.top_k or result.get('augmentations') != request.augmentations
            or not isinstance(candidates, list) or not 1 <= len(candidates) <= request.top_k
            or type(result.get('prediction_count')) is not int
            or result['prediction_count'] != len(candidates)):
        return False
    seen = set()
    for rank, row in enumerate(candidates, 1):
        if (not isinstance(row, dict) or type(row.get('rank')) is not int or row['rank'] != rank
                or not isinstance(row.get('smiles'), str) or not row['smiles']
                or row['smiles'] in seen or row.get('reactants') != row['smiles'].split('.')
                or any(not fragment for fragment in row['reactants'])):
            return False
        seen.add(row['smiles'])
    return True


def verify_assets():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    if (manifest.get('upstream_commit') != UPSTREAM_COMMIT or manifest.get('model_sha256') != MODEL_SHA256
            or manifest.get('device') != 'cpu' or manifest.get('strict_load', {}).get('missing_keys') != []
            or manifest.get('strict_load', {}).get('unexpected_keys') != []):
        raise ValueError('Unverified EditRetro runtime')
    files = manifest['files']
    if files.get('checkpoint_best.pt') != MODEL_SHA256:
        raise ValueError('Checkpoint identity differs from the accepted user model')
    for required in ('checkpoint_best.pt', 'uv.lock', 'source/editretro/models/editretro_nat.py',
                     'source/interactive/databin/dict.src.txt', 'source/interactive/databin/dict.tgt.txt',
                     'source/preprocess/SPE_ChEMBL.txt'):
        if required not in files:
            raise ValueError('Missing asset identity: ' + required)
    for name, expected in files.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Invalid manifest path')
        checksum = hashlib.sha256()
        with (ROOT / name).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                checksum.update(block)
        if checksum.hexdigest() != expected:
            raise ValueError('EditRetro asset hash mismatch: ' + name)
    return manifest


# @spec ER-001 — Upstream decoding on CPU with the unchanged user-supplied checkpoint.
def main():
    request_path = Path(sys.argv[1]).resolve()
    request = json.loads(request_path.read_text())
    options = SimpleNamespace(**request)
    validate_editretro(options)
    if (type(options.cores) is not int or not 1 <= options.cores <= 8
            or type(options.top_k) is not int or not 1 <= options.top_k <= 20
            or type(options.augmentations) is not int or not 1 <= options.augmentations <= 20):
        raise ValueError('Invalid EditRetro resource or decoding parameters')
    if hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:options.cores])
    os.environ.update({name: str(options.cores) for name in
                       ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')})
    os.environ.update(CUDA_VISIBLE_DEVICES='', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    os.environ.pop('PYTHONPATH', None)
    from rdkit import Chem
    molecule = Chem.MolFromSmiles(options.smiles.strip())
    if (molecule is None or molecule.GetNumAtoms() == 0 or len(Chem.GetMolFrags(molecule)) != 1
            or any(atom.GetAtomicNum() == 0 for atom in molecule.GetAtoms())
            or Chem.AddHs(molecule).GetNumAtoms() > 128):
        raise ValueError('A valid connected product with at most 128 atoms including hydrogens is required')
    print('Checking checkpoint, source, tokenizer and vocabulary identities', flush=True)
    manifest = verify_assets()
    directory = Path.cwd()
    (directory / 'input.smi').write_text(options.smiles.strip() + '\n')
    source = ROOT / 'source'
    command = [str(ROOT / '.venv/bin/fairseq-interactive'), '--user-dir', str(source / 'editretro'),
               str(source / 'interactive/databin'), '-s', 'src', '-t', 'tgt', '--input', str(directory / 'input.smi'),
               '--task', 'translation_retro', '--path', str(ROOT / 'checkpoint_best.pt'), '--cpu',
               '--iter-decode-max-iter', '10', '--iter-decode-eos-penalty', '0', '--beam', '1', '--remove-bpe',
               '--init-src', '--buffer-size', '20', '--batch-size', '20', '--TOPK', '20',
               '--inference-with-augmentation', '--aug', str(options.augmentations),
               '--repos-beam', '5', '--mask-beam', '1', '--token-beam', '4', '--print-step',
               '--retain-iter-history', '--num-workers', '0', '--seed', '1']
    started = time.monotonic()
    print(f'Running single-step EditRetro on CPU: {options.augmentations} augmentations, {options.cores} cores', flush=True)
    with (directory / 'generation.txt').open('w') as output:
        subprocess.run(command, cwd=source, stdout=output, stderr=subprocess.STDOUT, check=True)
    print('Ranking and validating candidate reactant SMILES', flush=True)
    subprocess.run([str(ROOT / '.venv/bin/python'), str(source / 'utils/get_ranked_topk.py'),
                    '-output_file', str(directory / 'generation.txt'), '-save_file', str(directory / 'ranked_preds.txt'),
                    '-augmentation', str(options.augmentations), '-beam_size', '20',
                    '-n_best', str(options.top_k), '-score_alpha', '0.1', '-process_number', str(options.cores)],
                   cwd=source, check=True)
    candidates, seen = [], set()
    for line in (directory / 'ranked_preds.txt').read_text().splitlines():
        if not line.strip():
            continue
        mol = Chem.MolFromSmiles(line)
        if mol is None or any(atom.GetAtomicNum() == 0 for atom in mol.GetAtoms()):
            raise ValueError('Upstream ranking returned an invalid candidate')
        smiles = Chem.MolToSmiles(mol, isomericSmiles=True)
        if smiles not in seen:
            candidates.append({'rank': len(candidates) + 1, 'smiles': smiles, 'reactants': smiles.split('.')})
            seen.add(smiles)
    result = {'app_id': 'editretro', 'verified': True, 'device': 'cpu', 'model_sha256': MODEL_SHA256,
              'input_smiles': options.smiles.strip(), 'canonical_product': Chem.MolToSmiles(molecule),
              'top_k': options.top_k, 'augmentations': options.augmentations, 'seed': 1,
              'prediction_count': len(candidates), 'candidates': candidates,
              'elapsed_seconds': time.monotonic() - started,
              'provenance': {key: value for key, value in manifest.items() if key != 'files'},
              'note': 'Ranked single-step model predictions; ranking is not a calibrated probability or experimental validation. Multi-step routes and stock availability are outside this calculation.'}
    if not verified_editretro(result, options):
        raise ValueError('Incomplete EditRetro result')
    (directory / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    with (directory / 'candidates.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['rank', 'smiles'])
        writer.writeheader()
        writer.writerows({'rank': row['rank'], 'smiles': row['smiles']} for row in candidates)
    with zipfile.ZipFile(directory / 'results.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ('request.json', 'input.smi', 'result.json', 'candidates.csv', 'ranked_preds.txt', 'generation.txt'):
            archive.write(directory / name, name)
    print(json.dumps({'prediction_count': len(candidates), 'elapsed_seconds': result['elapsed_seconds']}), flush=True)
    print('EM_AGENT_EDITRETRO_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
