# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Semantic analysis: statements in, :class:`~bsasm.model.Program` out.

This module owns every check that needs a readable diagnostic: numeric
ranges and spellings, label resolution, the ctrsel/lutsel/rel_addr
compatibility rules, extra instructions and the per-bundle
'unusually many opcodes' checks. The behaviour mirrors the original
assembler's four passes; the differences are deliberate and documented in
the repository README.md.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace

from bsasm.errors import AssemblerError, AssemblerSyntaxError, Location
from bsasm.isa import (
    INPUT_LUT_BITS,
    INPUTS,
    INPUTS_CTRSEL_CLR,
    INPUTS_CTRSEL_SET,
    LOOP_ENDS_ON_VALUES,
    LUT_MAX_VALUES,
    LUT_MINMAX,
    LUT_STARTS,
    LUT_WIDTH_VALUES,
    OPTIONAL_INSTRUCTION_GROUPS,
    OPTIONAL_OPCODES,
    PREFETCH_VALUES,
    TRAILING_BYTES_MAX,
    VALID_WIDTHS,
)
from bsasm.model import (
    COND_MUX_SLOT,
    MAX_INSTS,
    AddctiSub,
    AddSub,
    Atom,
    BundleStmt,
    CfgKey,
    CfgStmt,
    CounterSel,
    EofSide,
    Halves,
    IfSub,
    Instruction,
    JmpSub,
    LabelStmt,
    LdctdSub,
    LdctiSub,
    LoopSub,
    LutStmt,
    LutWidth,
    MuxSource,
    NopSub,
    Opcode,
    OpcodeKind,
    Program,
    ProgramMeta,
    SetSub,
    Statement,
    SubInstr,
    Width,
    WidthSub,
    check_sources_compatible,
    mux_with_condition,
)


@dataclass(frozen=True, slots=True)
class SourceSpelling:
    """One mux-source name the assembler accepts, for editor completions."""

    name: str
    detail: str
    allows_relative: bool  # True iff CTL_MUX_SEL index is below 64
    lut_index: int | None = None  # 0..31 when this is ``lN``


def source_spellings() -> list[SourceSpelling]:
    """Every valid mux-source spelling, derived from the :func:`_parse_input` tables.

    Empty names (the multiplexed-region placeholder in ``INPUTS[32:64]``)
    are omitted. ``allows_relative`` follows the same ``index < 64`` rule as
    :func:`_parse_input`. LUT-bit filtering by ``cfg lut_width_bits`` stays
    with the caller, which uses :attr:`SourceSpelling.lut_index`.
    """
    items = [
        *[SourceSpelling(name, 'input FIFO bit', True) for name in INPUTS[:32]],
        *[
            SourceSpelling(name, 'counter a bit' if name.startswith('a') else 'counter b bit', True)
            for name in INPUTS_CTRSEL_SET
        ],
        *[SourceSpelling(name, 'reg_mem1 bit', True) for name in INPUTS_CTRSEL_CLR],
        *[SourceSpelling(name, 'LUT bit', True, lut_index=i) for i, name in enumerate(INPUT_LUT_BITS)],
    ]
    for index, name in enumerate(INPUTS[64:], start=64):
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


def normalize_extra_inst(names: Iterable[str]) -> frozenset[str]:
    """Return the canonical spelling of ``names``, rejecting unknown ones.

    Each name enables one family of mnemonics (``addcti`` enables the
    ``ADDCTI*`` instructions). Matching is case-insensitive. A bare string is
    rejected: the value is a collection of names, and a string would otherwise
    be read one character at a time. An unknown name raises
    :class:`AssemblerError`.
    """
    if isinstance(names, str):
        raise AssemblerError('Extra instructions must be a collection of names, not a single string')
    enabled: set[str] = set()
    unknown: list[str] = []
    seen_unknown: set[str] = set()
    for name in names:
        if not isinstance(name, str):
            raise AssemblerError(f'Extra instruction name must be a string, got {type(name).__name__}')
        canonical = name.lower()
        if canonical in OPTIONAL_INSTRUCTION_GROUPS:
            enabled.add(canonical)
        elif canonical not in seen_unknown:
            unknown.append(name)
            seen_unknown.add(canonical)
    if unknown:
        unknown.sort(key=str.lower)
        valid = ', '.join(sorted(OPTIONAL_INSTRUCTION_GROUPS)) or '(none)'
        raise AssemblerError(f'Unknown extra instructions {", ".join(unknown)}; valid names: {valid}')
    return frozenset(enabled)


def analyze(
    statements: list[Statement], enabled_extra_inst: Iterable[str] = ()
) -> tuple[Program, list[AssemblerError]]:
    """Run the five semantic passes, collecting every error.

    ``enabled_extra_inst`` lists the extra-instruction families that
    are allowed. Names are matched case-insensitively; an unknown name raises
    :class:`AssemblerError`. An instruction whose family is absent is reported
    in ``errors``. The returned :class:`Program` is only safe to encode when
    ``errors`` is empty.
    """
    enabled = normalize_extra_inst(enabled_extra_inst)
    errors: list[AssemblerError] = []
    labels = _collect_labels(statements, errors)
    meta = _collect_cfg(statements, errors)
    lut = _collect_lut(statements, meta.lut_width, errors)
    insts = _build_insts(statements, enabled, labels, meta.lut_width, errors)
    # Count bundles, not successfully-built insts: labels are indexed by bundle,
    # so a bundle that failed to build must not shift the instruction count used
    # for the hardware limit and the jump-target bounds.
    bundles = [st for st in statements if isinstance(st, BundleStmt)]
    inst_ct = len(bundles)
    if inst_ct > MAX_INSTS:
        errors.append(
            AssemblerSyntaxError(bundles[MAX_INSTS].location, f'Program has more than {MAX_INSTS} instructions.')
        )
    _check_jump_targets(statements, labels, inst_ct, errors)
    return Program(meta=meta, insts=tuple(insts), lut=tuple(lut), labels=labels), errors


# Pass 1: labels ------------------------------------------------------------


def _collect_labels(statements: list[Statement], errors: list[AssemblerError]) -> dict[str, int]:
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
                errors.append(AssemblerSyntaxError(st.location, f"'{st.name}' is already defined here", defined[key]))
                continue  # keep the first definition; later references still resolve
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


def _collect_cfg(statements: list[Statement], errors: list[AssemblerError]) -> ProgramMeta:
    """Apply all 'cfg' statements in document order (the last one wins)."""
    meta = ProgramMeta()
    for st in statements:
        if not isinstance(st, CfgStmt):
            continue
        text = st.value.text.lower()
        match st.key:
            case CfgKey.PREFETCH:
                if text not in PREFETCH_VALUES:
                    errors.append(
                        AssemblerSyntaxError(st.value.location, f'{text} is not an allowed value for prefetch')
                    )
                    continue
                meta = replace(meta, prefetch=PREFETCH_VALUES[text])
            case CfgKey.TRAILING_BYTES:
                try:
                    trailing = _parse_val(st.value, 0, TRAILING_BYTES_MAX)
                except AssemblerError as e:
                    errors.append(e)
                    continue
                meta = replace(meta, trailing_bytes=trailing)
            case CfgKey.EOF_ON:
                # The grammar only lets UPSTREAM/DOWNSTREAM through.
                meta = replace(meta, eof_on=EofSide[text.upper()])
            case CfgKey.LUT_WIDTH_BITS:
                if text not in LUT_WIDTH_VALUES:
                    errors.append(
                        AssemblerSyntaxError(st.value.location, f'{text} is not an allowed value for lut_width_bits')
                    )
                    continue
                meta = replace(meta, lut_width=LUT_WIDTH_VALUES[text])
            case CfgKey.LOOP_ENDS_ON:
                if text not in LOOP_ENDS_ON_VALUES:
                    errors.append(
                        AssemblerSyntaxError(st.value.location, f'{text} is not an allowed value for loop_ends_on')
                    )
                    continue
                meta = replace(meta, loop_ends_on=LOOP_ENDS_ON_VALUES[text])
    return meta


# Pass 3: LUT ----------------------------------------------------------------


def _collect_lut(statements: list[Statement], lut_width: LutWidth, errors: list[AssemblerError]) -> list[int]:
    """Collect all LUT values, validated against the final LUT width.

    The binary header stores the LUT length as a 16-bit word count, so an
    oversized table is reported here instead of overflowing struct.pack in
    the encoder.
    """
    minimum, maximum = LUT_MINMAX[lut_width]
    max_values = LUT_MAX_VALUES[lut_width]
    values: list[int] = []
    for st in statements:
        if isinstance(st, LutStmt):
            for atom in st.values:
                try:
                    values.append(_parse_val(atom, minimum, maximum))
                except AssemblerError as e:
                    errors.append(e)
    if len(values) > max_values:
        first_lut = next(st for st in statements if isinstance(st, LutStmt))
        errors.append(
            AssemblerSyntaxError(
                first_lut.location,
                f'Program has more than {max_values} LUT values for the configured LUT width.',
            )
        )
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
    if text in INPUTS:
        # Always accessible regardless of ctrsel/lutsel; '' lands on the
        # first entry of the multiplexed region, i.e. input 32.
        index = INPUTS.index(text)
    elif text in INPUTS_CTRSEL_SET:
        i = INPUTS_CTRSEL_SET.index(text)
        index = i + 32
        ctrsel = 1
        if i >= LUT_STARTS[lut_width]:
            lutsel = 0
    elif text in INPUTS_CTRSEL_CLR:
        i = INPUTS_CTRSEL_CLR.index(text)
        index = i + 32
        ctrsel = 0
        if i >= LUT_STARTS[lut_width]:
            # These overlap the LUT; lutsel cannot be 1 while they are used.
            lutsel = 0
    elif text in INPUT_LUT_BITS:
        i = INPUT_LUT_BITS.index(text)
        if i >= int(lut_width):
            raise AssemblerSyntaxError(
                atom.location,
                f'LUT input {text} referenced, but LUT is configured to be only {int(lut_width)} bits wide.',
            )
        index = i + 32 + LUT_STARTS[lut_width]
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


def _build_insts(
    statements: list[Statement],
    enabled: frozenset[str],
    labels: dict[str, int],
    lut_width: LutWidth,
    errors: list[AssemblerError],
) -> list[Instruction]:
    insts: list[Instruction] = []
    for st in statements:
        if not isinstance(st, BundleStmt):
            continue
        try:
            insts.append(_build_inst(st, enabled, labels, lut_width))
        except AssemblerError as e:
            errors.append(e)
    return insts


# Pass 5: jump targets --------------------------------------------------------


def _check_jump_targets(
    statements: list[Statement],
    labels: dict[str, int],
    inst_ct: int,
    errors: list[AssemblerError],
) -> None:
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
            ip = labels.get(name)
            if ip is None:
                continue  # _build_inst already reported the missing label
            if ip >= inst_ct:
                errors.append(
                    AssemblerSyntaxError(
                        sub.target.location,
                        f"jump target '{name}' points past the end of the program ({inst_ct} instructions)",
                    )
                )


class _InstBuilder:
    """Accumulates the mux routes, FIFO widths and opcode of one instruction."""

    def __init__(self, st: BundleStmt, labels: dict[str, int], lut_width: LutWidth, enabled: frozenset[str]) -> None:
        self._location = st.location
        self._labels = labels
        self._lut_width = lut_width
        self._enabled = enabled
        self._mux: dict[int, MuxSource] = {}
        self._read = Width.ZERO
        self._write = Width.ZERO
        self._read_at: Location | None = None
        self._write_at: Location | None = None
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
        name = OPTIONAL_OPCODES.get(op.kind)
        if name is not None and name not in self._enabled:
            raise AssemblerSyntaxError(op.location, f"extra instructions '{name}' are not enabled")
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
        noun = 'read' if sub.is_read else 'write'
        previous = self._read_at if sub.is_read else self._write_at
        if previous is not None:
            raise AssemblerSyntaxError(previous, f'Cannot have multiple {noun}s in one instruction', sub.location)
        value = _parse_val(sub.width, 0, 32)
        if value not in VALID_WIDTHS:
            raise AssemblerSyntaxError(sub.location, f'{value} is not a valid amount of bits to {noun}')
        if sub.is_read:
            self._read_at = sub.location
            self._read = Width(value)
        else:
            self._write_at = sub.location
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


def _build_inst(st: BundleStmt, enabled: frozenset[str], labels: dict[str, int], lut_width: LutWidth) -> Instruction:
    builder = _InstBuilder(st, labels, lut_width, enabled)
    for sub in st.subs:
        builder.add(sub)
    return builder.build()
