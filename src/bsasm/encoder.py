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
from bsasm.isa import (
    BITSCRAMBLER_BINARY_VER,
    BITSCRAMBLER_HW_REV,
    DEFAULT_LOW_INPUT,
    HEADER_FMT,
    HEADER_LEN_WORDS,
    INSTRUCTION_BITS,
    INSTRUCTION_PAD_BITS,
    OPCODE_BASES,
)
from bsasm.model import (
    COND_MUX_SLOT,
    MAX_INSTS,
    CounterSel,
    Halves,
    Instruction,
    LutWidth,
    Opcode,
    OpcodeKind,
    Program,
    mux_with_condition,
)


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
        # analyze() already rejects this; keep a guard for Program objects
        # assembled by hand rather than through analyze().
        raise AssemblerError(f'Program has more than {MAX_INSTS} instructions.')

    out = bytearray()
    lut_words = reformat_lut(program.lut, program.meta.lut_width)

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


def reformat_lut(lut: tuple[int, ...], lut_width: LutWidth) -> list[int]:
    """Pack LUT values into 32-bit words for the configured width.

    Public because the CLI reports the word count actually stored in the
    binary, which differs from ``len(lut)`` for 8/16-bit widths.
    """
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

    op = inst.op
    if op is None:
        # An instruction without an opcode defaults to NOP, which is ADDA 0
        # with both counter halves written back.
        op = Opcode(kind=OpcodeKind.ADD, location=inst.location, counter=CounterSel.A, halves=Halves.FULL, value=0)
    mux = mux_with_condition(inst.mux, op)

    # One loop over all 33 slots: each routed slot's 7-bit selection goes at
    # its own position in the stream; unrouted ones encode the fixed-low
    # source. Source compatibility was checked in sema (build time).
    flags = {'rel_addr': 0, 'ctrsel': 0, 'lutsel': 0}
    for i in range(COND_MUX_SLOT + 1):
        if i not in mux:
            if i < COND_MUX_SLOT:
                # Unrouted mux inputs select the fixed-low source.
                bits.add_bits(DEFAULT_LOW_INPUT, 7)
            continue
        src = mux[i]
        if src.rel_addr is not None:
            flags['rel_addr'] = int(src.rel_addr)
        if src.ctrsel is not None:
            flags['ctrsel'] = src.ctrsel
        if src.lutsel is not None:
            flags['lutsel'] = src.lutsel
        if i < COND_MUX_SLOT:
            bits.add_bits(src.index, 7)

    # Opcode field, 26 bits: bit 25 LOOP flag, 24 counter, 23/22 halves,
    # 21..23 target, 16..20 sub-opcode, 0..15 immediate / 0..6 IF source.
    opcode = OPCODE_BASES[op.kind]
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
