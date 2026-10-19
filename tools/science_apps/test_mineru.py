"""MinerU upload, cloud protocol and result safety contracts."""
import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from tools.science_apps.service import JobRequest, Manager, create_app
from tools.science_apps.mineru_runner import extract_result, convert, api, transfer


def bundle(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return stream.getvalue()


class MinerUTests(unittest.TestCase):
    # @spec MINERU-001 — Bounded authenticated document uploads share the queue
    def test_document_upload_and_download_contract(self):
        with tempfile.TemporaryDirectory() as folder, patch('tools.science_apps.service.application_executable', return_value='/missing/mineru'):
            with TestClient(create_app(Path(folder), 'test-key')) as client:
                url = '/api/science/documents?filename=paper.pdf&language=en&method=vlm'
                self.assertEqual(client.post(url, content=b'%PDF-1.4\nExample').status_code, 401)
                headers = {'X-Session-API-Key': 'test-key'}
                response = client.post(url, content=b'%PDF-1.4\n' + b'x' * 140000, headers=headers)
                self.assertEqual(response.status_code, 201, response.text)
                job = response.json()
                self.assertEqual(job['request']['task'], 'textify')
                self.assertEqual(job['request']['document_name'], 'paper.pdf')
                self.assertNotIn('token', json.dumps(job).lower())
                detail = client.get('/api/science/jobs/' + job['id'], headers=headers).json()
                self.assertIn('document.pdf', [f['name'] for f in detail['files']])
                for filename, data in [('bad.pdf', b'not a pdf'), ('../paper.pdf', b'%PDF-1.4'), ('bad.exe', b'%PDF-1.4'), ('bad.docx', b'PKbad')]:
                    result = client.post('/api/science/documents', params={'filename': filename}, content=data, headers=headers)
                    self.assertEqual(result.status_code, 422, result.text)
                with patch('tools.science_apps.service.MAX_DOCUMENT_BYTES', 10):
                    self.assertEqual(client.post(url, content=b'%PDF-' + b'x' * 10, headers=headers).status_code, 413)
                    def chunks():
                        yield b'%PDF-'
                        yield b'x' * 6
                    self.assertEqual(client.post(url, content=chunks(), headers=headers).status_code, 413)
                self.assertEqual(client.post('/api/science/jobs', headers=headers, json={'app_id': 'mineru', 'task': 'textify', 'document_name': 'paper.pdf'}).status_code, 422)
                self.assertEqual(client.post('/api/science/documents?filename=paper.pdf&language=auto', content=b'%PDF-1.4', headers=headers).status_code, 422)

    # @spec MINERU-002 — PDF and Word use MinerU and preserve linked assets
    def test_cloud_workflow_and_no_secrets_in_results(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'document.docx'
            source.write_bytes(bundle({'[Content_Types].xml': '<Types/>', 'word/document.xml': '<document/>'}))
            (root / 'request.json').write_text(json.dumps({'document_name': 'example.docx', 'method': 'vlm', 'language': 'ch', 'enable_formula': True, 'enable_table': True}))
            calls = []
            def api(method, path, payload=None):
                calls.append((method, path, payload))
                if method == 'POST':
                    return {'batch_id': 'batch-1', 'file_urls': ['https://assets.example/upload?secret=signed']}
                return {'extract_result': [{'data_id': 'em-agent', 'state': 'done', 'full_zip_url': 'https://assets.example/result?secret=signed'}]}
            with patch('tools.science_apps.mineru_runner.api', side_effect=api), patch('tools.science_apps.mineru_runner.transfer') as transfer:
                def transfer_file(method, url, destination=None, source=None):
                    if destination:
                        destination.write_bytes(bundle({'paper/full.md': '# Example\n\n![](images/figure.png)', 'paper/images/figure.png': b'png'}))
                transfer.side_effect = transfer_file
                convert(root / 'request.json')
            self.assertEqual(calls[0][2]['files'][0]['name'], 'example.docx')
            self.assertTrue(calls[0][2]['enable_formula'])
            self.assertIn('# Example', (root / 'document.md').read_text())
            with zipfile.ZipFile(root / 'results.zip') as archive:
                self.assertIn('paper/images/figure.png', archive.namelist())
            result = json.loads((root / 'result.json').read_text())
            self.assertTrue(result['verified'])
            self.assertNotIn('signed', (root / 'result.json').read_text())

    # @spec MINERU-003 — Reject unsafe archives and missing Markdown
    def test_result_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / 'results.zip'
            for entries in [{'../escape.md': '# Bad'}, {'full.md': ''}, {'data.json': '{}'}]:
                archive.write_bytes(bundle(entries))
                with self.subTest(entries=entries), self.assertRaises(ValueError):
                    extract_result(archive, root)

    # @spec MINERU-003 — API auth never follows asset URLs; upstream text stays private
    def test_credentials_and_api_failures(self):
        class Response(io.BytesIO):
            pass
        with patch('tools.science_apps.mineru_runner.token', return_value='private-token'), patch('tools.science_apps.mineru_runner.open_request') as opened:
            opened.return_value = Response(b'{"code":-100,"msg":"https://example.com/?secret=signed"}')
            with self.assertRaises(RuntimeError) as failed:
                api('GET', '/test')
            self.assertNotIn('signed', str(failed.exception))
            self.assertEqual(opened.call_args.args[0].get_header('Authorization'), 'Bearer private-token')
            opened.return_value = Response(b'')
            transfer('GET', 'https://example.com/result?secret=signed')
            self.assertIsNone(opened.call_args.args[0].get_header('Authorization'))

    # @spec MINERU-002 — A completion marker alone cannot publish success
    def test_queue_verifies_downloaded_results(self):
        async def exercise(root):
            executable = root / 'parser'
            manager = Manager(root / 'jobs')
            with patch('tools.science_apps.service.application_executable', return_value=str(executable)):
                for complete in [False, True]:
                    executable.write_text('#!/usr/bin/env python3\nimport json,zipfile\nfrom pathlib import Path\n'
                        + ('Path("document.md").write_text("# Parsed")\n'
                           'with zipfile.ZipFile("results.zip","w") as z: z.writestr("full.md","# Parsed")\n' if complete else '')
                        + 'Path("result.json").write_text(json.dumps({"verified":True,"provider":"MinerU","markdown_file":"document.md","bundle_file":"results.zip","markdown_characters":8}))\n'
                        + 'print("EM_AGENT_MINERU_COMPLETE")\n')
                    executable.chmod(0o755)
                    job = manager.submit(JobRequest(app_id='mineru', task='textify', document_name='paper.pdf'), b'%PDF-1.4\nexample')
                    await manager.run(job['id'])
                    self.assertEqual(job['status'], 'succeeded' if complete else 'failed')
                    self.assertEqual('result' in job, complete)
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(exercise(Path(folder)))


if __name__ == '__main__':
    unittest.main()
