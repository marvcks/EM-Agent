"""ChemTSv3 Pareto molecular-generation adapter. Catalog imports use only the stdlib."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import zipfile

ROOT = Path('/opt/em-agent-tools/molgen')
APP = ROOT / 'app'
VENV = ROOT / '.venv'
APP_ID = 'molgen'
MARKER = 'EM_AGENT_MOLGEN_COMPLETE'
MODEL_NAMES = ('BDE_v2.ckpt', 'Density_v2.ckpt', 'DetoD_v2.ckpt', 'DetoP_v2.ckpt',
               'DetoQ_v2.ckpt', 'DetoT_v2.ckpt', 'DetoV_v2.ckpt', 'HOFs_v2.ckpt', 'Td.pt')
RNN_FILES = ('model.pt', 'language.lang', 'config.json', 'config.yaml')
MERGE_INTERVAL_SECONDS = 300
MAX_GLOBAL_POOL = 30000
PLOT_GRACE_SECONDS = 240


def molgen_available(root=ROOT):
    app = root / 'app'
    return (os.access(root / '.venv/bin/python', os.X_OK)
            and os.access(root / '.venv/bin/chemtsv3', os.X_OK)
            and (root / 'manifest.json').is_file()
            and (app / 'config/setting.yaml').is_file()
            and all((app / 'models/rnn/best' / name).is_file() for name in RNN_FILES)
            and all((app / 'core/chemprop_model' / name).is_file() for name in MODEL_NAMES)
            and (app / 'data_pool/reference_pool/initial_reference_pool.csv').is_file())


# @spec MG-002 — Bounded generation parameters; no molecular structure, shell or native config input.
def validate_molgen(request):
    if (request.task != 'generation' or request.method not in ('', 'ChemTSv3')
            or request.basis or request.xyz or request.smiles or request.charge
            or request.multiplicity != 1 or request.compound_name
            or request.input_kind != 'smiles' or request.document_name
            or request.table_csv or request.input_mode != 'single'):
        raise ValueError('invalid_molgen_input')
    for value in (request.molgen_workers, request.molgen_seconds, request.molgen_seed,
                  request.cores, request.memory_mb):
        if type(value) is not int:
            raise ValueError('invalid_molgen_input')
    if not 1 <= request.molgen_workers <= 7:
        raise ValueError('invalid_molgen_input')
    if not 60 <= request.molgen_seconds <= 7200:
        raise ValueError('invalid_molgen_input')
    if not 0 <= request.molgen_seed <= 2147483647:
        raise ValueError('invalid_molgen_input')
    if not 2 <= request.cores <= 8 or request.cores < request.molgen_workers + 1:
        raise ValueError('invalid_molgen_input')
    if not 1024 <= request.memory_mb <= 8192:
        raise ValueError('invalid_molgen_input')


def verified_molgen(result, request):
    if (result.get('verified') is not True or result.get('app_id') != APP_ID
            or result.get('workers') != request.molgen_workers
            or result.get('generation_seconds') != request.molgen_seconds
            or result.get('seed') != request.molgen_seed):
        return False
    for key in ('generated_records', 'unique_generated', 'pool_rows', 'generated_pool_rows'):
        if type(result.get(key)) is not int or result[key] < 0:
            return False
    if result['generated_records'] < 1 or result['unique_generated'] < 1 or result['generated_pool_rows'] < 1:
        return False
    best = result.get('best_reward')
    if type(best) not in (int, float) or best != best or best in (float('inf'), float('-inf')):
        return False
    workers = result.get('worker_results')
    if not isinstance(workers, list) or len(workers) != request.molgen_workers:
        return False
    seen = set()
    for row in workers:
        if (not isinstance(row, dict) or not isinstance(row.get('run_id'), str)
                or row['run_id'] in seen or row.get('exit_code') != 0
                or row.get('done') is not True or type(row.get('records')) is not int
                or row['records'] < 0):
            return False
        seen.add(row['run_id'])
    top = result.get('top_molecules')
    if not isinstance(top, list) or not 1 <= len(top) <= 10:
        return False
    for row in top:
        if (not isinstance(row, dict) or not isinstance(row.get('smiles'), str) or not row['smiles']
                or type(row.get('reward')) not in (int, float) or row['reward'] != row['reward']):
            return False
    return True


def sha256_file(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def verify_assets():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    if manifest.get('app_id') != APP_ID or not manifest.get('upstream', {}).get('package_sha256'):
        raise ValueError('Unverified molecular-generation runtime')
    files = manifest.get('app_files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Missing application file manifest')
    for name, expected in files.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Invalid manifest path')
        if sha256_file(APP / name) != expected:
            raise ValueError('Application asset hash mismatch: ' + name)
    return manifest


def replace_scalar(text, key, value):
    pattern = re.compile(rf'^{re.escape(key)}:.*$', re.MULTILINE)
    replacement = f'{key}: {value}'
    if not pattern.search(text):
        return text + '\n' + replacement + '\n'
    return pattern.sub(replacement, text)


def normalize_smiles(smiles):
    try:
        from rdkit import Chem
        molecule = Chem.MolFromSmiles(smiles)
        return Chem.MolToSmiles(molecule) if molecule is not None else smiles
    except Exception:
        return smiles


def read_records(path):
    rows = []
    try:
        with path.open(newline='') as stream:
            for row in csv.DictReader(stream):
                if None not in row:
                    rows.append(row)
    except (OSError, csv.Error):
        pass
    return rows


def numeric(row, key):
    try:
        value = float(row.get(key, ''))
        return value if value == value and abs(value) != float('inf') else None
    except (TypeError, ValueError):
        return None


def result_csvs(result_root):
    return [path for path in sorted(result_root.glob('run_*/*/*.csv'))
            if path.parent.name != 'pending']


def collect_worker_results(result_root):
    workers = []
    records = []
    for run_dir in sorted(result_root.glob('run_*')):
        csv_paths = [path for path in sorted(run_dir.glob('*/*.csv'))
                     if path.parent.name != 'pending']
        run_records = [row for path in csv_paths for row in read_records(path)]
        records.extend(run_records)
        rewards = [numeric(row, 'reward') for row in run_records]
        rewards = [value for value in rewards if value is not None]
        exit_file = run_dir / 'exit_code.txt'
        exit_code = int(exit_file.read_text().strip()) if exit_file.is_file() else None
        workers.append({'run_id': run_dir.name, 'exit_code': exit_code,
                        'done': (run_dir / 'DONE').is_file() and exit_code == 0,
                        'records': len(run_records),
                        'best_reward': max(rewards) if rewards else None})
    return workers, records


def top_molecules(records, limit=10):
    ranked = []
    for row in records:
        reward = numeric(row, 'reward')
        smiles = (row.get('key') or '').strip()
        if reward is None or not smiles:
            continue
        ranked.append((reward, smiles, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    top, seen = [], set()
    for reward, smiles, row in ranked:
        canonical = normalize_smiles(smiles)
        if canonical in seen:
            continue
        seen.add(canonical)
        top.append({'smiles': canonical, 'reward': reward,
                    'density': numeric(row, 'density'), 'BDE': numeric(row, 'BDE'),
                    'Td': numeric(row, 'Td'), 'detoD': numeric(row, 'detoD'),
                    'sa_score': numeric(row, 'sa_score'),
                    'heavy_atom_count': numeric(row, 'heavy_atom_count')})
        if len(top) == limit:
            break
    return top


def pool_stats(shared_pool):
    rows = read_records(shared_pool) if shared_pool.is_file() else []
    generated = [row for row in rows if row.get('source_type') == 'run_generated']
    rewards = [numeric(row, 'pareto_reward') for row in generated]
    rewards = [value for value in rewards if value is not None]
    return {'pool_rows': len(rows), 'generated_pool_rows': len(generated),
            'best_pool_reward': max(rewards) if rewards else None}


def build_zip(directory, work):
    with zipfile.ZipFile(directory / 'results.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ('request.json', 'result.json', 'molecules.csv', 'top_molecules.csv'):
            path = directory / name
            if path.is_file():
                archive.write(path, name)
        for path in sorted(work.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.write(path, 'work/' + path.relative_to(work).as_posix())


# @spec MG-001 — Multi-worker ChemTSv3 search shares one /api/science job directory.
def main():
    request_path = Path(sys.argv[1]).resolve()
    request = json.loads(request_path.read_text())
    options = type('Options', (), request)
    validate_molgen(options)
    print('Checking molecular-generation source, models and runtime identities', flush=True)
    manifest = verify_assets()
    directory = Path.cwd().resolve()
    work = directory / 'work'
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(APP, work)
    result_root = work / 'result/job'
    config_root = work / 'config/job'
    pool_root = work / 'data_pool/job'
    result_root.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)
    pool_root.mkdir(parents=True, exist_ok=True)
    (pool_root / 'pool_snapshots').mkdir(exist_ok=True)
    shared_pool = pool_root / 'shared_pool.csv'
    shutil.copyfile(work / 'data_pool/reference_pool/initial_reference_pool.csv', shared_pool)
    template = (work / 'config/setting.yaml').read_text()
    workers, configs = options.molgen_workers, []
    for index in range(workers):
        run_id = f'run_{index:02d}'
        output_dir = f'result/job/{run_id}'
        config = template
        config = replace_scalar(config, 'seed', options.molgen_seed + index)
        config = replace_scalar(config, 'output_dir', output_dir)
        config = replace_scalar(config, 'time_limit', options.molgen_seconds)
        (result_root / run_id / 'pending').mkdir(parents=True, exist_ok=True)
        config_path = config_root / f'config_{index:02d}.yaml'
        config_path.write_text(config)
        configs.append(config_path)
    environment = {**os.environ, 'PYTHONPATH': f'{work / "engine/ChemTSv3"}:{work}',
                   'PYTHONDONTWRITEBYTECODE': '1', 'CUDA_VISIBLE_DEVICES': '',
                   'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
                   'OPENBLAS_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1'}
    python = str(VENV / 'bin/python')
    merge_log = (pool_root / 'merge.log').open('wb')
    merge = subprocess.Popen([python, '-u', 'core/merge_pareto_pool.py',
                              '--shared_pool', str(shared_pool),
                              '--snapshot_dir', str(pool_root / 'pool_snapshots'),
                              '--job_root', str(result_root),
                              '--max_global_pool', str(MAX_GLOBAL_POOL),
                              '--merge_interval', str(MERGE_INTERVAL_SECONDS)],
                             cwd=work, env=environment, stdout=merge_log, stderr=subprocess.STDOUT)
    processes = []
    for index, config_path in enumerate(configs):
        run_id = f'run_{index:02d}'
        pending = result_root / run_id / 'pending' / f'pending_{index:02d}.csv'
        child_environment = {**environment, 'PARETO_SHARED_POOL': str(shared_pool),
                             'PARETO_PENDING_CSV': str(pending), 'PARETO_RUN_ID': run_id}
        log = (result_root / run_id / 'launch.log').open('wb')
        process = subprocess.Popen([str(VENV / 'bin/chemtsv3'), '-c', str(config_path)],
                                   cwd=work, env=child_environment, stdout=log, stderr=subprocess.STDOUT)
        processes.append((run_id, process, log))
    started = time.monotonic()
    deadline = started + options.molgen_seconds + PLOT_GRACE_SECONDS
    print(f'Started {workers} ChemTSv3 workers with a {options.molgen_seconds}s generation budget', flush=True)
    try:
        last_report = 0
        while any(process.poll() is None for _, process, _ in processes):
            elapsed = time.monotonic() - started
            if elapsed > deadline:
                print('Wall-clock deadline reached; stopping remaining workers', flush=True)
                break
            if elapsed - last_report >= 30:
                last_report = elapsed
                count = sum(len(read_records(path)) for path in result_csvs(result_root))
                print(f'[{int(elapsed)}s] evaluated records: {count}', flush=True)
            time.sleep(2)
        for run_id, process, log in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
            code = process.wait()
            (result_root / run_id / 'exit_code.txt').write_text(str(code) + '\n')
            (result_root / run_id / ('DONE' if code == 0 else 'FAILED')).touch()
            log.close()
    finally:
        for _, process, log in processes:
            if process.poll() is None:
                process.kill()
            if not log.closed:
                log.close()
        if merge.poll() is None:
            merge.terminate()
            try:
                merge.wait(timeout=30)
            except subprocess.TimeoutExpired:
                merge.kill()
                merge.wait()
    print('Running final Pareto pool merge', flush=True)
    subprocess.run([python, 'core/merge_pareto_pool.py',
                    '--shared_pool', str(shared_pool),
                    '--snapshot_dir', str(pool_root / 'pool_snapshots'),
                    '--job_root', str(result_root),
                    '--max_global_pool', str(MAX_GLOBAL_POOL),
                    '--merge_interval', '0'],
                   cwd=work, env=environment, stdout=merge_log, stderr=subprocess.STDOUT,
                   check=False)
    merge_log.close()
    worker_results, records = collect_worker_results(result_root)
    stats = pool_stats(shared_pool)
    top = top_molecules(records)
    rewards = [row['best_reward'] for row in worker_results if row['best_reward'] is not None]
    shutil.copyfile(shared_pool, directory / 'molecules.csv')
    result = {'app_id': APP_ID, 'verified': True, 'workers': workers,
              'generation_seconds': options.molgen_seconds, 'seed': options.molgen_seed,
              'generated_records': len(records),
              'unique_generated': len({row.get('key') for row in records if row.get('key')}),
              'pool_rows': stats['pool_rows'], 'generated_pool_rows': stats['generated_pool_rows'],
              'best_reward': max(rewards) if rewards else None,
              'best_pool_reward': stats['best_pool_reward'],
              'worker_results': worker_results, 'top_molecules': top,
              'elapsed_seconds': time.monotonic() - started,
              'runtime': {'python': manifest.get('python'), 'torch': manifest.get('versions', {}).get('torch'),
                          'chemprop': manifest.get('versions', {}).get('chemprop'),
                          'rdkit': manifest.get('versions', {}).get('rdkit'),
                          'package_sha256': manifest['upstream']['package_sha256'],
                          'app_sha256': manifest.get('app_sha256')},
              'provenance': manifest.get('upstream', {}),
              'note': ('Properties are predictions from the nine bundled ChemProp models; '
                       'generation is stochastic and finite-budget. Ranking is not an experimental '
                       'or synthetic-accessibility validation.')}
    (directory / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    with (directory / 'top_molecules.csv').open('w', newline='') as stream:
        fields = ['smiles', 'reward', 'density', 'BDE', 'Td', 'detoD', 'sa_score', 'heavy_atom_count']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(top)
    build_zip(directory, work)
    if not verified_molgen(result, options):
        raise ValueError('Incomplete molecular-generation result')
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({'generated_records': len(records), 'unique_generated': result['unique_generated'],
                      'generated_pool_rows': result['generated_pool_rows'],
                      'elapsed_seconds': result['elapsed_seconds']}), flush=True)
    print(MARKER, flush=True)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    main()
