"""SME prediction/attribution contract tests; model weights are not required."""
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

from tools.science_apps.service import JobRequest, prepare_input


def regression_result(**overrides):
    fragment = {'index': 1, 'label': 'CCO', 'atoms': [0, 1, 2], 'atom_count': 3,
                'attribution': 0.1, 'attribution_std': 0.02,
                'attribution_normalized': math.tanh(0.1), 'masked_prediction_mean': 1.1}
    result = {'verified': True, 'app_id': 'sme', 'task': 'DV_R', 'kind': 'regression',
              'seed_count': 10, 'fragmentations': ['brics'],
              'molecules': [{'index': 1, 'smiles': 'CCO', 'atom_count': 3,
                             'prediction': {'mean': 1.2, 'std': 0.1},
                             'schemes': {'brics': {'image': 'images/mol_01_brics.png',
                                                   'fragments': [fragment]}}}]}
    result.update(overrides)
    return result


class SMEContractTests(unittest.TestCase):
    # @spec SME-002 — SMILES-only bounded request with one property task
    def test_request_contract_and_bounds(self):
        request = JobRequest(app_id='sme', task='prediction', method='RGCN',
                             smiles='CCO\nc1ccccc1', sme_task='DV_R')
        name, content, args = prepare_input(request)
        self.assertEqual((name, args), ('request.json', ['request.json']))
        payload = json.loads(content)
        self.assertEqual(payload['sme_task'], 'DV_R')
        self.assertEqual(payload['sme_fragmentation'], 'all')
        for change in ({'xyz': '1\nH 0 0 0\n'}, {'table_csv': 'a'}, {'document_name': 'a.pdf'},
                       {'charge': 1}, {'multiplicity': 2}, {'compound_name': 'ethanol'},
                       {'basis': 'sto-3g'}, {'method': 'other'}, {'task': 'energy'},
                       {'smiles': ''}, {'smiles': 'CCO\nCCO'}, {'smiles': 'C C'},
                       {'sme_task': 'Unknown'}, {'sme_fragmentation': 'atom'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_input(request.model_copy(update=change))
        self.assertEqual(prepare_input(request.model_copy(
            update={'smiles': '\n'.join(['C' * length for length in range(1, 11)])}))[0], 'request.json')
        with self.assertRaises(ValueError):
            prepare_input(request.model_copy(update={'smiles': '\n'.join(['C'] * 11)}))

    # @spec SME-004 — Fragment rows must be finite, in range and image-backed
    def test_result_verification_rejects_incomplete_attribution(self):
        from tools.science_apps.sme_runner import verified_sme
        request = JobRequest(app_id='sme', task='prediction', method='RGCN',
                             smiles='CCO', sme_task='DV_R', sme_fragmentation='brics')
        result = regression_result()
        self.assertTrue(verified_sme(result, request))
        fragment = result['molecules'][0]['schemes']['brics']['fragments'][0]
        molecule = result['molecules'][0]
        for change in ({'verified': False}, {'task': 'Unknown'}, {'kind': 'classification'},
                       {'seed_count': 0}, {'fragmentations': ['fg']},
                       {'molecules': [dict(molecule, schemes={'brics': {'image': 'x.png', 'fragments': []}})]},
                       {'molecules': [dict(molecule, schemes={'brics': {
                           'image': 'images/x.png',
                           'fragments': [dict(fragment, atoms=[0, 3])]}})]},
                       {'molecules': [dict(molecule, schemes={'brics': {
                           'image': 'images/x.png',
                           'fragments': [dict(fragment, attribution=float('nan'))]}})]},
                       {'molecules': [dict(molecule, schemes={'brics': {
                           'image': 'images/x.png',
                           'fragments': [dict(fragment, attribution_normalized=2.0)]}})]},
                       {'molecules': [dict(molecule, prediction={'mean': 1.0, 'std': float('inf')})]},
                       {'molecules': []}, {'molecules': [molecule, molecule]},
                       {'fragmentations': ['brics', 'fg']}):
            self.assertFalse(verified_sme({**result, **change}, request), change)

    def test_classification_requires_probability_and_label(self):
        from tools.science_apps.sme_runner import verified_sme
        request = JobRequest(app_id='sme', task='prediction', method='RGCN',
                             smiles='CCO', sme_task='DV_C', sme_fragmentation='brics')
        molecule = {'index': 1, 'smiles': 'CCO', 'atom_count': 3,
                    'prediction': {'mean': 0.7, 'std': 0.05}, 'probability_class1': 0.7,
                    'label': 1, 'schemes': {'brics': {
                        'image': 'images/mol_01_brics.png',
                        'fragments': [{'index': 1, 'label': 'CCO', 'atoms': [0, 1, 2],
                                       'atom_count': 3, 'attribution': 0.1, 'attribution_std': 0.01,
                                       'attribution_normalized': math.tanh(0.1),
                                       'masked_prediction_mean': 0.6}]}}}
        result = {'verified': True, 'app_id': 'sme', 'task': 'DV_C', 'kind': 'classification',
                  'seed_count': 10, 'fragmentations': ['brics'], 'molecules': [molecule]}
        self.assertTrue(verified_sme(result, request))
        for change in ({'probability_class1': 1.2}, {'label': 2}, {'label': True}):
            self.assertFalse(verified_sme({**result, 'molecules': [{**molecule, **change}]}, request))

    def test_availability_requires_venv_manifest_and_models(self):
        from tools.science_apps.sme_runner import sme_available
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertFalse(sme_available(root))
            (root / '.venv/bin').mkdir(parents=True)
            (root / '.venv/bin/python').touch(mode=0o755)
            (root / 'manifest.json').write_text(json.dumps({'app_id': 'sme', 'format': 1, 'tasks': {
                'DV_R': {'seeds': [{'file': 'missing.pt'}]}}}))
            self.assertFalse(sme_available(root))
            (root / 'models').mkdir()
            (root / 'models/missing.pt').touch()
            self.assertTrue(sme_available(root))

    @unittest.skipUnless(__import__('importlib').util.find_spec('rdkit') and
                         __import__('importlib').util.find_spec('torch'),
                         'RDKit and PyTorch are not installed')
    def test_runner_writes_verified_outputs_with_a_stub_model(self):
        import torch as th
        from tools.science_apps import sme_runner
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'tool'
            (root / '.venv/bin').mkdir(parents=True)
            (root / '.venv/bin/python').touch()
            (root / 'models').mkdir()
            th.manual_seed(0)
            state = {}
            for index in range(1):
                prefix = f'rgcn_gnn_layers.{index}.'
                state[prefix + 'graph_conv_layer.linear_r.W'] = th.randn(65, 40, 64) * 0.02
                state[prefix + 'graph_conv_layer.linear_r.coeff'] = th.randn(65, 65) * 0.02
                state[prefix + 'graph_conv_layer.h_bias'] = th.zeros(64)
                state[prefix + 'graph_conv_layer.loop_weight'] = th.randn(40, 64) * 0.02
                state[prefix + 'res_connection.weight'] = th.randn(64, 40) * 0.02
                state[prefix + 'res_connection.bias'] = th.zeros(64)
                state[prefix + 'bn_layer.weight'] = th.ones(64)
                state[prefix + 'bn_layer.bias'] = th.zeros(64)
                state[prefix + 'bn_layer.running_mean'] = th.zeros(64)
                state[prefix + 'bn_layer.running_var'] = th.ones(64)
            state['readout.atom_weighting.0.weight'] = th.randn(1, 64) * 0.02
            state['readout.atom_weighting.0.bias'] = th.zeros(1)
            for name in ('fc_layers1', 'fc_layers2', 'fc_layers3'):
                state[name + '.1.weight'] = th.randn(64, 64) * 0.02
                state[name + '.1.bias'] = th.zeros(64)
                state[name + '.3.weight'] = th.ones(64)
                state[name + '.3.bias'] = th.zeros(64)
                state[name + '.3.running_mean'] = th.zeros(64)
                state[name + '.3.running_var'] = th.ones(64)
            state['predict.0.weight'] = th.randn(1, 64) * 0.02
            state['predict.0.bias'] = th.zeros(1)
            model_path = root / 'models/DV_R_1.pt'
            th.save({'model_state_dict': state}, model_path)
            import hashlib
            digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
            (root / 'manifest.json').write_text(json.dumps({
                'app_id': 'sme', 'format': 1, 'created_at': '2026-01-01T00:00:00Z',
                'source': {}, 'tasks': {'DV_R': {
                    'kind': 'regression', 'hidden': [64], 'ffn': 64,
                    'seeds': [{'file': 'DV_R_1.pt', 'sha256': digest}], 'metrics': {}}}}))
            job = Path(folder) / 'job'
            job.mkdir()
            (job / 'request.json').write_text(json.dumps({
                'app_id': 'sme', 'task': 'prediction', 'method': 'RGCN', 'basis': '',
                'xyz': '', 'smiles': 'CCO\nc1ccccc1', 'input_kind': 'smiles',
                'compound_name': '', 'title': '', 'charge': 0, 'multiplicity': 1,
                'cores': 1, 'memory_mb': 1024, 'input_mode': 'single', 'table_csv': '',
                'document_name': '', 'sme_task': 'DV_R', 'sme_fragmentation': 'brics'}))
            previous = os.getcwd()
            os.chdir(job)
            try:
                sme_runner.run_job(job / 'request.json', root=root)
            finally:
                os.chdir(previous)
            result = json.loads((job / 'result.json').read_text())
            self.assertTrue(sme_runner.verified_sme(result, json.loads((job / 'request.json').read_text()),
                                                    job))
            self.assertEqual([molecule['smiles'] for molecule in result['molecules']],
                             ['CCO', 'c1ccccc1'])
            self.assertTrue((job / 'results.zip').is_file())
            for molecule in result['molecules']:
                self.assertTrue((job / molecule['schemes']['brics']['image']).is_file())


if __name__ == '__main__':
    unittest.main()
