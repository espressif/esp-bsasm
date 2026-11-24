# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Pin the ISA facts in :mod:`bsasm.isa` and the bit layout they encode.

``BitScrambler.g4`` owns syntax; ``isa.py`` owns semantics/encoding. These
tests guard the table values themselves, that per-module private names are
aliases of one object rather than copies that could drift, and that the fields
of an assembled binary match the TRM BitScrambler chapter. Byte-exact goldens
pin agreement with ESP-IDF's assembler; the bit-layout checks pin agreement
with the hardware documentation.
"""

from bsasm import assemble, encode, encoder, isa, lsp, sema
from bsasm.isa import INPUTS
from bsasm.model import LutWidth, OpcodeKind, Width

# --- ISA tables and constants ---


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


# --- Encoded bit layout vs the TRM ---


def _bits(data: bytes, off: int, length: int) -> int:
    # Fields are packed LSB-first per field into the byte stream, matching
    # tools/test_bsasm/test_bsasm.py's decoder.
    ret = 0
    for i in range(length):
        if data[(off + i) // 8] & (1 << ((off + i) % 8)):
            ret |= 1 << i
    return ret


def _opcode(binary: bytes, index: int = 0) -> int:
    inst = binary[12 + index * 36 : 12 + (index + 1) * 36]
    return _bits(inst, 224, 26)


def test_opcode_bit_layout() -> None:
    binary = encode(
        assemble(
            'ldctda:\nldctda 0x1234\nloopb 100 -3 ldctda\nadda 5\naddbh 6\naddbl 7\naddb 8\naddah 9\nif b0 ldctda\n'
        )
    )
    # LDCTDA: sub=3 (bits 16..20), counter A (bit 24 = 0), both halves
    # (bits 23/22), immediate in bits 0..15.
    op = _opcode(binary, 0)
    assert (op >> 25) & 1 == 0
    assert (op >> 24) & 1 == 0
    assert (op >> 23) & 1 == 1
    assert (op >> 22) & 1 == 1
    assert ((op >> 16) & 0x1F) == 3
    assert (op & 0xFFFF) == 0x1234
    # LOOPB: bit 25 set, counter B (bit 24), target in bits 21..23,
    # end_val in bits 5..20, signed 5-bit ctr_add in bits 0..4.
    op = _opcode(binary, 1)
    assert (op >> 25) & 1 == 1
    assert (op >> 24) & 1 == 1
    assert ((op >> 21) & 7) == 0
    assert ((op >> 5) & 0xFFFF) == 100
    assert (op & 0x1F) == (-3 & 31)
    # ADD c/h/l matrix: (index, counter B, high half, low half).
    for idx, (c, high, low) in {2: (0, 1, 1), 3: (1, 1, 0), 4: (1, 0, 1), 5: (1, 1, 1), 6: (0, 1, 0)}.items():
        op = _opcode(binary, idx)
        assert ((op >> 16) & 0x1F) == 0
        assert (op >> 24) & 1 == c
        assert (op >> 23) & 1 == high
        assert (op >> 22) & 1 == low
    # IF b0: sub=1, source = counter B bit 0 (input 48), no h/l bits.
    op = _opcode(binary, 7)
    assert ((op >> 16) & 0x1F) == 1
    assert (op & 0x7F) == 48
    assert (op >> 24) & 1 == 0


def test_ifn_and_jmp_sources() -> None:
    binary = encode(assemble('ldctda:\nifn h ldctda\njmp ldctda\n'))
    # IFN: sub=2, 'h' is the fixed-high comparator at input 95.
    op = _opcode(binary, 0)
    assert ((op >> 16) & 0x1F) == 2
    assert (op & 0x7F) == 95
    # JMP is an IF on the same fixed-high input (TRM: "IF 95,tgt").
    op = _opcode(binary, 1)
    assert ((op >> 16) & 0x1F) == 1
    assert (op & 0x7F) == 95


def test_control_flags_and_widths() -> None:
    inst = encode(assemble('cfg lut_width_bits 16\nread 16, write 32, set 0 5+a\n'))[12:48]
    assert _bits(inst, 250, 2) == 2  # CTL_READ_IN = 16 bits
    assert _bits(inst, 252, 2) == 3  # CTL_WR_OUT = 32 bits
    assert _bits(inst, 254, 1) == 1  # CTL_MUX_REL
    assert _bits(inst, 255, 1) == 0  # CTL_CTR_SRC_SEL
    assert _bits(inst, 256, 1) == 0  # CTL_LUT_SRC_SEL
    assert _bits(inst, 0, 7) == 5


def test_mux_source_regions() -> None:
    # LUT placement per TRM: for width N, l{n} sits at input 64 - N + n.
    for width, base in ((32, 32), (16, 48), (8, 56)):
        inst = encode(assemble(f'cfg lut_width_bits {width}\nset 0 l0, set 1 l{width - 1}\n'))[12:48]
        assert _bits(inst, 0, 7) == base
        assert _bits(inst, 7, 7) == base + width - 1
    # Counters: 32..47 = counter A, 48..63 = counter B (TRM table).
    inst = encode(assemble('set 0 a15, set 1 b0\n'))[12:48]
    assert _bits(inst, 0, 7) == 47
    assert _bits(inst, 7, 7) == 48
    assert _bits(inst, 255, 1) == 1
    # Previous output register: 96..127.
    inst = encode(assemble('set 0 o31\n'))[12:48]
    assert _bits(inst, 0, 7) == 127


def test_comparator_table_order() -> None:
    # The 30 comparator inputs in TRM table order: bl/bh across
    # o0/o8/o16/o24 and b across o0/o16, each with <=, >, =.
    groups = (
        ('bl', ('o0', 'o8', 'o16', 'o24')),
        ('bh', ('o0', 'o8', 'o16', 'o24')),
        ('b', ('o0', 'o16')),
    )
    expected = [f'{part}{op}{off}' for part, offs in groups for off in offs for op in ('<=', '>', '=')]
    expected += ['l', 'h']  # fixed low/high
    assert list(INPUTS[64:96]) == expected
