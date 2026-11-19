# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Encode a :class:`~bsasm.model.Program` into the .bsbin binary format.

The on-disk format is:
    header (12 bytes = 3 32-bit words, self-describing length)
    instructions (36 bytes each, 257 bits used)
    LUT data (32-bit little-endian words)

The bit packing is byte-for-byte identical to the original assembler: bits
are appended to the stream one by one, LSB-first per field, filling each
byte from its most significant bit down.
"""

import struct

from bsasm.errors import AssemblerError
from bsasm.model import CounterSel
from bsasm.model import Halves
from bsasm.model import Instruction
from bsasm.model import LutWidth
from bsasm.model import MuxSource
from bsasm.model import Opcode
from bsasm.model import OpcodeKind
from bsasm.model import Program
from bsasm.model import check_sources_compatible

# If we have multiple BitScrambler versions, this'll indicate what hardware
# we're expecting to run on. Increase BITSCRAMBLER_BINARY_VER if the on-disk
# format ever changes incompatibly.
BITSCRAMBLER_BINARY_VER = 1
BITSCRAMBLER_HW_REV = 0

HEADER_FMT = '<BBBBHBBHBB'
HEADER_LEN_WORDS = 3
INSTRUCTION_BITS = 257
INSTRUCTION_PAD_BITS = 31  # pad to 36 bytes = 9 32-bit words
MAX_INSTS = 8

# Opcode base patterns (bits 16 upward), see the TRM opcode table.
_OP_BASES = {
    OpcodeKind.ADD: 0x0000000,
    OpcodeKind.IF: 0x0010000,
    OpcodeKind.IFN: 0x0020000,
    OpcodeKind.LDCTD: 0x0030000,
    OpcodeKind.LDCTI: 0x0040000,
    OpcodeKind.ADDCTI: 0x0050000,
    OpcodeKind.LOOP: 0x2000000,
}

# Pseudo-slot in the mux map holding the IF/IFN condition source; its value
# goes into the opcode's src field instead of a CTL_MUX_SEL field.
_COND_SLOT = 32

# Mux inputs that the program never routes default to the fixed-low source.
_DEFAULT_LOW_INPUT = 94  # the 'l' input


class _BitWriter:
    """Appends bit fields to a stream, MSB-of-byte first.

    Deliberately naive (bit by bit): the original assembler worked the same
    way and the resulting byte order is what the hardware loader expects.
    """

    def __init__(self) -> None:
        self._data = bytearray()
        self._cur = 0
        self._pos = 0

    def add_bits(self, value: int, bits: int) -> None:
        v = value
        for _ in range(bits):
            self._cur >>= 1
            if v & 1:
                self._cur |= 0x80
            v >>= 1
            self._pos += 1
            if self._pos == 8:
                self._data.append(self._cur)
                self._cur = 0
                self._pos = 0

    def size(self) -> int:
        """Size of the stream so far, in bits."""
        return len(self._data) * 8 + self._pos

    def to_bytes(self) -> bytes:
        return bytes(self._data)


def encode(program: Program) -> bytes:
    """Serialize a fully analyzed program into .bsbin bytes."""
    insts = program.insts
    if len(insts) > MAX_INSTS:
        raise AssemblerError('Program has more than eight instructions.')

    out = bytearray()
    lut_words = _reformat_lut(program.lut, program.meta.lut_width)

    out += struct.pack(
        HEADER_FMT,
        BITSCRAMBLER_BINARY_VER,  # byte: binary format version
        BITSCRAMBLER_HW_REV,  # byte: expected hardware revision
        HEADER_LEN_WORDS,  # byte: header length in 32-bit words
        len(insts),  # byte: instruction count
        len(lut_words),  # short: LUT length in 32-bit words
        program.meta.lut_width.encoding,  # byte: LUT width setting
        int(program.meta.prefetch),  # byte: prefetch enabled/disabled
        program.meta.trailing_bytes * 8,  # short: trailing *bits* after EOF
        program.meta.eof_on.value,  # byte: eof_on
        int(program.meta.loop_ends_on),  # byte: LOOP end condition
    )

    for inst in insts:
        out += _encode_inst(inst)

    for word in lut_words:
        out += struct.pack('<I', word & 0xFFFFFFFF)

    return bytes(out)


def _reformat_lut(lut: tuple[int, ...], lut_width: LutWidth) -> list[int]:
    """Pack LUT values into 32-bit words for the configured width."""
    values = list(lut)
    if lut_width == LutWidth.BITS8:
        values.extend([0] * (-len(values) % 4))
        return [
            (values[i] & 255) | (values[i + 1] & 255) << 8 | (values[i + 2] & 255) << 16 | (values[i + 3] & 255) << 24
            for i in range(0, len(values), 4)
        ]
    if lut_width == LutWidth.BITS16:
        values.extend([0] * (-len(values) % 2))
        return [(values[i] & 65535) | (values[i + 1] & 65535) << 16 for i in range(0, len(values), 2)]
    return values


def _encode_inst(inst: Instruction) -> bytes:
    bits = _BitWriter()

    mux = dict(inst.mux)
    op = inst.op
    if op is None:
        # An instruction without an opcode defaults to NOP, which is ADDA 0
        # with both counter halves written back.
        op = Opcode(kind=OpcodeKind.ADD, location=inst.location, counter=CounterSel.A, halves=Halves.FULL, value=0)
    if op.cond_source is not None:
        mux[_COND_SLOT] = op.cond_source

    # Instruction-wide control bits: every routed source may require
    # specific values; sources must agree pairwise, which is checked here
    # over all routed inputs exactly like in the original assembler so the
    # conflict diagnostics point at the same two operands.
    # One loop over all 33 slots, exactly like in the original assembler:
    # each routed slot's 7-bit selection goes at its own position in the
    # stream; unrouted ones encode the fixed-low source.
    flags = {'rel_addr': 0, 'ctrsel': 0, 'lutsel': 0}
    for i in range(_COND_SLOT + 1):
        if i not in mux:
            if i < _COND_SLOT:
                # Unrouted mux inputs select the fixed-low source.
                bits.add_bits(_DEFAULT_LOW_INPUT, 7)
            continue
        # Checking each input against each following one reports exactly
        # which two operands clash.
        for j in range(i + 1, _COND_SLOT + 1):
            if j in mux:
                message = check_sources_compatible(mux[i], mux[j])
                if message:
                    raise AssemblerError(_conflict_message(mux[i], mux[j], message))
        src = mux[i]
        if src.rel_addr is not None:
            flags['rel_addr'] = int(src.rel_addr)
        if src.ctrsel is not None:
            flags['ctrsel'] = src.ctrsel
        if src.lutsel is not None:
            flags['lutsel'] = src.lutsel
        if i < _COND_SLOT:
            bits.add_bits(src.index, 7)

    # Opcode field, 26 bits: bit 25 LOOP flag, 24 counter, 23/22 halves,
    # 21..23 target, 16..20 sub-opcode, 0..15 immediate / 0..6 IF source.
    opcode = _OP_BASES[op.kind]
    if op.counter is CounterSel.B:
        opcode |= 1 << 24
    if op.halves is not None and op.halves != Halves.LOW:
        opcode |= 1 << 23  # h
    if op.halves is not None and op.halves != Halves.HIGH:
        opcode |= 1 << 22  # l
    if op.target_ip is not None:
        opcode |= op.target_ip << 21
    if op.kind == OpcodeKind.LOOP:
        opcode |= (op.value or 0) << 5
        opcode |= (op.ctr_add or 0) & 31
    elif op.value is not None:
        opcode |= op.value & 0xFFFF
    if op.cond_source is not None:
        opcode |= op.cond_source.index & 0x7F
    bits.add_bits(opcode, 26)

    bits.add_bits(inst.read.encoding, 2)
    bits.add_bits(inst.write.encoding, 2)
    bits.add_bits(flags['rel_addr'], 1)
    bits.add_bits(flags['ctrsel'], 1)
    bits.add_bits(flags['lutsel'], 1)

    if bits.size() != INSTRUCTION_BITS:
        raise AssemblerError(f'Internal error: instruction size is {bits.size()}!')
    bits.add_bits(0, INSTRUCTION_PAD_BITS)
    return bits.to_bytes()


def _conflict_message(first: MuxSource, second: MuxSource, message: str) -> str:
    first_at = f'{first.location.describe()}: "{first.text}"'
    second_at = f'{second.location.describe()}: "{second.text}"'
    return f'{first_at} and {second_at}: {message}'
