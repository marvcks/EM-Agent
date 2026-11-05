"""Fixed user-supplied ResNet18 classifier; CPU-only, no downloads or training."""
import base64
import binascii
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import sys
import zipfile

ROOT = Path('/opt/em-agent-tools/image-cnn')
MODEL_SHA256 = 'fe02a72c0013edfa32b6075884b1486753fcf56dd1d9fd6cd8c94dcc74085299'
MAX_IMAGE_BYTES = 512 * 1024
LAYERS = ['Conv1', 'Layer1', 'Layer2', 'Layer3', 'Layer4']
PREPROCESSING = 'grayscale-224-rgb-normalize-0.5'


def image_cnn_available(root=ROOT):
    return (os.access(root / '.venv/bin/python', os.X_OK)
            and all((root / p).is_file() for p in ['manifest.json', 'model.pth', 'example.png']))


# @spec IC-001 — Bounded PNG input with dimensions checked before decoding.
def decode_image(encoded):
    try:
        if not encoded or len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
            raise ValueError
        data = base64.b64decode(encoded, validate=True)
        if (len(data) > MAX_IMAGE_BYTES or len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n'
                or data[8:16] != b'\x00\x00\x00\rIHDR'):
            raise ValueError
        width, height = struct.unpack('>II', data[16:24])
        if not (32 <= width <= 5000 and 32 <= height <= 5000 and width * height <= 20_000_000):
            raise ValueError
        return data
    except (ValueError, binascii.Error, struct.error):
        raise ValueError('invalid_image_cnn_input') from None


def validate_image_cnn(request):
    if (request.task != 'classification' or request.method != 'ResNet18'
            or request.xyz or request.smiles or request.basis or request.document_name
            or request.charge or request.multiplicity != 1
            or request.image_example == bool(request.image_base64)):
        raise ValueError('invalid_image_cnn_input')
    if not request.image_example:
        decode_image(request.image_base64)


def verified_image_cnn(result, request, directory):
    p = result.get('probability_class1')
    files = [f'gradcam_{name}.png' for name in LAYERS]
    return (result.get('verified') is True and result.get('app_id') == 'image-cnn'
            and result.get('model_sha256') == MODEL_SHA256
            and result.get('threshold') == 0.5
            and result.get('preprocessing') == PREPROCESSING
            and result.get('gradcam_target') == 'positive-logit'
            and type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1
            and type(result.get('predicted_class')) is int
            and result['predicted_class'] == int(p >= 0.5)
            and result.get('gradcam_files') == files
            and all((directory / name).is_file() and not (directory / name).is_symlink()
                    and (directory / name).stat().st_size > 0
                    for name in [*files, 'input.png', 'results.zip']))


# @spec IC-002 — Strict checkpoint, original training preprocessing, positive-logit Grad-CAM.
def run(request, root=ROOT):
    import numpy as np
    from PIL import Image
    import torch
    from torchvision.models import resnet18
    from torchvision import transforms
    torch.set_num_threads(request.cores)
    torch.set_num_interop_threads(1)
    validate_image_cnn(request)
    manifest = json.loads((root / 'manifest.json').read_text())
    if (hashlib.sha256((root / 'model.pth').read_bytes()).hexdigest() != MODEL_SHA256
            or manifest['model_sha256'] != MODEL_SHA256
            or manifest['lock_sha256'] != hashlib.sha256((root / 'uv.lock').read_bytes()).hexdigest()):
        raise ValueError('Runtime/model integrity check failed')
    data = (root / 'example.png').read_bytes() if request.image_example else decode_image(request.image_base64)
    if request.image_example and hashlib.sha256(data).hexdigest() != manifest['example_sha256']:
        raise ValueError('Example integrity check failed')
    decode_image(base64.b64encode(data).decode())
    with Image.open(io.BytesIO(data)) as check:
        check.verify()
    with Image.open(io.BytesIO(data)) as original:
        if original.format != 'PNG' or getattr(original, 'n_frames', 1) != 1:
            raise ValueError('Expected a single-frame PNG')
        if 'A' in original.getbands() or 'transparency' in original.info:
            rgba = original.convert('RGBA')
            background = Image.new('RGBA', rgba.size, 'white')
            original_rgb = Image.alpha_composite(background, rgba).convert('RGB')
        else:
            original_rgb = original.convert('RGB')
        original_rgb.save('input.png')
        image = original_rgb.convert('L').resize((224, 224)).convert('RGB')
    model = resnet18(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, 1)
    state = torch.load(root / 'model.pth', map_location='cpu', weights_only=True)
    state = {k.removeprefix('module.'): v for k, v in state.items()}
    model.load_state_dict(state, strict=True)
    model.eval()
    # Avoid in-place modification of hook outputs, particularly the Conv1 activation.
    for module in model.modules():
        if isinstance(module, torch.nn.ReLU):
            module.inplace = False
    activations = {}
    handles = []
    for name, module in zip(LAYERS, [model.conv1, model.layer1, model.layer2, model.layer3, model.layer4]):
        handles.append(module.register_forward_hook(lambda m, i, out, name=name: activations.__setitem__(name, out)))
    transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize([0.5]*3, [0.5]*3)])
    try:
        logit = model(transform(image).unsqueeze(0)).squeeze()
        probability = float(torch.sigmoid(logit).detach())
        if not math.isfinite(probability):
            raise ValueError('Nonfinite model output')
        grads = torch.autograd.grad(logit, [activations[name] for name in LAYERS])
        for name, gradient in zip(LAYERS, grads):
            cam = (gradient.mean(dim=(2, 3), keepdim=True) * activations[name]).sum(1).relu()
            cam = torch.nn.functional.interpolate(cam.unsqueeze(1), (224, 224), mode='bilinear', align_corners=False)[0,0].detach().numpy()
            if not np.isfinite(cam).all():
                raise ValueError('Nonfinite Grad-CAM')
            span = float(cam.max() - cam.min())
            cam = (cam - cam.min()) / span if span > 0 else np.zeros_like(cam)
            heat = np.stack([cam, np.zeros_like(cam), 1-cam], axis=-1)
            overlay = np.clip(np.array(image)*0.6 + heat*255*0.4, 0, 255).astype('uint8')
            Image.fromarray(overlay).save(f'gradcam_{name}.png')
    finally:
        for handle in handles:
            handle.remove()
    result = {'verified': True, 'app_id': 'image-cnn', 'model_sha256': MODEL_SHA256,
              'model_id': 'cla_5/resnet18_opt1', 'probability_class1': probability,
              'predicted_class': int(probability >= 0.5), 'threshold': 0.5,
              'preprocessing': PREPROCESSING, 'gradcam_target': 'positive-logit',
              'gradcam_files': [f'gradcam_{name}.png' for name in LAYERS],
              'note': 'Experimental uncalibrated classification. Two datasets reuse IDs with different labels; checkpoint-to-data-version mapping, physical class order, units and phase identities are unconfirmed. Grad-CAM targets positive-class logit, not causal interpretation.'}
    Path('result.json').write_text(json.dumps(result, indent=2) + '\n')
    with zipfile.ZipFile('results.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ['request.json', 'input.png', 'result.json', *result['gradcam_files']]:
            archive.write(name)
    print(json.dumps(result, indent=2))
    print('EM_AGENT_IMAGE_CNN_COMPLETE')


if __name__ == '__main__':
    from types import SimpleNamespace
    run(SimpleNamespace(**json.loads(Path(sys.argv[1]).read_text())))
