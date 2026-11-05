#!/usr/bin/env python3
"""Train the SME RGCN property models from the supplied package datasets.

The packaged checkpoints could not reproduce the package's own reported test
metrics with the documented architecture, so this script retrains every task
from the shipped CSV splits with the documented hyperparameters and writes a
new, checksummed manifest. Run it on the server that hosts the science tools:

    PYTHONPATH=/opt/openhands/source python3 sme_train.py --data-dir ... \
        --models-dir /opt/em-agent-tools/sme/models \
        --manifest /opt/em-agent-tools/sme/manifest.json --workers 8

Only the documented hyperparameters and the package's train/valid/test split
are used; no data augmentation or external data is introduced.
"""
import argparse
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np
import torch as th

from tools.science_apps.sme_runner import TASKS, _graph_arrays, _predict, _tensor_params

PACKAGE = '资料1031/可解释模型_1030'
# @spec SME-001 — Documented per-task hyperparameters; ESOL's pickle was not shipped
HYPERPARAMETERS = {
    'Density_R': {'hidden': [64, 64, 64], 'ffn': 128, 'rgcn_dropout': 0.2, 'ffn_dropout': 0.4,
                  'lr': 0.003, 'batch_size': 100, 'epochs': 600, 'patience': 30},
    'DV_R': {'hidden': [64, 64], 'ffn': 64, 'rgcn_dropout': 0.3, 'ffn_dropout': 0.1,
             'lr': 0.003, 'batch_size': 256, 'epochs': 1000, 'patience': 60},
    'DV_C': {'hidden': [64, 64], 'ffn': 128, 'rgcn_dropout': 0.5, 'ffn_dropout': 0.5,
             'lr': 0.003, 'batch_size': 50, 'epochs': 600, 'patience': 30},
    'IS_R': {'hidden': [64, 64, 64], 'ffn': 128, 'rgcn_dropout': 0.4, 'ffn_dropout': 0.4,
             'lr': 0.0003, 'batch_size': 100, 'epochs': 600, 'patience': 30},
    'IS_C': {'hidden': [64, 64, 64], 'ffn': 128, 'rgcn_dropout': 0.0, 'ffn_dropout': 0.3,
             'lr': 0.0003, 'batch_size': 100, 'epochs': 600, 'patience': 30},
    'MP': {'hidden': [256, 256, 256], 'ffn': 128, 'rgcn_dropout': 0.3, 'ffn_dropout': 0.1,
           'lr': 0.003, 'batch_size': 1024, 'epochs': 600, 'patience': 30},
    # The package did not ship hyperparameter_ESOL.pkl; architecture is inferred
    # from the ESOL checkpoints and the training schedule follows the other
    # regression tasks. Recorded here so the provenance stays explicit.
    'ESOL': {'hidden': [128, 128], 'ffn': 128, 'rgcn_dropout': 0.2, 'ffn_dropout': 0.2,
             'lr': 0.001, 'batch_size': 128, 'epochs': 600, 'patience': 30,
             'inferred': True},
}


def _layer(cin, cout):
    layer = th.nn.Module()
    layer.W = th.nn.Parameter(th.empty(65, cin, cout))
    layer.coeff = th.nn.Parameter(th.empty(65, 65))
    th.nn.init.uniform_(layer.W, -1 / math.sqrt(cin), 1 / math.sqrt(cin))
    th.nn.init.xavier_uniform_(layer.coeff, gain=th.nn.init.calculate_gain('relu'))
    layer.h_bias = th.nn.Parameter(th.zeros(cout))
    layer.loop = th.nn.Parameter(th.empty(cin, cout))
    th.nn.init.xavier_uniform_(layer.loop)
    layer.res = th.nn.Linear(cin, cout)
    layer.bn = th.nn.BatchNorm1d(cout)
    return layer


class RGCN(th.nn.Module):
    def __init__(self, hidden, ffn, ffn_dropout):
        super().__init__()
        self.layers = th.nn.ModuleList()
        cin = 40
        for size in hidden:
            self.layers.append(_layer(cin, size))
            cin = size
        self.aw = th.nn.Linear(cin, 1)
        self.fcs = th.nn.ModuleList([
            th.nn.Sequential(th.nn.Dropout(ffn_dropout), th.nn.Linear(cin, ffn),
                             th.nn.ReLU(), th.nn.BatchNorm1d(ffn)),
            th.nn.Sequential(th.nn.Dropout(ffn_dropout), th.nn.Linear(ffn, ffn),
                             th.nn.ReLU(), th.nn.BatchNorm1d(ffn)),
            th.nn.Sequential(th.nn.Dropout(ffn_dropout), th.nn.Linear(ffn, ffn),
                             th.nn.ReLU(), th.nn.BatchNorm1d(ffn))])
        self.out = th.nn.Linear(ffn, 1)

    def forward(self, batch):
        x, src, dst, etype, graph_id, smask = batch
        for layer in self.layers:
            previous = x
            weight = (layer.coeff @ layer.W.reshape(65, -1)).reshape(65, layer.W.shape[1], layer.W.shape[2])
            message = th.bmm(x[src].unsqueeze(1), weight[etype]).squeeze(1)
            aggregate = th.zeros(x.shape[0], message.shape[1], dtype=x.dtype).index_add_(0, dst, message)
            x = th.relu(aggregate + layer.h_bias + previous @ layer.loop)
            x = x + th.relu(previous @ layer.res.weight.t() + layer.res.bias)
            x = layer.bn(x)
        weight = th.sigmoid(self.aw(x)).squeeze(1)
        graph = th.zeros(int(graph_id.max()) + 1, x.shape[1], dtype=x.dtype).index_add_(
            0, graph_id, x * (weight * smask)[:, None])
        z = graph
        for fc in self.fcs:
            z = fc(z)
        return self.out(z).squeeze(1)


def batchify(graphs):
    features, sources, destinations, etypes, graph_ids, masks = [], [], [], [], [], []
    offset = 0
    for index, graph in enumerate(graphs):
        arrays = graph['arrays']
        x, src, dst, etype = arrays
        features.append(x)
        sources.append(src + offset)
        destinations.append(dst + offset)
        etypes.append(etype)
        graph_ids.append(th.full((x.shape[0],), index, dtype=th.long))
        masks.append(th.ones(x.shape[0]))
        offset += x.shape[0]
    return (th.cat(features), th.cat(sources), th.cat(destinations),
            th.cat(etypes), th.cat(graph_ids), th.cat(masks))


def evaluate(model, graphs, labels, indices, classification, batch_size=1024):
    model.eval()
    predictions = []
    with th.no_grad():
        for start in range(0, len(indices), batch_size):
            chunk = indices[start:start + batch_size]
            raw = model(batchify([graphs[i] for i in chunk]))
            predictions.append(th.sigmoid(raw) if classification else raw)
    prediction = th.cat(predictions).numpy()
    truth = np.asarray([labels[i] for i in indices], dtype=float)
    if classification:
        accuracy = float(((prediction >= 0.5) == truth.astype(bool)).mean())
        sensitivity = float(((prediction >= 0.5) & (truth == 1)).sum() /
                            max(1, (truth == 1).sum()))
        specificity = float(((prediction < 0.5) & (truth == 0)).sum() /
                            max(1, (truth == 0).sum()))
        return {'accuracy': accuracy, 'sensitivity': sensitivity, 'specificity': specificity}
    residual = ((truth - prediction) ** 2).sum()
    total = ((truth - truth.mean()) ** 2).sum()
    return {'r2': float(1 - residual / total) if total else 0.0,
            'mae': float(np.abs(truth - prediction).mean()),
            'rmse': float(np.sqrt(residual / len(truth)))}


def state_dict(model):
    state = {}
    for index, layer in enumerate(model.layers):
        prefix = f'rgcn_gnn_layers.{index}.'
        state[prefix + 'graph_conv_layer.linear_r.W'] = layer.W
        state[prefix + 'graph_conv_layer.linear_r.coeff'] = layer.coeff
        state[prefix + 'graph_conv_layer.h_bias'] = layer.h_bias
        state[prefix + 'graph_conv_layer.loop_weight'] = layer.loop
        state[prefix + 'res_connection.weight'] = layer.res.weight
        state[prefix + 'res_connection.bias'] = layer.res.bias
        state[prefix + 'bn_layer.weight'] = layer.bn.weight
        state[prefix + 'bn_layer.bias'] = layer.bn.bias
        state[prefix + 'bn_layer.running_mean'] = layer.bn.running_mean
        state[prefix + 'bn_layer.running_var'] = layer.bn.running_var
        state[prefix + 'bn_layer.num_batches_tracked'] = layer.bn.num_batches_tracked
    state['readout.atom_weighting.0.weight'] = model.aw.weight
    state['readout.atom_weighting.0.bias'] = model.aw.bias
    for number, fc in enumerate(model.fcs, 1):
        prefix = f'fc_layers{number}.'
        state[prefix + '1.weight'] = fc[1].weight
        state[prefix + '1.bias'] = fc[1].bias
        state[prefix + '3.weight'] = fc[3].weight
        state[prefix + '3.bias'] = fc[3].bias
        state[prefix + '3.running_mean'] = fc[3].running_mean
        state[prefix + '3.running_var'] = fc[3].running_var
        state[prefix + '3.num_batches_tracked'] = fc[3].num_batches_tracked
    state['predict.0.weight'] = model.out.weight
    state['predict.0.bias'] = model.out.bias
    return {key: value.detach().cpu() for key, value in state.items()}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_task(data_dir, task):
    rows = []
    with (Path(data_dir) / f'{task}.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            rows.append((row['smiles'], float(row[task]), row['group']))
    return rows


def prepare_graphs(rows):
    from rdkit import Chem
    graphs = []
    for smiles, _, _ in rows:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None or not 1 <= mol.GetNumAtoms() <= 128:
            raise ValueError('unparseable training molecule: ' + smiles[:80])
        graphs.append({'smiles': smiles, 'arrays': _graph_arrays(mol, Chem, th)})
    return graphs


def train_one(data_dir, models_dir, task, seed_index, threads=3):
    from tools.science_apps.sme_runner import TASKS as RUNNER_TASKS
    th.set_num_threads(threads)
    hyper = HYPERPARAMETERS[task]
    kind = RUNNER_TASKS[task]['kind']
    classification = kind == 'classification'
    rows = load_task(data_dir, task)
    graphs = prepare_graphs(rows)
    labels = [label for _, label, _ in rows]
    groups = [group for _, _, group in rows]
    train_index = [i for i, group in enumerate(groups) if group == 'training']
    valid_index = [i for i, group in enumerate(groups) if group == 'valid']
    test_index = [i for i, group in enumerate(groups) if group == 'test']
    if not train_index or not valid_index or not test_index:
        raise ValueError(f'incomplete split for {task}')
    th.manual_seed(2022 + seed_index * 10)
    np.random.seed(2022 + seed_index * 10)
    model = RGCN(hyper['hidden'], hyper['ffn'], hyper['ffn_dropout'])
    pos_weight = None
    if classification:
        positives = sum(1 for i in train_index if labels[i] == 1)
        negatives = len(train_index) - positives
        pos_weight = th.tensor([negatives / (positives + 1e-8)])
    best = (-math.inf, None)
    counter = 0
    batch_size = hyper['batch_size']
    started = time.time()
    epoch = 0
    for epoch in range(hyper['epochs']):
        model.train()
        optimizer = th.optim.Adam(model.parameters(), lr=hyper['lr'])
        order = np.random.permutation(train_index)
        for start in range(0, len(order), batch_size):
            chunk = order[start:start + batch_size]
            prediction = model(batchify([graphs[i] for i in chunk]))
            truth = th.tensor([labels[i] for i in chunk], dtype=th.float32)
            if classification:
                loss = th.nn.functional.binary_cross_entropy_with_logits(
                    prediction, truth, pos_weight=pos_weight).mean()
            else:
                loss = th.nn.functional.mse_loss(prediction, truth).mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        validation = evaluate(model, graphs, labels, valid_index, classification)
        score = validation['accuracy'] if classification else validation['r2']
        if score > best[0]:
            best = (score, {key: value.clone() for key, value in model.state_dict().items()})
            counter = 0
        else:
            counter += 1
            if counter >= hyper['patience']:
                break
    model.load_state_dict(best[1])
    metrics = {
        'train': evaluate(model, graphs, labels, train_index, classification),
        'valid': evaluate(model, graphs, labels, valid_index, classification),
        'test': evaluate(model, graphs, labels, test_index, classification)}
    models_dir = Path(models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    filename = f'{task}_{seed_index + 1}.pt'
    path = models_dir / filename
    th.save({'model_state_dict': state_dict(model)}, path)
    return {'file': filename, 'sha256': sha256_file(path), 'seed': seed_index + 1,
            'epochs': epoch + 1, 'metrics': metrics,
            'training_seconds': round(time.time() - started, 1)}


def split_counts(data_path, task):
    counts = {'training': 0, 'valid': 0, 'test': 0}
    with Path(data_path).open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row.get('group') in counts:
                counts[row['group']] += 1
    return counts


def evaluate_ensemble(data_dir, models_dir, task):
    """Score the mean of all seed models on the held-out split."""
    from rdkit import Chem
    rows = load_task(data_dir, task)
    kind = TASKS[task]['kind']
    classification = kind == 'classification'
    graphs = prepare_graphs(rows)
    labels = np.asarray([label for _, label, _ in rows], dtype=float)
    groups = [group for _, _, group in rows]
    test_index = [index for index, group in enumerate(groups) if group == 'test']
    predictions = []
    for path in sorted(Path(models_dir).glob(f'{task}_*.pt')):
        state = th.load(path, map_location='cpu', weights_only=True)['model_state_dict']
        params = _tensor_params(state, th)
        seed_predictions = []
        for index in test_index:
            mol = Chem.MolFromSmiles(rows[index][0])
            mask = th.ones(mol.GetNumAtoms())
            with th.no_grad():
                raw = _predict(params, graphs[index]['arrays'], mask, th)
            seed_predictions.append(1.0 / (1.0 + math.exp(-raw)) if classification else raw)
        predictions.append(seed_predictions)
    mean = np.mean(np.asarray(predictions), axis=0)
    truth = labels[test_index]
    if classification:
        return {'accuracy': float(((mean >= 0.5) == truth.astype(bool)).mean()),
                'seed_count': len(predictions)}
    residual = ((truth - mean) ** 2).sum()
    total = ((truth - truth.mean()) ** 2).sum()
    return {'r2': float(1 - residual / total) if total else 0.0,
            'mae': float(np.abs(truth - mean).mean()),
            'rmse': float(np.sqrt(residual / len(truth))),
            'seed_count': len(predictions)}


def update_manifest(manifest_path, models_dir, data_dir, tasks, results):
    manifest_path = Path(manifest_path)
    existing = {}
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text())
        except ValueError:
            existing = {}
    manifest = existing if existing.get('app_id') == 'sme' else {}
    manifest.update({'app_id': 'sme', 'format': 1, 'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                     'source': {
                         'package': PACKAGE,
                         'note': ('Models retrained from the supplied package datasets with the documented '
                                  'RGCN hyperparameters; the packaged checkpoints did not reproduce the '
                                  'package-reported metrics. ESOL hyperparameters were inferred.'),
                         'training_script': 'scripts/em-agent/sme_train.py'}})
    manifest.setdefault('tasks', {})
    for task in tasks:
        if not results.get(task):
            continue
        seeds = sorted(results[task], key=lambda row: row['seed'])
        kind = TASKS[task]['kind']
        metric_name = 'accuracy' if kind == 'classification' else 'r2'
        mean = lambda split, name: round(float(np.mean([row['metrics'][split][name] for row in seeds])), 4)
        data_path = Path(data_dir) / f'{task}.csv'
        manifest['tasks'][task] = {
            'label': TASKS[task]['label'], 'kind': kind,
            'hidden': HYPERPARAMETERS[task]['hidden'], 'ffn': HYPERPARAMETERS[task]['ffn'],
            'hyperparameters': {key: value for key, value in HYPERPARAMETERS[task].items()
                                if key not in ('hidden', 'ffn')},
            'seeds': seeds,
            'metrics': {f'{split}_{metric_name}_mean': mean(split, metric_name) for split in ('train', 'valid', 'test')}
                       | {f'test_{metric_name}_std': round(float(np.std([row['metrics']['test'][metric_name]
                                                                        for row in seeds])), 4)},
            'data_sha256': sha256_file(data_path),
            'split_counts': split_counts(data_path, task)}
    temporary = manifest_path.with_name(manifest_path.name + '.next')
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(manifest_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--models-dir', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--tasks', nargs='+', default=list(HYPERPARAMETERS))
    parser.add_argument('--seeds', type=int, default=10)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--threads', type=int, default=3)
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--evaluate-only', action='store_true',
                        help='score the stored seed ensembles and update the manifest')
    arguments = parser.parse_args()
    th.set_num_threads(arguments.threads)
    tasks = [task for task in arguments.tasks if task in HYPERPARAMETERS]
    if not tasks:
        raise SystemExit('no matching tasks')
    if arguments.evaluate_only:
        manifest = json.loads(arguments.manifest.read_text())
        for task in tasks:
            metrics = evaluate_ensemble(arguments.data_dir, arguments.models_dir, task)
            manifest['tasks'][task]['ensemble_metrics'] = metrics
            print(json.dumps({'task': task, 'ensemble': metrics}), flush=True)
        temporary = arguments.manifest.with_name(arguments.manifest.name + '.next')
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(arguments.manifest)
        return
    results = {task: [] for task in tasks}
    jobs = [(task, seed) for task in tasks for seed in range(arguments.seeds)]
    with ProcessPoolExecutor(max_workers=arguments.workers) as pool:
        futures = {pool.submit(train_one, arguments.data_dir, arguments.models_dir, task, seed,
                               arguments.threads): (task, seed)
                   for task, seed in jobs}
        for future in as_completed(futures):
            task, seed = futures[future]
            row = future.result()
            results[task].append(row)
            update_manifest(arguments.manifest, arguments.models_dir, arguments.data_dir, tasks, results)
            metric = row['metrics']['test']
            print(json.dumps({'task': task, 'seed': seed + 1, 'epochs': row['epochs'],
                              'seconds': row['training_seconds'], 'test': metric}), flush=True)
    print(json.dumps({task: [row['metrics']['test'] for row in results[task]] for task in tasks}), flush=True)


if __name__ == '__main__':
    main()
