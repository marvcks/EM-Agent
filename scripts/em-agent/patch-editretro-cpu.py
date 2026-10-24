#!/usr/bin/env python3
"""Apply the device-only inference patch to pinned upstream EditRetro source."""
from pathlib import Path
import sys

UPSTREAM_COMMIT = '8e5848e899b4e8ec6be970b9be04881042ed7b55'


def patch(root):
    target = root / 'editretro/models/editretro_nat.py'
    text = target.read_bytes().decode('utf-8')
    replacements = {
        'ranki.long().cuda(rank1.device)': 'ranki.long().to(rank1.device)',
        'mask_ins_pred_reshape.long().cuda(rank1.device)': 'mask_ins_pred_reshape.long().to(rank1.device)',
        'word_ins_pred_reshape.long().cuda(rank1.device)': 'word_ins_pred_reshape.long().to(rank1.device)',
        'word_ins_score_reshape.float().cuda(score1.device)': 'word_ins_score_reshape.float().to(score1.device)',
    }
    for old, new in replacements.items():
        if text.count(old) == 1 and new not in text:
            text = text.replace(old, new)
        elif old not in text and text.count(new) == 1:
            continue
        else:
            raise ValueError('Unexpected upstream source: ' + old)
    target.write_bytes(text.encode('utf-8'))


if __name__ == '__main__':
    patch(Path(sys.argv[1]))
