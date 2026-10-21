"""Pretrained crystal-morphology classification for the supplied process dataset.

Loads only the SHA-256-verified, preinstalled model cache; request inputs are
validated by the service and again here. Heavy imports load only in the runner
process, so the science service can start while this tool is unavailable.
"""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import pickle
import sys
import zipfile

ROOT = Path('/opt/em-agent-tools/crystal-morphology')
MODELS = ('CatBoost', 'LightGBM', 'XGBoost', 'SVM', 'GradientBoosting', 'RandomForest')
CLASS_ORDER = ['其他', '球', '针']
MAX_BATCH_ROWS = 500
# Canonical feature name, request field, hard input bounds. The bounds are unit
# plausibility limits, not an applicability claim: the training envelope is
# checked per row instead.
FEATURE_FIELDS = (
    ('添加剂百分比', 'additive_percent', 0.0, 20.0),
    ('反溶剂温度(°C)', 'antisolvent_temp_c', -10.0, 60.0),
    ('搅拌速率(rpm)', 'stirring_rpm', 50.0, 2000.0),
    ('浓度(g/ml)', 'concentration_g_ml', 0.001, 0.5),
    ('溶剂/反溶剂比值', 'solvent_ratio', 0.001, 2.0),
)


def morphology_available(root=ROOT):
    return (os.access(root / '.venv/bin/python', os.X_OK)
            and (root / 'manifest.json').is_file()
            and (root / 'models/model_results_cache.pkl').is_file())


# @spec CM-002 — Fixed five-parameter contract, single condition or bounded batch
def parse_batch_rows(text):
    if not text.strip():
        raise ValueError('invalid_morphology_input')
    reader = csv.reader(io.StringIO(text.lstrip('﻿')))
    try:
        header = [cell.strip() for cell in next(reader)]
    except StopIteration:
        raise ValueError('invalid_morphology_input') from None
    if (len(header) != len(FEATURE_FIELDS)
            or any(header.count(name) != 1 for name, _, _, _ in FEATURE_FIELDS)):
        raise ValueError('invalid_morphology_input')
    columns = [header.index(name) for name, _, _, _ in FEATURE_FIELDS]
    rows = []
    for line in reader:
        if not line or all(not cell.strip() for cell in line):
            continue
        if len(line) != len(header) or len(rows) >= MAX_BATCH_ROWS:
            raise ValueError('invalid_morphology_input')
        values = []
        for (_, _, low, high), column in zip(FEATURE_FIELDS, columns):
            try:
                value = float(line[column].strip())
            except ValueError:
                raise ValueError('invalid_morphology_input') from None
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError('invalid_morphology_input')
            values.append(value)
        rows.append(values)
    if not rows:
        raise ValueError('invalid_morphology_input')
    return rows


def validate_morphology(request):
    if (request.xyz or request.smiles or request.basis or request.document_name
            or request.charge or request.multiplicity != 1
            or request.task != 'classification' or request.method not in ('auto', *MODELS)):
        raise ValueError('invalid_morphology_input')
    if request.input_mode == 'single':
        if request.table_csv:
            raise ValueError('invalid_morphology_input')
        for _, field, low, high in FEATURE_FIELDS:
            value = getattr(request, field)
            if value is None or not math.isfinite(value) or not low <= value <= high:
                raise ValueError('invalid_morphology_input')
    else:
        if any(getattr(request, field) is not None for _, field, _, _ in FEATURE_FIELDS):
            raise ValueError('invalid_morphology_input')
        parse_batch_rows(request.table_csv)


def expected_row_count(request):
    # Accepts the service's JobRequest model or the runner's parsed request dict.
    mode = request['input_mode'] if isinstance(request, dict) else request.input_mode
    if mode == 'single':
        return 1
    table = request['table_csv'] if isinstance(request, dict) else request.table_csv
    try:
        return len(parse_batch_rows(table))
    except ValueError:
        return None


# @spec CM-003 — Fixed classes, SHA-verified cache, cached scaler for SVM
def choose_model(results):
    # Same ordering as the source code's pick_best_model: higher test accuracy,
    # then test F1, then CV score, then smaller generalization gap.
    def key(item):
        metrics = item[1]
        return (metrics.get('test_accuracy', 0.0), metrics.get('test_f1', 0.0),
                metrics.get('best_cv_score', 0.0), -metrics.get('generalization_gap', 1e9))
    return max(results.items(), key=key)[0]


def load_bundle(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    model_file = root / 'models/model_results_cache.pkl'
    digest = hashlib.sha256(model_file.read_bytes()).hexdigest()
    if digest != manifest.get('model_sha256'):
        raise ValueError('model asset checksum mismatch')
    with model_file.open('rb') as stream:
        cache = pickle.load(stream)
    if (cache.get('feature_names') != [name for name, _, _, _ in FEATURE_FIELDS]
            or list(cache.get('label_encoder').classes_) != CLASS_ORDER
            or set(cache.get('results', {})) != set(MODELS)):
        raise ValueError('model asset does not match the expected contract')
    return manifest, cache, digest


def predict(cache, model_name, rows, cores):
    import numpy as np
    from threadpoolctl import threadpool_limits
    model = cache['results'][model_name]['model']
    if model_name in {'XGBoost', 'LightGBM', 'RandomForest'}:
        # Training defaults may carry n_jobs=-1; never occupy all cores.
        model.set_params(n_jobs=cores)
    matrix = np.asarray(rows, dtype=float)
    if model_name == 'SVM':
        matrix = cache['scaler'].transform(matrix)
    with threadpool_limits(limits=cores):
        labels = np.asarray(model.predict(matrix)).reshape(-1).astype(int)
        probabilities = np.asarray(model.predict_proba(matrix))
    if (probabilities.shape != (len(rows), len(CLASS_ORDER))
            or not np.isfinite(probabilities).all()
            or not ((probabilities >= 0) & (probabilities <= 1)).all()
            or not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-6)):
        raise ValueError('model produced invalid probabilities')
    return labels, probabilities


def training_envelope(cache):
    import numpy as np
    matrix = np.asarray(cache['X'], dtype=float)
    return [(float(matrix[:, i].min()), float(matrix[:, i].max()))
            for i in range(len(FEATURE_FIELDS))]


# @spec CM-004 — Reviewable per-row predictions with model and envelope flags
def verified_morphology(result, request):
    if result.get('verified') is not True or result.get('app_id') != 'crystal-morphology':
        return False
    if result.get('model_id') not in MODELS or result.get('class_order') != CLASS_ORDER:
        return False
    rows = result.get('rows')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_BATCH_ROWS:
        return False
    expected = expected_row_count(request)
    if expected is None or len(rows) != expected or result.get('prediction_count') != expected:
        return False
    counts = result.get('class_counts')
    if (not isinstance(counts, dict) or set(counts) != set(CLASS_ORDER)
            or sum(counts.values()) != len(rows)):
        return False
    tally = {label: 0 for label in CLASS_ORDER}
    for row in rows:
        if not isinstance(row, dict) or row.get('predicted_label') not in CLASS_ORDER:
            return False
        tally[row['predicted_label']] += 1
        features = row.get('features')
        probabilities = row.get('probabilities')
        if not isinstance(features, dict) or list(features) != [name for name, _, _, _ in FEATURE_FIELDS]:
            return False
        if not isinstance(probabilities, dict) or list(probabilities) != CLASS_ORDER:
            return False
        values = list(probabilities.values())
        if (not all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1 for value in values)
                or abs(sum(values) - 1.0) > 1e-6):
            return False
        if type(row.get('in_training_range')) is not bool:
            return False
    return counts == tally


def write_outputs(result):
    names = [name for name, _, _, _ in FEATURE_FIELDS]
    with Path('predictions.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['序号'] + names + ['预测类别', '概率_其他', '概率_球', '概率_针', '训练范围内'])
        for row in result['rows']:
            writer.writerow([row['index']] + [row['features'][name] for name in names]
                            + [row['predicted_label']]
                            + [f"{row['probabilities'][label]:.6f}" for label in CLASS_ORDER]
                            + ['是' if row['in_training_range'] else '否'])
    Path('result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    with zipfile.ZipFile('results.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ('request.json', 'result.json', 'predictions.csv'):
            if Path(name).is_file():
                archive.write(name)


def run_job(request_path, root=ROOT):
    request = json.loads(Path(request_path).read_text())
    if request.get('app_id') != 'crystal-morphology' or request.get('task') != 'classification':
        raise ValueError('unsupported request')
    cores = int(request.get('cores', 2))
    if hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:cores])
    if request['input_mode'] == 'single':
        rows = [[request[field] for _, field, _, _ in FEATURE_FIELDS]]
    else:
        rows = parse_batch_rows(request['table_csv'])
    manifest, cache, digest = load_bundle(Path(root))
    model_name = request['method'] if request['method'] != 'auto' else choose_model(cache['results'])
    labels, probabilities = predict(cache, model_name, rows, cores)
    limits = training_envelope(cache)
    result_rows, counts, outside = [], {label: 0 for label in CLASS_ORDER}, 0
    for index, (features, prediction, probability) in enumerate(zip(rows, labels, probabilities), 1):
        label = CLASS_ORDER[int(prediction)]
        counts[label] += 1
        within = all(low - 1e-9 <= value <= high + 1e-9
                     for value, (low, high) in zip(features, limits))
        outside += not within
        result_rows.append({
            'index': index,
            'features': dict(zip([name for name, _, _, _ in FEATURE_FIELDS], features)),
            'predicted_label': label,
            'probabilities': {name: float(value) for name, value in zip(CLASS_ORDER, probability)},
            'in_training_range': within})
    result = {'verified': True, 'app_id': 'crystal-morphology', 'model_id': model_name,
              'model_selection': request['method'], 'class_order': list(CLASS_ORDER),
              'prediction_count': len(result_rows), 'class_counts': counts,
              'outside_training_range_count': outside, 'rows': result_rows,
              'provenance': {**manifest, 'model_sha256': digest},
              'scope': ('Pretrained classifier for five crystallization process parameters, '
                        'trained on the supplied LLM-105/PSI 83-case dataset; classes 其他/球/针. '
                        'Probabilities are uncalibrated model outputs. Rows outside the training '
                        'envelope are extrapolation; no applicability to other chemistries, '
                        'solvent/additive systems or measurement methods has been demonstrated.')}
    if not verified_morphology(result, request):
        raise ValueError('incomplete morphology result')
    write_outputs(result)
    print(f'{len(result_rows)} row(s) predicted with {model_name}; '
          f'{outside} outside the training envelope', flush=True)
    print('EM_AGENT_MORPHOLOGY_COMPLETE', flush=True)


if __name__ == '__main__':
    run_job(sys.argv[1])
