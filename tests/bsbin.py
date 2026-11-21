# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Decode a .bsbin into the dict shape the sidecar ``.json`` files use.

Field names and unpacking rules match ESP-IDF ``tools/test_bsasm/test_bsasm.py``,
which is also where the JSON expect files were produced.
"""

import struct
from pathlib import Path
from typing import TypedDict


class DecompInstOp(TypedDict, total=False):
    val: int
    op: str
    src: int
    tgt: int
    end_val: int
    ctr_add: int
    ctr_set: int


class DecompInst(TypedDict, total=False):
    mux_val: list[int]
    opcode: DecompInstOp
    read_in: int
    wr_out: int
    mux_rel: int
    ctr_src_sel: int
    lut_src_sel: int


class UnpackedBinary(TypedDict, total=False):
    binary_ver: int
    hw_rev: int
    hdr_len: int
    inst_ct: int
    lut_size_words: int
    lut_width_bits: int
    prefetch: int
    trailing_bits: int
    eof_on: int
    # Historical JSON key for the last header byte (loop_ends_on).
    padding: int
    inst: list[DecompInst]
    lut: list[int]


def _bit_from_inst(data: tuple[int, ...], off: int) -> int:
    return data[off // 8] & (1 << (off & 0x7))


def _bits_from_inst(data: tuple[int, ...], off: int, length: int) -> int:
    ret = 0
    for i in range(length):
        if _bit_from_inst(data, off + i) != 0:
            ret |= 1 << i
    return ret


def decode_inst(data: tuple[int, ...]) -> DecompInst:
    mux_val = [_bits_from_inst(data, i * 7, 7) for i in range(32)]
    opcode = _bits_from_inst(data, 224, 26)
    op: DecompInstOp = {'val': opcode}
    if opcode & (1 << 25):
        op['op'] = 'LOOPB' if (opcode & (1 << 24)) else 'LOOPA'
        op['tgt'] = (opcode >> 21) & 7
        op['end_val'] = (opcode >> 5) & 0xFFFF
        op['ctr_add'] = opcode & 31
    else:
        sub = (opcode >> 16) & 0x1F
        if sub == 1 or sub == 2:
            op['op'] = 'IF' if (sub == 1) else 'IFN'
            op['src'] = opcode & 0x7F
            op['tgt'] = (opcode >> 21) & 7
        else:
            fl = 'B' if (opcode & (1 << 24)) else 'A'
            hl = (opcode >> 22) & 3
            if hl == 3:
                pass  # don't add HL
            elif hl == 2:
                fl += 'H'
            elif hl == 1:
                fl += 'L'
            elif hl == 0:
                fl += 'XX'  # shouldn't happen

            if sub == 0:
                op['op'] = 'ADD' + fl
                op['ctr_add'] = opcode & 0xFFFF
            elif sub == 3:
                op['op'] = 'LDCTD' + fl
                op['ctr_set'] = opcode & 0xFFFF
            elif sub == 4:
                op['op'] = 'LDCTI' + fl
            elif sub == 5:
                op['op'] = 'ADDCTI' + fl
    return {
        'mux_val': mux_val,
        'opcode': op,
        'read_in': _bits_from_inst(data, 250, 2),
        'wr_out': _bits_from_inst(data, 252, 2),
        'mux_rel': _bits_from_inst(data, 254, 1),
        'ctr_src_sel': _bits_from_inst(data, 255, 1),
        'lut_src_sel': _bits_from_inst(data, 256, 1),
    }


def unpack_binary(filename: Path) -> UnpackedBinary:
    data = filename.read_bytes()
    ud = struct.unpack('<BBBBHBBHBB', data[:12])
    hdr_len: int = ud[2]
    inst_ct: int = ud[3]
    lut_size_words: int = ud[4]
    unpacked: UnpackedBinary = {
        'binary_ver': ud[0],
        'hw_rev': ud[1],
        'hdr_len': hdr_len,
        'inst_ct': inst_ct,
        'lut_size_words': lut_size_words,
        'lut_width_bits': ud[5],
        'prefetch': ud[6],
        'trailing_bits': ud[7],
        'eof_on': ud[8],
        'padding': ud[9],
    }
    off = hdr_len * 4
    inst: list[DecompInst] = []
    for _ in range(inst_ct):
        inst.append(decode_inst(struct.unpack_from('B' * 36, data, off)))
        off += 36
    unpacked['inst'] = inst
    unpacked['lut'] = list(struct.unpack_from('<' + 'L' * lut_size_words, data, off))
    return unpacked


def assert_expected_subset(decoded: object, expected: object, path: str) -> None:
    """JSON-sidecar comparison: every key in ``expected`` must match ``decoded``.

    Extra keys in ``decoded`` are ignored. Lists are compared over the length
    of the JSON value, matching IDF's ``TestAssembler.compare``.
    """
    assert type(decoded) is type(expected), f' Diverging types between json and decoded obj: {path}'
    if isinstance(expected, dict):
        assert isinstance(decoded, dict)
        for key, value in expected.items():
            assert key in decoded, f' Key not found in decoded output: {path}.{key}'
            assert_expected_subset(decoded[key], value, f'{path}.{key}')
        return
    if isinstance(expected, list):
        assert isinstance(decoded, list)
        for i, value in enumerate(expected):
            assert_expected_subset(decoded[i], value, f'{path}[{i}]')
        return
    assert expected == decoded, f'Items different: {path} (json {expected} decoded {decoded})'
