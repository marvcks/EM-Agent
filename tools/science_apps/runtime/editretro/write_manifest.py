"""Record pinned assets and strictly check user checkpoint against upstream code."""
from importlib.metadata import version
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
source = root / 'source'
sys.path[:0] = [str(source / 'fairseq'), str(source)]
import torch
from fairseq import checkpoint_utils, tasks, utils
import editretro  # Register the upstream task before fairseq upgrades checkpoint args.

EXPECTED_MODEL_SHA256 = '3a537dc6a8992dd61c02993485d8f89c83a7169e63ccb956dab88b949327daf8'


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


assert digest(root / 'checkpoint_best.pt') == EXPECTED_MODEL_SHA256, 'Unexpected model checkpoint'
state = checkpoint_utils.load_checkpoint_to_cpu(str(root / 'checkpoint_best.pt'))
args = state['args']
args.data = str(source / 'interactive/databin')
args.user_dir = str(source / 'editretro')
utils.import_user_module(args)
task = tasks.setup_task(args)
model = task.build_model(args)
loaded = model.load_state_dict(state['model'], strict=True, args=args)
assert not loaded.missing_keys and not loaded.unexpected_keys
assert not getattr(args, 'use_3d_features', False), 'Only the provided 2D checkpoint is supported'
tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z']).decode().split('\0')
assets = {str(Path('source') / name): digest(source / name) for name in tracked if name}
assets.update({name: digest(root / name) for name in ('checkpoint_best.pt', 'uv.lock',
              '.venv/lib/python3.10/site-packages/torch/lib/libtorch_cpu.so')})
manifest = {
    'upstream_url': 'https://github.com/yuqianghan/editretro',
    'upstream_commit': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD']).decode().strip(),
    'python': platform.python_version(), 'device': 'cpu',
    'cpu_patch': 'four Tensor.cuda(device) calls replaced by Tensor.to(device)',
    'elf_patch': 'libtorch_cpu.so GNU_STACK PF_X cleared for container glibc compatibility',
    'model_sha256': EXPECTED_MODEL_SHA256,
    'lock_sha256': assets['uv.lock'], 'files': assets,
    'strict_load': {'missing_keys': loaded.missing_keys, 'unexpected_keys': loaded.unexpected_keys,
                    'state_tensors': len(state['model']), 'vocab_size': len(task.source_dictionary)},
    'packages': {name: version(name) for name in ('torch', 'numpy', 'pandas', 'rdkit', 'SmilesPE', 'fairseq')},
}
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({key: value for key, value in manifest.items() if key != 'files'}, indent=2))
