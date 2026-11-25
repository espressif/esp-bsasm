# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Instruction-set facts for the BitScrambler assembler.

``BitScrambler.g4`` is the single source of truth for *syntax*: token
spellings and statement shapes. This module is the single source of truth for
the *semantics and encoding* the grammar cannot express - opcode bit
patterns, the 128-entry mux source table, cfg value domains and ranges, and
the ``.bsbin`` binary layout. Everything here is plain data, so it can be
exported to JSON when a second (e.g. JavaScript) implementation needs the
same facts instead of re-deriving them from Python code.

Deliberately *not* here:

* ``COND_MUX_SLOT`` / ``MAX_INSTS`` live in :mod:`bsasm.model` next to the IR
  dataclasses they describe. Moving them here would make ``model`` import
  ``isa`` while ``isa`` imports ``model``'s enums - a cycle.
* The 2-bit width encodings stay on ``Width.encoding`` / ``LutWidth.encoding``
  in :mod:`bsasm.model`, for the same reason.
* The mnemonic-to-(counter, halves) table stays in :mod:`bsasm.builder`:
  its keys are token IDs generated from the grammar, not ISA values.

Every consumer imports these objects directly - no copies and no private-name
aliases. ``tests/test_isa.py`` pins both the values and that single ownership.
"""

from bsasm.model import LoopEndsOn, LutWidth, OpcodeKind, Width

# ---------------------------------------------------------------------------
# .bsbin binary layout
# ---------------------------------------------------------------------------

# Increase BITSCRAMBLER_BINARY_VER if the on-disk format ever changes
# incompatibly; BITSCRAMBLER_HW_REV names the hardware revision we expect.
BITSCRAMBLER_BINARY_VER = 1
BITSCRAMBLER_HW_REV = 0

HEADER_FMT = '<BBBBHBBHBB'
HEADER_LEN_WORDS = 3
INSTRUCTION_BITS = 257
INSTRUCTION_PAD_BITS = 31  # pad to 36 bytes = 9 32-bit words

# Mux inputs the program never route default to the fixed-low source ('l').
DEFAULT_LOW_INPUT = 94  # the 'l' input

# Opcode base patterns (bits 16 upward), see the TRM opcode table.
OPCODE_BASES = {
    OpcodeKind.ADD: 0x0000000,
    OpcodeKind.IF: 0x0010000,
    OpcodeKind.IFN: 0x0020000,
    OpcodeKind.LDCTD: 0x0030000,
    OpcodeKind.LDCTI: 0x0040000,
    OpcodeKind.ADDCTI: 0x0050000,
    OpcodeKind.LOOP: 0x2000000,
}

# ---------------------------------------------------------------------------
# Mux source table (CTL_MUX_SEL values), see the TRM mux source table
# ---------------------------------------------------------------------------

# The 32 empty strings are the 32..63 region, multiplexed between reg_mem1,
# the counters and the LUT output by ctrsel/lutsel: a bare '+a' operand parses
# to the empty name and lands on input 32, exactly as in the original assembler.
# fmt: off
INPUTS = (
    *tuple(str(i) for i in range(32)),   # 0..31: input FIFO register (reg_mem0)
    *([''] * 32),                        # 32..63: multiplexed region
    'bl<=o0', 'bl>o0', 'bl=o0', 'bl<=o8', 'bl>o8', 'bl=o8', 'bl<=o16', 'bl>o16',
    'bl=o16', 'bl<=o24', 'bl>o24', 'bl=o24', 'bh<=o0', 'bh>o0', 'bh=o0', 'bh<=o8',
    'bh>o8', 'bh=o8', 'bh<=o16', 'bh>o16', 'bh=o16', 'bh<=o24', 'bh>o24', 'bh=o24',
    'b<=o0', 'b>o0', 'b=o0', 'b<=o16', 'b>o16', 'b=o16', 'l', 'h',   # 64..95: comparators + fixed 0/1
    *tuple(f'o{i}' for i in range(32)),  # 96..127: previous output register
)
# fmt: on
INPUTS_CTRSEL_SET = tuple(f'a{i}' for i in range(16)) + tuple(f'b{i}' for i in range(16))
INPUTS_CTRSEL_CLR = tuple(str(i) for i in range(32, 64))
INPUT_LUT_BITS = tuple(f'l{i}' for i in range(32))

# Where in the multiplexed region the LUT outputs live, per LUT width.
LUT_STARTS = {LutWidth.BITS8: 24, LutWidth.BITS16: 16, LutWidth.BITS32: 0}

# ---------------------------------------------------------------------------
# cfg / numeric domains
# ---------------------------------------------------------------------------

# Allowed value spellings and ranges, as in the original assembler's
# meta_inst_defs. 'cfg' value spellings are matched as strings, so '08' is
# rejected just like before.
PREFETCH_VALUES = {'true': True, 'false': False, '1': True, '0': False}
LUT_WIDTH_VALUES = {'8': LutWidth.BITS8, '16': LutWidth.BITS16, '32': LutWidth.BITS32}
LOOP_ENDS_ON_VALUES = {'equal': LoopEndsOn.EQUAL, 'equal_or_greater': LoopEndsOn.EQUAL_OR_GREATER}

# Range of a single LUT value, per LUT width. (The 16-bit maximum was
# 65537 in the original assembler, letting 65536/65537 wrap around to 0/1.)
LUT_MINMAX = {
    LutWidth.BITS8: (-128, 255),
    LutWidth.BITS16: (-32768, 65535),
    LutWidth.BITS32: (-2147483648, 4294967295),
}

# 'trailing_bytes' is stored in the header as trailing *bits* in a 16-bit
# field, so 8191 bytes (65528 bits) is the largest value that fits. (The
# original accepted 8192 and crashed inside struct.pack.)
TRAILING_BYTES_MAX = 8191

VALID_WIDTHS = (Width.ZERO, Width.EIGHT, Width.SIXTEEN, Width.THIRTYTWO)

# Optional opcodes, keyed by opcode and valued by the name a caller passes to
# enable that family of mnemonics (CLI: ``--enable-extra-inst``; API:
# ``enabled_extra_inst``). Several opcodes may share one name. By
# default nothing is enabled; the caller passes the names its target supports.
OPTIONAL_OPCODES: dict[OpcodeKind, str] = {
    OpcodeKind.ADDCTI: 'addcti',
}
OPTIONAL_INSTRUCTION_GROUPS: frozenset[str] = frozenset(OPTIONAL_OPCODES.values())

# Candidate value spellings offered by the editor after each cfg key.
# ``trailing_bytes`` takes an arbitrary integer, so nothing is enumerable.
# The keys are cross-checked against the grammar's cfg tokens in the tests.
CFG_VALUES: dict[str, tuple[str, ...]] = {
    'prefetch': ('true', 'false', '1', '0'),
    'trailing_bytes': (),
    'eof_on': ('upstream', 'downstream'),
    'lut_width_bits': ('8', '16', '32'),
    'loop_ends_on': ('equal', 'equal_or_greater'),
}
