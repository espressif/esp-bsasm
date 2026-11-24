# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Typed intermediate representation shared by the semantic and encoding layers.

The IR is deliberately small and immutable: :class:`Program` is what the
semantic analysis (:mod:`bsasm.sema`) produces and what the encoder
(:mod:`bsasm.encoder`) consumes, so every stage can be tested in isolation.
"""

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import TypedDict

from bsasm.errors import Location

# ---------------------------------------------------------------------------
# Instruction-level enums. Defined first: the statement and program IR below
# reference them.
# ---------------------------------------------------------------------------


class CounterSel(Enum):
    """Which of the two 16-bit counters an opcode operates on."""

    A = 'a'
    B = 'b'


class Halves(Enum):
    """Which bytes of a counter an opcode writes back."""

    FULL = 'full'  # h=1, l=1
    HIGH = 'high'  # h=1, l=0
    LOW = 'low'  # h=0, l=1


class OpcodeKind(Enum):
    """The seven hardware opcodes, see the TRM BitScrambler chapter."""

    ADD = 'add'
    IF = 'if'
    IFN = 'ifn'
    LDCTD = 'ldctd'
    LDCTI = 'ldcti'
    ADDCTI = 'addcti'
    LOOP = 'loop'


class Width(IntEnum):
    """How many bits an instruction reads or writes, in bits."""

    ZERO = 0
    EIGHT = 8
    SIXTEEN = 16
    THIRTYTWO = 32

    @property
    def encoding(self) -> int:
        """The 2-bit CTL_READ_IN / CTL_WR_OUT encoding of this width."""
        return {0: 0, 8: 1, 16: 2, 32: 3}[int(self)]


class EofSide(Enum):
    """Whether trailing-byte counting looks at the input or output side."""

    DOWNSTREAM = 0
    UPSTREAM = 1


class LutWidth(IntEnum):
    """Configured LUT word width, in bits."""

    BITS8 = 8
    BITS16 = 16
    BITS32 = 32

    @property
    def encoding(self) -> int:
        """The 2-bit LUT width setting stored in the header."""
        return {8: 0, 16: 1, 32: 2}[int(self)]


class LoopEndsOn(IntEnum):
    """Termination condition of the LOOP instruction.

    ``EQUAL_OR_GREATER`` is the hardware default: the loop falls through
    once the counter is greater than or equal to the end value. ``EQUAL``
    loops until the counter is exactly equal, which suits counting down.
    """

    EQUAL_OR_GREATER = 0
    EQUAL = 1


class CfgKey(Enum):
    """The 'cfg' meta-instruction keys."""

    PREFETCH = 'prefetch'
    TRAILING_BYTES = 'trailing_bytes'
    EOF_ON = 'eof_on'
    LUT_WIDTH_BITS = 'lut_width_bits'
    LOOP_ENDS_ON = 'loop_ends_on'


# ---------------------------------------------------------------------------
# Statement IR: what the ANTLR visitor (bsasm.builder) records from the
# parse tree, before any interpretation. Operands stay as raw Atom spellings
# with their source locations; bsasm.sema turns these into Instructions.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Atom:
    """A single-token operand (number, source bit or label reference)."""

    text: str
    location: Location


@dataclass(frozen=True, slots=True)
class LabelStmt:
    """A label definition; refers to the next instruction bundle."""

    name: str
    location: Location


@dataclass(frozen=True, slots=True)
class CfgStmt:
    """A 'cfg' meta-instruction; the value spelling is checked semantically."""

    key: CfgKey
    value: Atom
    location: Location


@dataclass(frozen=True, slots=True)
class LutStmt:
    """A 'lut' meta-instruction with its raw value spellings."""

    values: tuple[Atom, ...]
    location: Location


@dataclass(frozen=True, slots=True)
class SetSub:
    """'set out in': route input bits to output bits."""

    out_start: Atom
    out_end: Atom | None
    in_start: Atom
    in_end: Atom | None
    location: Location


@dataclass(frozen=True, slots=True)
class WidthSub:
    """'write N' (is_read=False) or 'read N' (is_read=True)."""

    width: Atom
    is_read: bool
    location: Location


@dataclass(frozen=True, slots=True)
class LoopSub:
    """'LOOPc end_val ctr_add tgt'."""

    counter: CounterSel
    end_val: Atom
    ctr_add: Atom
    target: Atom
    location: Location


@dataclass(frozen=True, slots=True)
class AddSub:
    """'ADDc[H|L] value'."""

    counter: CounterSel
    halves: Halves
    value: Atom
    location: Location


@dataclass(frozen=True, slots=True)
class IfSub:
    """'IF[N] source tgt'."""

    negated: bool
    cond: Atom
    target: Atom
    location: Location


@dataclass(frozen=True, slots=True)
class LdctdSub:
    """'LDCTDc[H|L] value': load counter from immediate."""

    counter: CounterSel
    halves: Halves
    value: Atom
    location: Location


@dataclass(frozen=True, slots=True)
class LdctiSub:
    """'LDCTIc[H|L]': load counter from the mux output."""

    counter: CounterSel
    halves: Halves
    location: Location


@dataclass(frozen=True, slots=True)
class AddctiSub:
    """'ADDCTIc[H|L]': add the mux output to the counter (chip-gated)."""

    counter: CounterSel
    halves: Halves
    location: Location


@dataclass(frozen=True, slots=True)
class JmpSub:
    """'jmp tgt' pseudo-op."""

    target: Atom
    location: Location


@dataclass(frozen=True, slots=True)
class NopSub:
    """'nop' pseudo-op."""

    location: Location


SubInstr = SetSub | WidthSub | LoopSub | AddSub | IfSub | LdctdSub | LdctiSub | AddctiSub | JmpSub | NopSub


@dataclass(frozen=True, slots=True)
class BundleStmt:
    """One instruction bundle: 1..n sub-instructions, one hardware instruction."""

    subs: tuple[SubInstr, ...]
    location: Location


Statement = LabelStmt | CfgStmt | LutStmt | BundleStmt


@dataclass(frozen=True, slots=True)
class MuxSource:
    """One selectable input of the 128-to-1 output muxes.

    ``index`` is the raw CTL_MUX_SEL_n value (0..127). ``ctrsel``,
    ``lutsel`` and ``rel_addr`` are the instruction-wide control bits the
    source requires: ``None`` means the bit may take any value, anything
    else must be encoded verbatim (and must agree across all sources of an
    instruction, which the semantic layer verifies).
    """

    index: int
    text: str
    location: Location
    ctrsel: int | None = None
    lutsel: int | None = None
    rel_addr: bool | None = None


@dataclass(frozen=True, slots=True)
class Opcode:
    """A control-flow opcode of an instruction."""

    kind: OpcodeKind
    location: Location
    counter: CounterSel | None = None
    halves: Halves | None = None
    # Immediate value: ctr_add for ADD, ctr_set for LDCTD, end_val for LOOP.
    # None for IF/IFN/LDCTI/ADDCTI which carry no immediate.
    value: int | None = None
    # Signed 5-bit counter increment of a LOOP opcode.
    ctr_add: int | None = None
    target_ip: int | None = None  # resolved instruction index, 0..7
    cond_source: MuxSource | None = None  # IF/IFN only


# Pseudo-slot used when walking all sources of one instruction: output bits
# 0..31 plus the IF/IFN condition. The condition is packed into the opcode
# src field, not a CTL_MUX_SEL field, and is stored on Opcode.cond_source
# rather than Instruction.mux.
COND_MUX_SLOT = 32

# Size of the hardware instruction RAM. Enforced during analysis so the
# language server reports it too; the encoder keeps a defensive check for
# Program objects built without going through analyze().
MAX_INSTS = 8


def mux_with_condition(mux: dict[int, MuxSource], op: Opcode | None) -> dict[int, MuxSource]:
    """Output-bit routing plus the IF/IFN condition at :data:`COND_MUX_SLOT`."""
    routed = dict(mux)
    if op is not None and op.cond_source is not None:
        routed[COND_MUX_SLOT] = op.cond_source
    return routed


@dataclass(frozen=True, slots=True)
class Instruction:
    """One 257-bit instruction: opcode, mux routing and FIFO widths."""

    location: Location
    # Output-bit routing, keyed 0..31. The IF/IFN condition is
    # Opcode.cond_source, not an extra key in this dict.
    mux: dict[int, MuxSource] = field(default_factory=dict)
    read: Width = Width.ZERO
    write: Width = Width.ZERO
    op: Opcode | None = None


@dataclass(frozen=True, slots=True)
class ProgramMeta:
    """The assembled 'cfg' settings of a program."""

    prefetch: bool = True
    trailing_bytes: int = 0
    eof_on: EofSide = EofSide.UPSTREAM
    lut_width: LutWidth = LutWidth.BITS32
    loop_ends_on: LoopEndsOn = LoopEndsOn.EQUAL_OR_GREATER


@dataclass(frozen=True, slots=True)
class Program:
    """A fully resolved BitScrambler program, ready for encoding."""

    meta: ProgramMeta
    insts: tuple[Instruction, ...]
    lut: tuple[int, ...]
    labels: dict[str, int] = field(default_factory=dict)  # lower-cased name -> instruction index


def check_sources_compatible(first: MuxSource, second: MuxSource) -> str:
    """Return an error message if two sources of one instruction conflict.

    The three checks run in a fixed order and the last conflict wins, which
    reproduces the diagnostics of the original assembler. An empty string
    means the sources can coexist in one instruction.
    """
    message = ''
    if first.rel_addr is not None and second.rel_addr is not None and first.rel_addr != second.rel_addr:
        message = 'Cannot have these inputs as both relative and not-relative in the same instruction'
    if first.ctrsel is not None and second.ctrsel is not None and first.ctrsel != second.ctrsel:
        message = 'Cannot have both counters/LUT as well as reg_mem1 inputs in the same instruction'
    if first.lutsel is not None and second.lutsel is not None and first.lutsel != second.lutsel:
        message = 'With the selected LUT width, the LUT input overlaps the selected counter input'
    return message


class Chipcfg(TypedDict, total=False):
    """Chip capability description, as found in bsasm_targets/*.json."""

    chipname: str
    extra_instruction_groups: list[str]
    support_all: bool
