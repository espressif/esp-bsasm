# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Pin the ISA facts in :mod:`bsasm.isa` and prove they are not duplicated.

``BitScrambler.g4`` owns syntax; ``isa.py`` owns semantics/encoding. These
tests guard both the values themselves and the fact that the per-module
private names are aliases of one object rather than copies that could drift.
"""

from bsasm import encoder, isa, lsp, sema
from bsasm.model import LutWidth, OpcodeKind, Width


def test_modules_share_one_copy_of_each_table() -> None:
    assert sema.INPUTS is isa.INPUTS
    assert sema.INPUTS_CTRSEL_SET is isa.INPUTS_CTRSEL_SET
    assert sema.INPUTS_CTRSEL_CLR is isa.INPUTS_CTRSEL_CLR
    assert sema.INPUT_LUT_BITS is isa.INPUT_LUT_BITS
    assert sema.LUT_STARTS is isa.LUT_STARTS
    assert sema.PREFETCH_VALUES is isa.PREFETCH_VALUES
    assert sema.LUT_WIDTH_VALUES is isa.LUT_WIDTH_VALUES
    assert sema.LOOP_ENDS_ON_VALUES is isa.LOOP_ENDS_ON_VALUES
    assert sema.LUT_MINMAX is isa.LUT_MINMAX
    assert sema.VALID_WIDTHS is isa.VALID_WIDTHS
    assert sema.DEFAULT_CHIPCFG is isa.DEFAULT_CHIPCFG
    assert encoder.OPCODE_BASES is isa.OPCODE_BASES
    assert encoder.DEFAULT_LOW_INPUT == isa.DEFAULT_LOW_INPUT
    assert lsp.CFG_VALUES is isa.CFG_VALUES


def test_mux_source_table_layout() -> None:
    assert len(isa.INPUTS) == 128
    assert isa.INPUTS[0] == '0' and isa.INPUTS[31] == '31'
    assert all(name == '' for name in isa.INPUTS[32:64])
    assert isa.INPUTS[94] == 'l' and isa.INPUTS[95] == 'h'
    assert isa.INPUTS[96] == 'o0' and isa.INPUTS[127] == 'o31'
    assert len(isa.INPUTS_CTRSEL_SET) == 32
    assert isa.INPUTS_CTRSEL_CLR[0] == '32' and isa.INPUTS_CTRSEL_CLR[-1] == '63'
    assert isa.INPUT_LUT_BITS[0] == 'l0' and isa.INPUT_LUT_BITS[-1] == 'l31'
    assert isa.LUT_STARTS == {LutWidth.BITS8: 24, LutWidth.BITS16: 16, LutWidth.BITS32: 0}
    assert isa.DEFAULT_LOW_INPUT == 94


def test_opcode_bases_match_the_trm_table() -> None:
    assert isa.OPCODE_BASES == {
        OpcodeKind.ADD: 0x0000000,
        OpcodeKind.IF: 0x0010000,
        OpcodeKind.IFN: 0x0020000,
        OpcodeKind.LDCTD: 0x0030000,
        OpcodeKind.LDCTI: 0x0040000,
        OpcodeKind.ADDCTI: 0x0050000,
        OpcodeKind.LOOP: 0x2000000,
    }


def test_cfg_and_numeric_domains() -> None:
    assert isa.PREFETCH_VALUES == {'true': True, 'false': False, '1': True, '0': False}
    assert isa.LUT_WIDTH_VALUES == {'8': LutWidth.BITS8, '16': LutWidth.BITS16, '32': LutWidth.BITS32}
    assert isa.LUT_MINMAX == {
        LutWidth.BITS8: (-128, 255),
        LutWidth.BITS16: (-32768, 65535),
        LutWidth.BITS32: (-2147483648, 4294967295),
    }
    assert isa.TRAILING_BYTES_MAX == 8191
    assert isa.VALID_WIDTHS == (Width.ZERO, Width.EIGHT, Width.SIXTEEN, Width.THIRTYTWO)
    assert set(isa.CFG_VALUES) == {
        'prefetch',
        'trailing_bytes',
        'eof_on',
        'lut_width_bits',
        'loop_ends_on',
    }


def test_bsbin_layout() -> None:
    assert isa.BITSCRAMBLER_BINARY_VER == 1
    assert isa.BITSCRAMBLER_HW_REV == 0
    assert isa.HEADER_FMT == '<BBBBHBBHBB'
    assert isa.HEADER_LEN_WORDS == 3
    assert isa.INSTRUCTION_BITS == 257
    assert isa.INSTRUCTION_PAD_BITS == 31
