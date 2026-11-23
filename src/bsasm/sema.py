# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Semantic analysis: statements in, :class:`~bsasm.model.Program` out.

This module owns every check that needs a readable diagnostic: numeric
ranges and spellings, label resolution, the ctrsel/lutsel/rel_addr
compatibility rules, per-chip instruction gating and the per-bundle
'unusually many opcodes' checks. The behaviour mirrors the original
assembler's four passes; the differences are deliberate and documented in
the repository README.md.
"""

from dataclasses import dataclass
from dataclasses import replace

from bsasm.errors import AssemblerSyntaxError
from bsasm.errors import Location
from bsasm.model import COND_MUX_SLOT
from bsasm.model import AddctiSub
from bsasm.model import AddSub
from bsasm.model import Atom
from bsasm.model import BundleStmt
from bsasm.model import CfgKey
from bsasm.model import CfgStmt
from bsasm.model import Chipcfg
from bsasm.model import CounterSel
from bsasm.model import EofSide
from bsasm.model import Halves
from bsasm.model import IfSub
from bsasm.model import Instruction
from bsasm.model import JmpSub
from bsasm.model import LabelStmt
from bsasm.model import LdctdSub
from bsasm.model import LdctiSub
from bsasm.model import LoopEndsOn
from bsasm.model import LoopSub
from bsasm.model import LutStmt
from bsasm.model import LutWidth
from bsasm.model import MuxSource
from bsasm.model import NopSub
from bsasm.model import Opcode
from bsasm.model import OpcodeKind
from bsasm.model import Program
from bsasm.model import ProgramMeta
from bsasm.model import SetSub
from bsasm.model import Statement
from bsasm.model import SubInstr
from bsasm.model import Width
from bsasm.model import WidthSub
from bsasm.model import check_sources_compatible
from bsasm.model import mux_with_condition

# The mux input names, in CTL_MUX_SEL value order (see the TRM mux source
# table). The 32 empty strings are the 32..63 region, which is multiplexed
# between reg_mem1, the counters and the LUT output by ctrsel/lutsel: a bare
# '+a' operand parses to the empty name and lands on input 32, exactly as in
# the original assembler.
# fmt: off
_INPUTS = (
    *tuple(str(i) for i in range(32)),   # 0..31: input FIFO register (reg_mem0)
    *([''] * 32),                        # 32..63: multiplexed region
    'bl<=o0', 'bl>o0', 'bl=o0', 'bl<=o8', 'bl>o8', 'bl=o8', 'bl<=o16', 'bl>o16',
    'bl=o16', 'bl<=o24', 'bl>o24', 'bl=o24', 'bh<=o0', 'bh>o0', 'bh=o0', 'bh<=o8',
    'bh>o8', 'bh=o8', 'bh<=o16', 'bh>o16', 'bh=o16', 'bh<=o24', 'bh>o24', 'bh=o24',
    'b<=o0', 'b>o0', 'b=o0', 'b<=o16', 'b>o16', 'b=o16', 'l', 'h',   # 64..95: comparators + fixed 0/1
    *tuple(f'o{i}' for i in range(32)),  # 96..127: previous output register
)
_INPUTS_CTRSEL_SET = tuple(f'a{i}' for i in range(16)) + tuple(f'b{i}' for i in range(16))
_INPUTS_CTRSEL_CLR = tuple(str(i) for i in range(32, 64))
_INPUT_LUT_BITS = tuple(f'l{i}' for i in range(32))
# fmt: on


@dataclass(frozen=True, slots=True)
class SourceSpelling:
    """One mux-source name the assembler accepts, for editor completions."""

    name: str
    detail: str
    allows_relative: bool  # True iff CTL_MUX_SEL index is below 64
    lut_index: int | None = None  # 0..31 when this is ``lN``


def source_spellings() -> list[SourceSpelling]:
    """Every valid mux-source spelling, derived from the :func:`_parse_input` tables.

    Empty names (the multiplexed-region placeholder in ``_INPUTS[32:64]``)
    are omitted. ``allows_relative`` follows the same ``index < 64`` rule as
    :func:`_parse_input`. LUT-bit filtering by ``cfg lut_width_bits`` stays
    with the caller, which uses :attr:`SourceSpelling.lut_index`.
    """
    items = [
        *[SourceSpelling(name, 'input FIFO bit', True) for name in _INPUTS[:32]],
        *[
            SourceSpelling(name, 'counter a bit' if name.startswith('a') else 'counter b bit', True)
            for name in _INPUTS_CTRSEL_SET
        ],
        *[SourceSpelling(name, 'reg_mem1 bit', True) for name in _INPUTS_CTRSEL_CLR],
        *[SourceSpelling(name, 'LUT bit', True, lut_index=i) for i, name in enumerate(_INPUT_LUT_BITS)],
    ]
    for index, name in enumerate(_INPUTS[64:], start=64):
        if index < 94:
            detail = 'comparator'
        elif index == 94:
            detail = 'fixed low'
        elif index == 95:
            detail = 'fixed high'
        else:
            detail = 'previous output bit'
        items.append(SourceSpelling(name, detail, False))
    return items


# Where in the multiplexed region the LUT outputs live, per LUT width.
_LUT_STARTS = {LutWidth.BITS8: 24, LutWidth.BITS16: 16, LutWidth.BITS32: 0}

# Allowed value spellings and ranges, as in the original assembler's
# meta_inst_defs. 'cfg' value spellings are matched as strings, so '08' is
# rejected just like before.
_PREFETCH_VALUES = {'true': True, 'false': False, '1': True, '0': False}
_LUT_WIDTH_VALUES = {'8': LutWidth.BITS8, '16': LutWidth.BITS16, '32': LutWidth.BITS32}
_LOOP_ENDS_ON_VALUES = {'equal': LoopEndsOn.EQUAL, 'equal_or_greater': LoopEndsOn.EQUAL_OR_GREATER}

# Range of a single LUT value, per LUT width. (The 16-bit maximum was
# 65537 in the original assembler, letting 65536/65537 wrap around to 0/1.)
_LUT_MINMAX = {
    LutWidth.BITS8: (-128, 255),
    LutWidth.BITS16: (-32768, 65535),
    LutWidth.BITS32: (-2147483648, 4294967295),
}

# 'trailing_bytes' is stored in the header as trailing *bits* in a 16-bit
# field, so 8191 bytes (65528 bits) is the largest value that fits. (The
# original accepted 8192 and crashed inside struct.pack.)
_TRAILING_BYTES_MAX = 8191

_VALID_WIDTHS = (Width.ZERO, Width.EIGHT, Width.SIXTEEN, Width.THIRTYTWO)

DEFAULT_CHIPCFG: Chipcfg = {'chipname': 'chip', 'extra_instruction_groups': [], 'support_all': True}


def analyze(statements: list[Statement], chipcfg: Chipcfg | None = None) -> Program:
    """Run the five semantic passes and produce a :class:`Program`."""
    cfg = DEFAULT_CHIPCFG if chipcfg is None else chipcfg
    labels = _collect_labels(statements)
    meta = _collect_cfg(statements)
    lut = _collect_lut(statements, meta.lut_width)
    insts = _build_insts(statements, cfg, labels, meta.lut_width)
    _check_jump_targets(statements, labels, len(insts))
    return Program(meta=meta, insts=tuple(insts), lut=tuple(lut), labels=labels)


# Pass 1: labels ------------------------------------------------------------


def _collect_labels(statements: list[Statement]) -> dict[str, int]:
    """Record the instruction index every label points at.

    Labels are matched case-insensitively, matching the rest of the
    language; a second definition of the same name (in any spelling) is an
    error. (The original assembler matched definitions case-sensitively but
    references lower-cased, so 'FOO:' could never be referenced at all, and
    silently let duplicates overwrite each other.)
    """
    labels: dict[str, int] = {}
    defined: dict[str, Location] = {}
    ip = 0
    for st in statements:
        if isinstance(st, LabelStmt):
            key = st.name.lower()
            if key in defined:
                raise AssemblerSyntaxError(st.location, f"'{st.name}' is already defined here", defined[key])
            labels[key] = ip
            defined[key] = st.location
        elif isinstance(st, BundleStmt):
            ip += 1
    return labels


def _resolve_label(atom: Atom, labels: dict[str, int]) -> int:
    target = labels.get(atom.text.lower())
    if target is None:
        raise AssemblerSyntaxError(atom.location, f"'{atom.text.lower()}': Label not found.")
    return target


# Pass 2: cfg ---------------------------------------------------------------


def _collect_cfg(statements: list[Statement]) -> ProgramMeta:
    """Apply all 'cfg' statements in document order (the last one wins)."""
    meta = ProgramMeta()
    for st in statements:
        if not isinstance(st, CfgStmt):
            continue
        text = st.value.text.lower()
        match st.key:
            case CfgKey.PREFETCH:
                if text not in _PREFETCH_VALUES:
                    raise AssemblerSyntaxError(st.value.location, f'{text} is not an allowed value for prefetch')
                meta = replace(meta, prefetch=_PREFETCH_VALUES[text])
            case CfgKey.TRAILING_BYTES:
                meta = replace(meta, trailing_bytes=_parse_val(st.value, 0, _TRAILING_BYTES_MAX))
            case CfgKey.EOF_ON:
                # The grammar only lets UPSTREAM/DOWNSTREAM through.
                meta = replace(meta, eof_on=EofSide[text.upper()])
            case CfgKey.LUT_WIDTH_BITS:
                if text not in _LUT_WIDTH_VALUES:
                    raise AssemblerSyntaxError(st.value.location, f'{text} is not an allowed value for lut_width_bits')
                meta = replace(meta, lut_width=_LUT_WIDTH_VALUES[text])
            case CfgKey.LOOP_ENDS_ON:
                if text not in _LOOP_ENDS_ON_VALUES:
                    raise AssemblerSyntaxError(st.value.location, f'{text} is not an allowed value for loop_ends_on')
                meta = replace(meta, loop_ends_on=_LOOP_ENDS_ON_VALUES[text])
    return meta


# Pass 3: LUT ----------------------------------------------------------------


def _collect_lut(statements: list[Statement], lut_width: LutWidth) -> list[int]:
    """Collect all LUT values, validated against the final LUT width."""
    minimum, maximum = _LUT_MINMAX[lut_width]
    values: list[int] = []
    for st in statements:
        if isinstance(st, LutStmt):
            values.extend(_parse_val(atom, minimum, maximum) for atom in st.values)
    return values


# Value and source parsing ---------------------------------------------------


def _parse_int(text: str) -> int:
    """Parse a NUMBER spelling the way Python integer literals work.

    ``int(text, 0)`` picks up ``0x`` / ``0o`` / ``0b`` (and a leading sign).
    Bare decimals with leading zeros (``08``) are not Python literals, but
    the grammar's decimal alternative still emits them; fall back to base 10.
    """
    try:
        return int(text, 0)
    except ValueError:
        return int(text, 10)


def _parse_val(atom: Atom, minimum: int, maximum: int) -> int:
    """Parse a NUMBER token into an int in ``[minimum, maximum]``."""
    text = atom.text
    try:
        value = _parse_int(text)
    except ValueError:
        raise AssemblerSyntaxError(atom.location, f"'{text}' is not an integer") from None
    if value < minimum or value > maximum:
        raise AssemblerSyntaxError(atom.location, f"'{text}' is out of range [{minimum}..{maximum}]")
    return value


def _parse_input(atom: Atom, lut_width: LutWidth) -> MuxSource:
    """Resolve one mux source name to its CTL_MUX_SEL value and control bits.

    This is a direct port of the original parse_input(): same name tables,
    same '+a' suffix handling, same error messages. The only behavioural
    change is the LUT width check, which used '>' where '>= 'was meant and
    mis-encoded 'l8' on an 8-bit LUT as a comparator input.
    """
    text = atom.text.lower()
    rel_addr = text.endswith('+a')
    if rel_addr:
        text = text[:-2]  # chop off the '+a'

    ctrsel: int | None = None
    lutsel: int | None = None
    if text in _INPUTS:
        # Always accessible regardless of ctrsel/lutsel; '' lands on the
        # first entry of the multiplexed region, i.e. input 32.
        index = _INPUTS.index(text)
    elif text in _INPUTS_CTRSEL_SET:
        i = _INPUTS_CTRSEL_SET.index(text)
        index = i + 32
        ctrsel = 1
        if i >= _LUT_STARTS[lut_width]:
            lutsel = 0
    elif text in _INPUTS_CTRSEL_CLR:
        i = _INPUTS_CTRSEL_CLR.index(text)
        index = i + 32
        ctrsel = 0
        if i >= _LUT_STARTS[lut_width]:
            # These overlap the LUT; lutsel cannot be 1 while they are used.
            lutsel = 0
    elif text in _INPUT_LUT_BITS:
        i = _INPUT_LUT_BITS.index(text)
        if i >= int(lut_width):
            raise AssemblerSyntaxError(
                atom.location,
                f'LUT input {text} referenced, but LUT is configured to be only {int(lut_width)} bits wide.',
            )
        index = i + 32 + _LUT_STARTS[lut_width]
        lutsel = 1
    elif _looks_like_number(text):
        # ``set 0 0x10`` is FIFO bit 16. Re-enter with the decimal spelling
        # so table lookup and ``+a`` share one path.
        value = _parse_val(Atom(text, atom.location), 0, 63)
        suffix = '+a' if rel_addr else ''
        return _parse_input(Atom(f'{value}{suffix}', atom.location), lut_width)
    else:
        raise AssemblerSyntaxError(atom.location, f"Input '{text}' is not valid.")

    if index >= 64 and rel_addr:
        raise AssemblerSyntaxError(atom.location, f"LUT input '{text}' cannot be relatively addressed.")

    # Only inputs below 64 can be relatively addressed; for those, rel_addr
    # is a hard requirement (False counts as one), for the others it is
    # don't-care.
    return MuxSource(
        index=index,
        text=text,
        location=atom.location,
        ctrsel=ctrsel,
        lutsel=lutsel,
        rel_addr=rel_addr if index < 64 else None,
    )


def _check_sources_compatible(first: MuxSource, second: MuxSource) -> None:
    """Raise if two mux sources of one instruction need conflicting bits."""
    message = check_sources_compatible(first, second)
    if message:
        raise AssemblerSyntaxError(first.location, message, second.location)


def _parse_input_range(start: Atom, end: Atom | None, lut_width: LutWidth) -> list[MuxSource]:
    """Expand 'a..b' input selections into the mux sources they denote."""
    first = _parse_input(start, lut_width)
    last = first if end is None else _parse_input(end, lut_width)

    # Ranges may span the 0..31 / 32..63 boundary only when the multiplexed
    # half needs no specific ctrsel/lutsel (i.e. plain reg_mem1 bits); this
    # is a direct port of the original boundary logic.
    def plain_multiplexed(source: MuxSource) -> bool:
        """True if the source needs no specific ctrsel/lutsel (plain reg_mem1)."""
        return (source.ctrsel is None or source.ctrsel == 0) and (source.lutsel is None or source.lutsel == 0)

    if (first.index < 32 and 32 <= last.index < 64 and plain_multiplexed(last)) or (
        last.index < 32 and 32 <= first.index < 64 and plain_multiplexed(first)
    ):
        pass
    elif first.index // 32 != last.index // 32:
        errtxt = f'{start.text.lower()}..{last.text.lower()} is not a valid range of input selections. '
        if first.lutsel == 1 and last.lutsel is None and last.index < 32:
            errtxt += 'Did you forget an L at the end of the range? (e.g. L0..31 instead of L0..L31)'
        else:
            errtxt += 'Try splitting up the range.'
        raise AssemblerSyntaxError(start.location, errtxt)

    _check_sources_compatible(first, last)

    # Merge the control-bit requirements: the end operand wins where it
    # states one, as in the original assembler.
    merged = MuxSource(
        index=0,
        text=f'{start.text.lower()}..{last.text.lower()}' if end is not None else start.text.lower(),
        location=start.location,
        ctrsel=last.ctrsel if last.ctrsel is not None else first.ctrsel,
        lutsel=last.lutsel if last.lutsel is not None else first.lutsel,
        rel_addr=last.rel_addr if last.rel_addr is not None else first.rel_addr,
    )

    if first.index <= last.index:
        indices = range(first.index, last.index + 1)
    else:
        indices = range(first.index, last.index - 1, -1)
    return [
        MuxSource(
            index=i,
            text=merged.text,
            location=start.location,
            ctrsel=merged.ctrsel,
            lutsel=merged.lutsel,
            rel_addr=merged.rel_addr,
        )
        for i in indices
    ]


def _looks_like_number(text: str) -> bool:
    """True if ``text`` parses as a NUMBER spelling (see :func:`_parse_int`)."""
    try:
        _parse_int(text)
    except ValueError:
        return False
    return True


def _parse_output_range(start: Atom, end: Atom | None) -> range:
    """Expand an output bit selection into a (possibly backwards) range.

    Endpoints are NUMBER tokens, so ``int(..., 0)`` spellings are accepted
    the same way as LUT values and immediates (``set 0x10 5`` is bit 16).
    """
    first = _parse_val(start, 0, 31)
    last = first if end is None else _parse_val(end, 0, 31)
    return range(first, last + 1) if first <= last else range(first, last - 1, -1)


# Pass 4: instructions --------------------------------------------------------


def _check_chip_supports(chipcfg: Chipcfg, group: str, location: Location) -> None:
    if chipcfg.get('support_all'):
        return
    if group not in chipcfg.get('extra_instruction_groups', []):
        name = chipcfg.get('chipname', 'chip')
        raise AssemblerSyntaxError(location, f'Chip {name} does not support this instruction')


def _build_insts(
    statements: list[Statement],
    chipcfg: Chipcfg,
    labels: dict[str, int],
    lut_width: LutWidth,
) -> list[Instruction]:
    insts: list[Instruction] = []
    for st in statements:
        if not isinstance(st, BundleStmt):
            continue
        insts.append(_build_inst(st, chipcfg, labels, lut_width))
    return insts


# Pass 5: jump targets --------------------------------------------------------


def _check_jump_targets(statements: list[Statement], labels: dict[str, int], inst_ct: int) -> None:
    """Reject jumps to labels that point past the last instruction.

    The original assembler silently encoded such targets: with a full eight
    instructions the 3-bit target field overflowed into the counter-select
    bit, and with fewer instructions the hardware would execute unloaded
    instruction memory. A label that nothing references is fine anywhere,
    including at the very end of the file.
    """
    for st in statements:
        if not isinstance(st, BundleStmt):
            continue
        for sub in st.subs:
            if not isinstance(sub, LoopSub | IfSub | JmpSub):
                continue
            name = sub.target.text.lower()
            ip = labels[name]
            if ip >= inst_ct:
                raise AssemblerSyntaxError(
                    sub.target.location,
                    f"jump target '{name}' points past the end of the program ({inst_ct} instructions)",
                )


class _InstBuilder:
    """Accumulates the mux routes, FIFO widths and opcode of one instruction."""

    def __init__(self, st: BundleStmt, labels: dict[str, int], lut_width: LutWidth, chipcfg: Chipcfg) -> None:
        self._location = st.location
        self._labels = labels
        self._lut_width = lut_width
        self._chipcfg = chipcfg
        self._mux: dict[int, MuxSource] = {}
        self._read = Width.ZERO
        self._write = Width.ZERO
        self._op: Opcode | None = None

    def build(self) -> Instruction:
        self._check_mux_conflicts()
        return Instruction(location=self._location, mux=self._mux, read=self._read, write=self._write, op=self._op)

    def _check_mux_conflicts(self) -> None:
        """Pairwise source compatibility over all 33 mux slots.

        Same slot order and first-conflict-wins behavior as the original
        assembler's encode-time check, now raised at analysis time as a
        located :class:`AssemblerSyntaxError`.
        """
        mux = mux_with_condition(self._mux, self._op)
        for i in range(COND_MUX_SLOT + 1):
            if i not in mux:
                continue
            for j in range(i + 1, COND_MUX_SLOT + 1):
                if j in mux:
                    message = check_sources_compatible(mux[i], mux[j])
                    if message:
                        raise AssemblerSyntaxError(mux[i].location, message, mux[j].location)

    def add(self, sub: SubInstr) -> None:
        match sub:
            case SetSub():
                self._add_set(sub)
            case WidthSub():
                self._add_width(sub)
            case LoopSub():
                self._add_loop(sub)
            case AddSub():
                self._add_counter_imm(OpcodeKind.ADD, sub.location, sub.counter, sub.halves, sub.value)
            case IfSub():
                self._add_if(sub)
            case LdctdSub():
                self._add_counter_imm(OpcodeKind.LDCTD, sub.location, sub.counter, sub.halves, sub.value)
            case LdctiSub():
                self._add_counter(OpcodeKind.LDCTI, sub.location, sub.counter, sub.halves)
            case AddctiSub():
                _check_chip_supports(self._chipcfg, 'addcti', sub.location)
                self._add_counter(OpcodeKind.ADDCTI, sub.location, sub.counter, sub.halves)
            case JmpSub():
                # JMP is an IF on the fixed-high input.
                self._add_jump(OpcodeKind.IF, sub.location, Atom('h', sub.location), sub.target)
            case NopSub():
                # NOP assembles to ADD hl 0.
                self._add_counter_imm(OpcodeKind.ADD, sub.location, CounterSel.A, Halves.FULL, Atom('0', sub.location))
            case _:
                # pragma: no cover - every builder variant is handled above
                raise AssertionError(f'Unhandled sub-instruction {sub!r}')

    def _set_op(self, op: Opcode) -> None:
        if self._op is not None:
            raise AssemblerSyntaxError(
                self._op.location, 'Cannot have multiple opcodes in one instruction', op.location
            )
        self._op = op

    def _add_set(self, sub: SetSub) -> None:
        outs = _parse_output_range(sub.out_start, sub.out_end)
        ins = _parse_input_range(sub.in_start, sub.in_end, self._lut_width)
        if len(ins) != 1 and len(ins) != len(outs):
            raise AssemblerSyntaxError(sub.location, 'ranges not the same length')
        i = 0
        for out in outs:
            if out in self._mux:
                raise AssemblerSyntaxError(sub.location, f'output {out} already set earlier in instruction')
            if len(ins) == 1:
                self._mux[out] = ins[0]
            else:
                self._mux[out] = ins[i]
                i += 1

    def _add_width(self, sub: WidthSub) -> None:
        value = _parse_val(sub.width, 0, 32)
        if value not in _VALID_WIDTHS:
            noun = 'read' if sub.is_read else 'write'
            raise AssemblerSyntaxError(sub.location, f'{value} is not a valid amount of bits to {noun}')
        if sub.is_read:
            self._read = Width(value)
        else:
            self._write = Width(value)

    def _add_loop(self, sub: LoopSub) -> None:
        self._set_op(
            Opcode(
                kind=OpcodeKind.LOOP,
                location=sub.location,
                counter=sub.counter,
                value=_parse_val(sub.end_val, -32768, 65535) & 0xFFFF,
                ctr_add=_parse_val(sub.ctr_add, -16, 15) & 31,
                target_ip=_resolve_label(sub.target, self._labels),
            )
        )

    def _add_if(self, sub: IfSub) -> None:
        self._add_jump(OpcodeKind.IFN if sub.negated else OpcodeKind.IF, sub.location, sub.cond, sub.target)

    def _add_jump(self, kind: OpcodeKind, location: Location, cond: Atom, target: Atom) -> None:
        self._set_op(
            Opcode(
                kind=kind,
                location=location,
                cond_source=_parse_input(cond, self._lut_width),
                target_ip=_resolve_label(target, self._labels),
            )
        )

    def _add_counter_imm(
        self,
        kind: OpcodeKind,
        location: Location,
        counter: CounterSel,
        halves: Halves,
        value: Atom | None,
    ) -> None:
        parsed = None if value is None else _parse_val(value, -32768, 65535) & 0xFFFF
        self._add_counter(kind, location, counter, halves, parsed)

    def _add_counter(
        self,
        kind: OpcodeKind,
        location: Location,
        counter: CounterSel,
        halves: Halves,
        value: int | None = None,
    ) -> None:
        self._set_op(Opcode(kind=kind, location=location, counter=counter, halves=halves, value=value))


def _build_inst(st: BundleStmt, chipcfg: Chipcfg, labels: dict[str, int], lut_width: LutWidth) -> Instruction:
    builder = _InstBuilder(st, labels, lut_width, chipcfg)
    for sub in st.subs:
        builder.add(sub)
    return builder.build()
