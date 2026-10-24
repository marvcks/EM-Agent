#!/usr/bin/env python3
"""Clear the legacy Torch 1.12 CPU library's unnecessary executable-stack flag.

New container glibc rejects the wheel's PT_GNU_STACK PF_X bit. This changes only
that ELF program-header bit, preserving the library's instructions and data.
"""
from pathlib import Path
import os
import shutil
import struct
import sys
import tempfile

library = Path(sys.argv[1]) / '.venv/lib/python3.10/site-packages/torch/lib/libtorch_cpu.so'
# uv may hard-link wheels from its shared cache. Modify a private inode only.
if library.stat().st_nlink > 1:
    descriptor, temporary = tempfile.mkstemp(prefix='.torch-cpu-', dir=library.parent)
    os.close(descriptor)
    try:
        shutil.copy2(library, temporary)
        os.replace(temporary, library)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
with library.open('r+b') as stream:
    header = stream.read(64)
    if header[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', header, 18)[0] != 62:
        raise ValueError('Expected the pinned Linux x86_64 Torch CPU ELF library')
    offset = struct.unpack_from('<Q', header, 32)[0]
    entry_size, count = struct.unpack_from('<HH', header, 54)
    found = False
    for index in range(count):
        position = offset + index * entry_size
        stream.seek(position)
        kind, flags = struct.unpack('<II', stream.read(8))
        if kind == 0x6474e551:  # PT_GNU_STACK
            if flags not in (6, 7):
                raise ValueError('Unexpected GNU stack permissions')
            stream.seek(position + 4)
            stream.write(struct.pack('<I', flags & ~1))  # PF_X
            found = True
            print(f'GNU_STACK flags: {flags} -> {flags & ~1}')
    if not found:
        raise ValueError('Expected a GNU_STACK program header')
