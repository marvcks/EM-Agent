import base64
import json
from pathlib import Path
import tempfile
import unittest
from tools.science_apps.service import JobRequest, prepare_input


class ImageCNNTests(unittest.TestCase):
    # @spec IC-001 — Image input never falls through to molecular input adapters.
    def test_example_and_strict_image_contract(self):
        req = JobRequest(app_id='image-cnn', task='classification', image_example=True)
        name, content, args = prepare_input(req)
        self.assertEqual((name, args), ('request.json', ['request.json']))
        self.assertEqual(json.loads(content)['method'], 'ResNet18')
        for changes in [{'task': 'energy'}, {'xyz': 'water'}, {'smiles': 'CC'},
                        {'charge': 1}, {'image_example': False},
                        {'image_base64': 'not base64'}, {'basis': 'HF'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                prepare_input(req.model_copy(update=changes))
        from tools.science_apps.image_cnn_runner import decode_image
        for data in [b'invalid', b'\x89PNG\r\n\x1a\n' + b'\x00' * 40]:
            with self.assertRaises(ValueError):
                decode_image(base64.b64encode(data).decode())

    def test_large_request_limit_is_reserved_for_images(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from tools.science_apps.service import create_app
        # Valid header with a bounded body; pixel decoding still occurs in runner.
        import struct
        data = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + struct.pack('>II', 224, 224) + b'\x00' * 110000
        payload = {'app_id':'image-cnn', 'task':'classification', 'image_base64':base64.b64encode(data).decode()}
        with tempfile.TemporaryDirectory() as d, patch('tools.science_apps.service.application_executable', return_value='/missing/tool'):
            with TestClient(create_app(Path(d), 'test-key')) as client:
                headers = {'X-Session-API-Key':'test-key'}
                self.assertEqual(client.post('/api/science/jobs', json=payload, headers=headers).status_code, 201)
                payload['app_id'] = 'xtb'
                self.assertEqual(client.post('/api/science/jobs', json=payload, headers=headers).status_code, 413)
                payload['app_id'] = 'image-cnn'
                payload['image_base64'] = 'x' * 730000
                self.assertEqual(client.post('/api/science/jobs', json=payload, headers=headers).status_code, 413)

    # @spec IC-003 — Only complete finite, model-bound predictions are successful.
    def test_result_gate(self):
        from tools.science_apps.image_cnn_runner import verified_image_cnn, MODEL_SHA256
        req = JobRequest(app_id='image-cnn', task='classification', image_example=True)
        result = dict(verified=True, app_id='image-cnn', model_sha256=MODEL_SHA256,
                      probability_class1=0.8, predicted_class=1, threshold=0.5,
                      preprocessing='grayscale-224-rgb-normalize-0.5',
                      gradcam_target='positive-logit', gradcam_files=[f'gradcam_{x}.png' for x in ['Conv1','Layer1','Layer2','Layer3','Layer4']])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            for name in [*result['gradcam_files'], 'input.png', 'results.zip']:
                (p/name).write_bytes(b'content')
            self.assertTrue(verified_image_cnn(result, req, p))
            for changes in [{'probability_class1': float('nan')}, {'predicted_class': 0},
                            {'model_sha256': 'wrong'}, {'gradcam_files': []}, {'threshold': 0.6}]:
                self.assertFalse(verified_image_cnn({**result, **changes}, req, p))
            (p/'gradcam_Layer4.png').unlink()
            self.assertFalse(verified_image_cnn(result, req, p))
