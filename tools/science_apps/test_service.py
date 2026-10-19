"""Exercise the manual application contract without scientific licenses/models."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from tools.science_apps.service import JobRequest, Manager, create_app, prepare_input

WATER = '3\nwater\nO 0 0 0\nH 0.7586 0 0.5043\nH -0.7586 0 0.5043\n'


class ScienceTests(unittest.TestCase):
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
                job = manager.submit(JobRequest(app_id='xtb', xyz=WATER))
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
