"""Exercise the manual application contract without scientific licenses/models."""
import asyncio
from contextlib import redirect_stdout
import io
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from tools.science_apps.service import JobRequest, Manager, create_app, prepare_input

WATER = '3\nwater\nO 0 0 0\nH 0.7586 0 0.5043\nH -0.7586 0 0.5043\n'


class ScienceTests(unittest.TestCase):
    # @spec ER-002 — Single-product prediction and verified ranked candidates share the queue.
    def test_editretro_contract_and_result_gate(self):
        from tools.science_apps.editretro_runner import verified_editretro
        request = JobRequest(app_id='editretro', task='retrosynthesis', smiles='CC(=O)NCC',
                             top_k=2, augmentations=5)
        name, content, args = prepare_input(request)
        self.assertEqual((name, args), ('request.json', ['request.json']))
        self.assertEqual(__import__('json').loads(content)['augmentations'], 5)
        for change in ({'smiles': 'CCO.CN'}, {'smiles': 'CCO\nCCN'}, {'task': 'search'},
                       {'xyz': WATER}, {'method': '3D'}, {'charge': 1}, {'compound_name': 'ethanol'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_input(request.model_copy(update=change))
        for change in ({'top_k': 21}, {'augmentations': 0}):
            with self.assertRaises(ValueError):
                JobRequest(**{**request.model_dump(), **change})
        result = {'app_id': 'editretro', 'verified': True, 'device': 'cpu',
                  'model_sha256': '3a537dc6a8992dd61c02993485d8f89c83a7169e63ccb956dab88b949327daf8',
                  'input_smiles': request.smiles, 'top_k': 2, 'augmentations': 5,
                  'prediction_count': 1,
                  'candidates': [{'rank': 1, 'smiles': 'CCN.CC(=O)O', 'reactants': ['CCN', 'CC(=O)O']}]}
        self.assertTrue(verified_editretro(result, request))
        for change in ({'candidates': []}, {'prediction_count': 2}, {'input_smiles': 'CCO'},
                       {'model_sha256': 'wrong'}, {'augmentations': 20},
                       {'candidates': [{'rank': 2, 'smiles': 'CCN', 'reactants': ['CCN']}]}):
            with self.subTest(change=change):
                self.assertFalse(verified_editretro({**result, **change}, request))
        async def exercise(root):
            executable = root / 'editretro-test'
            executable.touch(mode=0o755)
            manager = Manager(root / 'jobs')
            with patch('tools.science_apps.service.application_executable', return_value=str(executable)):
                for valid in (False, True):
                    executable.write_text('#!/bin/sh\necho EM_AGENT_EDITRETRO_COMPLETE\n' +
                        ("echo '%s' > result.json\npython3 -c 'from zipfile import ZipFile; ZipFile(\"results.zip\",\"w\").close()'\n" % __import__('json').dumps(result) if valid else ''))
                    job = manager.submit(request)
                    await manager.run(job['id'])
                    self.assertEqual(job['status'], 'succeeded' if valid else 'failed')
                self.assertIsNone(job['energy_hartree'])
                self.assertEqual(job['result']['candidates'][0]['reactants'], ['CCN', 'CC(=O)O'])
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    # @spec SJT-001 — Agent submissions outlive the manual timeout and remain cancellable
    def test_agent_jobs_have_no_platform_timeout(self):
        async def exercise(root):
            executable = root / 'fake-xtb'
            executable.write_text('#!/bin/sh\nsleep 1\necho "normal termination of xtb"\n')
            executable.chmod(0o755)
            manager = Manager(root / 'jobs')
            with patch('tools.science_apps.service.application_executable', return_value=str(executable)), \
                    patch('tools.science_apps.service.TIMEOUT_SECONDS', 0.01):
                job = manager.submit(JobRequest(app_id='xtb', xyz=WATER), source='agent')
                await asyncio.wait_for(manager.run(job['id']), 4)
                self.assertEqual(job['status'], 'succeeded')
                self.assertIsNone(job['error'])
                self.assertEqual(Manager(root / 'jobs').get(job['id'])['source'], 'agent')
                executable.write_text('#!/bin/sh\nsleep 30\n')
                job = manager.submit(JobRequest(app_id='xtb', xyz=WATER), source='agent')
                runner = asyncio.create_task(manager.run(job['id']))
                while manager.process is None:
                    await asyncio.sleep(0.01)
                await manager.cancel(job['id'])
                await asyncio.wait_for(runner, 3)
                self.assertEqual(job['status'], 'cancelled')
                self.assertIsNone(manager.process)
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    # @spec SJT-001 — JSON and document submissions default to manual, CLI marks agent
    def test_submission_source_for_both_endpoints(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch('tools.science_apps.service.application_executable', return_value='/missing/tool'):
            with TestClient(create_app(Path(folder), 'test-key')) as client:
                for source in ['manual', 'agent']:
                    headers = {'X-Session-API-Key': 'test-key'}
                    if source == 'agent':
                        headers['X-EM-Agent-Source'] = source
                    catalog = client.get('/api/science/apps', headers=headers).json()
                    self.assertTrue(all(app['timeout_seconds'] == (None if source == 'agent' else 900)
                                        for app in catalog))
                    response = client.post('/api/science/jobs', headers=headers,
                                           json={'app_id': 'xtb', 'xyz': WATER})
                    self.assertEqual(response.status_code, 201, response.text)
                    self.assertEqual(response.json()['source'], source)
                    response = client.post('/api/science/documents?filename=paper.pdf',
                                           headers=headers, content=b'%PDF-1.4\nExample')
                    self.assertEqual(response.status_code, 201, response.text)
                    self.assertEqual(response.json()['source'], source)
                headers['X-EM-Agent-Source'] = 'unknown'
                self.assertEqual(client.post('/api/science/jobs', headers=headers,
                    json={'app_id': 'xtb', 'xyz': WATER}).status_code, 422)

    # @spec MG-003 — Bounded generation requests never accept structures or shell input.
    def test_molgen_contract_and_verified_pool_gate(self):
        from tools.science_apps.molgen_runner import verified_molgen
        request = JobRequest(app_id='molgen', task='generation', method='ChemTSv3',
                             molgen_workers=2, molgen_seconds=600, molgen_seed=7,
                             cores=3, memory_mb=4096)
        name, content, args = prepare_input(request)
        self.assertEqual((name, args), ('request.json', ['request.json']))
        self.assertEqual(__import__('json').loads(content)['molgen_workers'], 2)
        for change in ({'task': 'energy'}, {'xyz': WATER}, {'smiles': 'CCO'},
                       {'charge': 1}, {'method': 'MCTS'}, {'table_csv': 'a,b'},
                       {'molgen_workers': 8}, {'molgen_seconds': 30},
                       {'cores': 2}, {'memory_mb': 512}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_input(request.model_copy(update=change))
        result = {'app_id': 'molgen', 'verified': True, 'workers': 2,
                  'generation_seconds': 600, 'seed': 7,
                  'generated_records': 5, 'unique_generated': 5,
                  'pool_rows': 10, 'generated_pool_rows': 5, 'best_reward': 0.5,
                  'worker_results': [
                      {'run_id': 'run_00', 'exit_code': 0, 'done': True, 'records': 3, 'best_reward': 0.5},
                      {'run_id': 'run_01', 'exit_code': 0, 'done': True, 'records': 2, 'best_reward': 0.4}],
                  'top_molecules': [{'smiles': 'C[N+](=O)[O-]', 'reward': 0.5}]}
        self.assertTrue(verified_molgen(result, request))
        for change in ({'generated_records': 0}, {'seed': 8}, {'workers': 1},
                       {'worker_results': result['worker_results'][:1]},
                       {'worker_results': [{**result['worker_results'][0], 'done': False},
                                           result['worker_results'][1]]},
                       {'top_molecules': []}, {'generated_pool_rows': 0}):
            with self.subTest(change=change):
                self.assertFalse(verified_molgen({**result, **change}, request))
        async def exercise(root):
            executable = root / 'molgen-test'
            manager = Manager(root / 'jobs')
            with patch('tools.science_apps.service.application_executable', return_value=str(executable)):
                for valid in (False, True):
                    executable.write_text('#!/bin/sh\n' +
                        ("echo '%s' > result.json\ntouch molecules.csv\n"
                         "python3 -c 'from zipfile import ZipFile; ZipFile(\"results.zip\",\"w\").close()'\n" %
                         __import__('json').dumps(result) if valid else '') +
                        'echo EM_AGENT_MOLGEN_COMPLETE\n')
                    executable.chmod(0o755)
                    job = manager.submit(request)
                    await manager.run(job['id'])
                    detail = manager.detail(job['id'])
                    self.assertEqual(detail['status'], 'succeeded' if valid else 'failed')
                    self.assertEqual(detail.get('result'), result if valid else None)
                    self.assertIsNone(detail['energy_hartree'])
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    # @spec SJT-001 — Every bundled Agent CLI marks actual submission requests
    def test_agent_cli_submission_headers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'water.xyz').write_text(WATER)
            (root / 'molecules.smi').write_text('CCO')
            (root / 'paper.pdf').write_bytes(b'%PDF-1.4\nExample')
            cases = [
                ('em-cnt2d', []),
                ('em-bde', ['--smiles', 'CCO']),
                ('em-magus', [str(root / 'water.xyz'), '--volume-min', '180', '--volume-max', '400']),
                ('em-reaction', ['lcms2yield', str(root / 'molecules.smi')]),
                ('em-reaction', ['editretro', str(root / 'molecules.smi'), '--top-k', '10', '--augmentations', '5']),
                ('em-mineru', [str(root / 'paper.pdf')]),
                ('em-morphology', ['--additive-percent', '1', '--antisolvent-temp-c', '10',
                                   '--stirring-rpm', '300', '--concentration-g-ml', '0.06',
                                   '--solvent-ratio', '0.125']),
                ('em-molgen', ['--workers', '2', '--seconds', '600']),
            ]
            for name, args in cases:
                with self.subTest(cli=name), patch.dict('os.environ', {'LOCAL_BACKEND_API_KEY': 'test-key'}), \
                        patch('sys.argv', [name, 'submit', *args]), redirect_stdout(io.StringIO()), \
                        patch('urllib.request.urlopen', return_value=io.BytesIO(b'{}')) as opened:
                    runpy.run_path(str(Path(__file__).parent / name), run_name='__main__')
                    request = opened.call_args.args[0]
                    self.assertEqual(request.get_method(), 'POST')
                    self.assertEqual(request.get_header('X-em-agent-source'), 'agent')
                    self.assertEqual(request.get_header('X-session-api-key'), 'test-key')

    # @spec CNT2D-006 — Shared queue stores only a verified conduction result.
    def test_cnt2d_result_verification_and_nonmolecular_request(self):
        from tools.science_apps.cnt2d_runner import validate_cnt2d
        request = JobRequest(app_id='cnt2d', task='conduction', method='FEM-P2')
        name, content, args = prepare_input(request)
        self.assertEqual((name, args), ('request.json', ['request.json']))
        self.assertEqual(__import__('json').loads(content)['cnt_seed'], 20260901)
        with self.assertRaises(ValueError):
            prepare_input(request.model_copy(update={'xyz': WATER}))
        result = {'verified': True, 'app_id': 'cnt2d', 'unit': 'W/(m K)',
                  'parameters': validate_cnt2d(request), 'seed': 20260901,
                  'metrics': {'Keff_X': .15, 'CNT_Number': 10, 'Triangles': 1000,
                              'Energy_Balance_Error': 1e-9, 'Free_Residual_Relative': 1e-10,
                              'Heatflow_Left': -3., 'Heatflow_Right': 3.,
                              'Matrix_Area_Fraction_Mesh': .99, 'Core_Area_Fraction_Mesh': .00784,
                              'Interface_Area_Fraction_Mesh': .00216}}
        async def exercise(root):
            executable = root / 'cnt-solver'
            manager = Manager(root / 'jobs')
            with patch('tools.science_apps.service.application_executable', return_value=str(executable)):
                for valid in [False, True]:
                    payload = result if valid else {**result, 'unit': 'eV'}
                    executable.write_text('#!/bin/sh\necho \'%s\' > result.json\ntouch results.zip\necho EM_AGENT_CNT2D_COMPLETE\n' % __import__('json').dumps(payload))
                    executable.chmod(0o755)
                    job = manager.submit(request)
                    await manager.run(job['id'])
                    detail = manager.detail(job['id'])
                    self.assertEqual(detail['status'], 'succeeded' if valid else 'failed')
                    self.assertEqual(detail.get('result'), result if valid else None)
                    self.assertIsNone(detail['energy_hartree'])
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    # @spec CM-003 — Only a verified morphology result publishes predictions
    def test_morphology_publishes_only_complete_verified_result(self):
        async def exercise(root):
            executable = root / 'morphology-model'
            manager = Manager(root / 'jobs')
            features = {'添加剂百分比': 1.0, '反溶剂温度(°C)': 10.0, '搅拌速率(rpm)': 300.0,
                        '浓度(g/ml)': 0.06, '溶剂/反溶剂比值': 0.125}
            result = {'verified': True, 'app_id': 'crystal-morphology', 'model_id': 'CatBoost',
                      'class_order': ['其他', '球', '针'], 'prediction_count': 1,
                      'class_counts': {'其他': 0, '球': 1, '针': 0},
                      'rows': [{'index': 1, 'features': features, 'predicted_label': '球',
                                'probabilities': {'其他': 0.2, '球': 0.7, '针': 0.1},
                                'in_training_range': True}]}
            request = JobRequest(app_id='crystal-morphology', task='classification', input_mode='single',
                                 additive_percent=1.0, antisolvent_temp_c=10, stirring_rpm=300,
                                 concentration_g_ml=0.06, solvent_ratio=0.125)
            with patch('tools.science_apps.service.application_executable', return_value=str(executable)):
                for valid in [False, True]:
                    payload = result if valid else {**result, 'prediction_count': 2}
                    executable.write_text('#!/bin/sh\necho \'%s\' > result.json\necho EM_AGENT_MORPHOLOGY_COMPLETE\n' % __import__('json').dumps(payload, ensure_ascii=False))
                    executable.chmod(0o755)
                    job = manager.submit(request)
                    await manager.run(job['id'])
                    detail = manager.detail(job['id'])
                    self.assertEqual(detail['status'], 'succeeded' if valid else 'failed')
                    self.assertEqual(detail.get('result'), result if valid else None)
                    self.assertIsNone(detail['energy_hartree'])
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    def test_bde_only_publishes_complete_verified_results(self):
        async def exercise(root):
            executable = root / 'bde-model'
            manager = Manager(root / 'jobs')
            result = {'verified': True, 'mode': 'ALFABET', 'unit': 'kcal/mol', 'canonical_smiles': 'CC',
                      'bonds': [{'bond_index': 0, 'status': 'ok', 'bde_kcal_mol': 90.2}],
                      'minimum_bond_index': 0, 'minimum_bde_kcal_mol': 90.2}
            with patch('tools.science_apps.service.application_executable', return_value=str(executable)):
                for valid in [False, True]:
                    payload = result if valid else {**result, 'minimum_bond_index': 3}
                    executable.write_text('#!/bin/sh\necho \'%s\' > result.json\necho EM_AGENT_BDE_COMPLETE\n' % __import__('json').dumps(payload))
                    executable.chmod(0o755)
                    job = manager.submit(JobRequest(app_id='bde', task='bde', smiles='CC'))
                    await manager.run(job['id'])
                    detail = manager.detail(job['id'])
                    self.assertEqual(detail['status'], 'succeeded' if valid else 'failed')
                    self.assertEqual(detail.get('result'), result if valid else None)
                    self.assertIsNone(detail['energy_hartree'])
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    def test_reaction_ipc_works_with_long_persistent_paths_and_cleans_scratch(self):
        async def exercise(root):
            executable = root / 'ipc-model'
            executable.write_text('#!/usr/bin/env python3\n'
                'import json, tempfile\nfrom multiprocessing.connection import Listener\n'
                'from pathlib import Path\n'
                'with Listener(str(Path(tempfile.gettempdir()) / "ipc.sock"), family="AF_UNIX") as listener:\n'
                '    print("scratch=" + tempfile.gettempdir())\n'
                'Path("result.json").write_text(json.dumps({"verified":True,"app_id":"lcms2yield","correction_factors":[{"smiles":"c1ccccc1","cf":1.13}]}))\n'
                'print("EM_AGENT_REACTION_COMPLETE")\n')
            executable.chmod(0o755)
            manager = Manager(root / ('persistent-' + 'a' * 80))
            with patch('tools.science_apps.service.application_executable', return_value=str(executable)):
                job = manager.submit(JobRequest(app_id='lcms2yield', task='correction_factor', smiles='c1ccccc1'))
                await manager.run(job['id'])
            detail = manager.detail(job['id'])
            self.assertEqual(detail['status'], 'succeeded', detail['log'])
            scratch = next(line.removeprefix('scratch=') for line in detail['log'].splitlines() if line.startswith('scratch='))
            self.assertFalse(Path(scratch).exists())
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    def test_reaction_inputs_use_smiles_and_bounded_search(self):
        request = JobRequest(app_id='aizynthfinder', task='retrosynthesis', smiles='CC(=O)Oc1ccccc1C(=O)O')
        name, content, args = prepare_input(request)
        self.assertEqual(name, 'request.json')
        self.assertEqual(__import__('json').loads(content)['smiles'], request.smiles)
        self.assertEqual(args, ['request.json'])
        for changes in [{'smiles': 'CCO; touch /tmp/x'}, {'smiles': 'CCO.O'},
                        {'xyz': WATER}, {'task': 'energy'}, {'method': 'arbitrary'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                prepare_input(request.model_copy(update=changes))
        with self.assertRaises(ValueError):
            JobRequest(app_id='aizynthfinder', task='retrosynthesis', smiles='CCO', search_seconds=901)
        cf = JobRequest(app_id='lcms2yield', task='correction_factor', smiles='c1ccccc1\nCC(=O)Oc1ccccc1C(=O)O')
        self.assertEqual(prepare_input(cf)[0], 'request.json')

    def test_reaction_success_requires_typed_verified_results(self):
        async def exercise(root):
            executable = root / 'fake-reaction'
            manager = Manager(root / 'jobs')
            cases = [
                ('aizynthfinder', 'retrosynthesis', {'verified': True, 'app_id': 'aizynthfinder', 'route_count': 2, 'solved_count': 1}),
                ('lcms2yield', 'correction_factor', {'verified': True, 'app_id': 'lcms2yield', 'correction_factors': [{'smiles': 'c1ccccc1', 'cf': 1.13}]}),
            ]
            for app_id, task, result in cases:
                with patch('tools.science_apps.service.application_executable', return_value=str(executable)):
                    executable.write_text('#!/bin/sh\necho EM_AGENT_REACTION_COMPLETE\n')
                    executable.chmod(0o755)
                    job = manager.submit(JobRequest(app_id=app_id, task=task, smiles='c1ccccc1'))
                    await manager.run(job['id'])
                    self.assertEqual(manager.detail(job['id'])['status'], 'failed')
                    executable.write_text('#!/bin/sh\necho \'%s\' > result.json\necho EM_AGENT_REACTION_COMPLETE\n' % __import__('json').dumps(result))
                    job = manager.submit(JobRequest(app_id=app_id, task=task, smiles='c1ccccc1'))
                    await manager.run(job['id'])
                    detail = manager.detail(job['id'])
                    self.assertEqual(detail['status'], 'succeeded')
                    self.assertIsNone(detail['energy_hartree'])
                    self.assertEqual(detail['result'], result)
                    self.assertNotIn('structure.xyz', [item['name'] for item in detail['files']])
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    def test_magus_validates_molecular_search_before_queueing(self):
        request = JobRequest(app_id='magus', xyz=WATER, task='search', method='MACE-OFF23',
                             molecules_per_cell=4, generations=3, population_size=6,
                             volume_min=180.0, volume_max=400.0)
        name, content, args = prepare_input(request)
        self.assertEqual(name, 'request.json')
        self.assertEqual(__import__('json').loads(content)['molecules_per_cell'], 4)
        self.assertEqual(args, ['request.json'])
        for changes in [{'charge': 2}, {'multiplicity': 3}, {'task': 'energy'},
                        {'volume_min': 401.0}, {'xyz': '1\nFe\nFe 0 0 0\n'},
                        {'molecules_per_cell': 8, 'xyz': '18\nwater\n' + '\n'.join(WATER.splitlines()[2:] * 6)}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                prepare_input(request.model_copy(update=changes))

    def test_magus_process_requires_verified_result_and_reports_ev(self):
        async def exercise(root):
            executable = root / 'fake-magus'
            executable.write_text('#!/bin/sh\necho "EM_AGENT_MAGUS_COMPLETE"\n')
            executable.chmod(0o755)
            manager = Manager(root / 'jobs')
            request = JobRequest(app_id='magus', xyz=WATER, task='search')
            with patch('tools.science_apps.service.application_executable', return_value=str(executable)):
                job = manager.submit(request)
                await manager.run(job['id'])
                self.assertEqual(manager.detail(job['id'])['status'], 'failed')
                executable.write_text('#!/bin/sh\necho \'{"verified":true,"energy_eV":-123.5,"candidate_count":4,"converged_count":3}\' > result.json\necho EM_AGENT_MAGUS_COMPLETE\n')
                job = manager.submit(request)
                await manager.run(job['id'])
            finished = manager.detail(job['id'])
            self.assertEqual(finished['status'], 'succeeded')
            self.assertEqual(finished['energy_ev'], -123.5)
            self.assertIsNone(finished['energy_hartree'])
            self.assertIn('result.json', [item['name'] for item in finished['files']])
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    def test_xyz_and_method_validation(self):
        for bad in ['1\ncomment\nH nan 0 0', '2\ncomment\nH 0 0 0', '1\ncomment\nXx 0 0 0', WATER + '! command\n']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                prepare_input(JobRequest(app_id='xtb', xyz=bad))
        with self.assertRaises(ValueError):
            prepare_input(JobRequest(app_id='orca', xyz=WATER, method='!unsafe'))
        with self.assertRaises(ValueError):
            prepare_input(JobRequest(app_id='xtb', xyz=WATER, multiplicity=2))

    def test_native_inputs_and_memory(self):
        name, content, args = prepare_input(JobRequest(app_id='orca', xyz=WATER, method='r2SCAN-3c', task='optimize', cores=4, memory_mb=2048))
        self.assertEqual(name, 'input.inp')
        self.assertIn('%maxcore 512', content)
        self.assertIn('! r2SCAN-3c Opt', content)
        self.assertEqual(args, ['input.inp'])
        _, content, args = prepare_input(JobRequest(app_id='gaussian', xyz=WATER, method='HF', basis='STO-3G'))
        self.assertIn('%mem=2048MB', content)
        self.assertIn('#p HF/STO-3G SP', content)
        self.assertEqual(args, [])

    def test_auth_submission_and_download_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Path(folder), 'test-key')
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/science/apps').status_code, 401)
                headers = {'X-Session-API-Key': 'test-key'}
                with patch('tools.science_apps.service.shutil.which', return_value=None):
                    catalog = client.get('/api/science/apps', headers=headers).json()
                    self.assertFalse(any(item['available'] for item in catalog))
                    response = client.post('/api/science/jobs', json={'app_id': 'xtb', 'xyz': WATER}, headers=headers)
                    self.assertEqual(response.status_code, 409)
                self.assertEqual(client.post('/api/science/jobs', json={'app_id': 'xtb', 'xyz': WATER, 'cores': 99}, headers=headers).status_code, 422)
                self.assertEqual(client.get('/api/science/jobs/not-an-id', headers=headers).status_code, 404)

    def test_real_subprocess_success_restart_and_cancel(self):
        async def exercise(root):
            executable = root / 'fake-xtb'
            executable.write_text('#!/bin/sh\necho "TOTAL ENERGY -5.25 Eh"\necho "normal termination of xtb"\necho optimized > xtbopt.xyz\n')
            executable.chmod(0o755)
            manager = Manager(root / 'jobs')
            with patch('tools.science_apps.service.shutil.which', return_value=str(executable)):
                job = manager.submit(JobRequest(app_id='xtb', xyz=WATER))
                await manager.run(job['id'])
            finished = manager.detail(job['id'])
            self.assertEqual(finished['status'], 'succeeded')
            self.assertEqual(finished['energy_hartree'], -5.25)
            self.assertIn('xtbopt.xyz', [f['name'] for f in finished['files']])
            outside = root / 'outside.txt'
            outside.write_text('private')
            (manager.directory(job['id']) / 'leak.txt').symlink_to(outside)
            with self.assertRaises(FileNotFoundError):
                manager.file(job['id'], 'leak.txt')
            with self.assertRaises(FileNotFoundError):
                manager.file(job['id'], '../outside.txt')
            executable.write_text('#!/bin/sh\necho starting\nsleep 30\n')
            with patch('tools.science_apps.service.shutil.which', return_value=str(executable)):
                cancelled = manager.submit(JobRequest(app_id='xtb', xyz=WATER))
                runner = asyncio.create_task(manager.run(cancelled['id']))
                while manager.process is None:
                    await asyncio.sleep(0.01)
                await manager.cancel(cancelled['id'])
                await asyncio.wait_for(runner, 3)
            self.assertEqual(manager.detail(cancelled['id'])['status'], 'cancelled')
            with patch('tools.science_apps.service.shutil.which', return_value=str(executable)):
                pending = manager.submit(JobRequest(app_id='xtb', xyz=WATER))
            recovered = Manager(root / 'jobs')
            self.assertEqual(recovered.detail(pending['id'])['status'], 'failed')
            self.assertEqual(recovered.detail(job['id'])['status'], 'succeeded')
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    def test_orca_parallel_workers_use_single_threaded_blas(self):
        async def exercise(root):
            executable = root / 'fake-orca'
            executable.write_text('#!/bin/sh\necho "threads=$OMP_NUM_THREADS blas=$OPENBLAS_NUM_THREADS"\necho "ORCA TERMINATED NORMALLY"\n')
            executable.chmod(0o755)
            manager = Manager(root / 'jobs')
            with patch('tools.science_apps.service.shutil.which', return_value=str(executable)):
                job = manager.submit(JobRequest(app_id='orca', xyz=WATER, cores=4))
                await manager.run(job['id'])
            detail = manager.detail(job['id'])
            self.assertEqual(detail['status'], 'succeeded')
            self.assertIn('threads=1 blas=1', detail['log'])
            self.assertIn('nprocs 4', manager.file(job['id'], 'input.inp').read_text())
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))

    def test_failure_timeout_and_persisted_files(self):
        async def exercise(root):
            executable = root / 'fake-xtb'
            executable.write_text('#!/bin/sh\necho incomplete\n')
            executable.chmod(0o755)
            manager = Manager(root / 'jobs')
            with patch('tools.science_apps.service.shutil.which', return_value=str(executable)):
                job = manager.submit(JobRequest(app_id='xtb', xyz=WATER))
                await manager.run(job['id'])
                self.assertEqual(manager.detail(job['id'])['status'], 'failed')
                self.assertIsNone(manager.detail(job['id'])['energy_hartree'])
                executable.write_text('#!/bin/sh\nsleep 30\n')
                for legacy in [False, True]:
                    job = manager.submit(JobRequest(app_id='xtb', xyz=WATER))
                    if legacy:
                        job.pop('source')
                    with patch('tools.science_apps.service.TIMEOUT_SECONDS', 0.01):
                        await asyncio.wait_for(manager.run(job['id']), 3)
                    self.assertEqual(manager.detail(job['id'])['error'], 'timeout')
                    self.assertIsNone(manager.process)
            app = create_app(root / 'jobs', 'test-key')
            with TestClient(app) as client:
                response = client.get('/api/science/jobs/' + job['id'] + '/files/input.xyz', headers={'X-Session-API-Key': 'test-key'})
                self.assertEqual(response.status_code, 200)
                self.assertIn('EM-Agent manual calculation', response.text)
                self.assertEqual(client.get('/api/science/jobs/' + job['id'] + '/files/job.json', headers={'X-Session-API-Key': 'test-key'}).status_code, 404)
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))


if __name__ == '__main__':
    unittest.main()
