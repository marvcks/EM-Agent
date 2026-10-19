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
