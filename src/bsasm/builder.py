# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Parse tree to statement IR: the ANTLR visitor layer.

The grammar guarantees the *shape* of every statement; this module walks the
parse tree and records that shape as the statement dataclasses defined in
:mod:`bsasm.model`, without interpreting anything (no numeric parsing, no
label resolution). All interpretation lives in :mod:`bsasm.sema`.
"""

from dataclasses import dataclass

from antlr4 import ParserRuleContext, TerminalNode, Token

from bsasm.errors import Location
from bsasm.generated.BitScramblerLexer import BitScramblerLexer
from bsasm.generated.BitScramblerParser import BitScramblerParser
from bsasm.generated.BitScramblerVisitor import BitScramblerVisitor
from bsasm.model import (
    AddctiSub,
    AddSub,
    Atom,
    BundleStmt,
    CfgKey,
    CfgStmt,
    CounterSel,
    Halves,
    IfSub,
    JmpSub,
    LabelStmt,
    LdctdSub,
    LdctiSub,
    LoopSub,
    LutStmt,
    NopSub,
    SetSub,
    Statement,
    WidthSub,
)


@dataclass(frozen=True, slots=True)
class _Mnemonic:
    """What the A/B/H/L letters baked into a mnemonic token stand for."""

    counter: CounterSel
    halves: Halves


# Mnemonic token type -> counter and written-back halves. The H/L suffixes
# select which bytes of the counter are written back; a bare mnemonic means
# both (h=1, l=1), see the ADD/LDCTD/LDCTI/ADDCTI opcode tables in the TRM.
_MNEMONICS: dict[int, _Mnemonic] = {
    BitScramblerLexer.ADDA: _Mnemonic(CounterSel.A, Halves.FULL),
    BitScramblerLexer.ADDAH: _Mnemonic(CounterSel.A, Halves.HIGH),
    BitScramblerLexer.ADDAL: _Mnemonic(CounterSel.A, Halves.LOW),
    BitScramblerLexer.ADDB: _Mnemonic(CounterSel.B, Halves.FULL),
    BitScramblerLexer.ADDBH: _Mnemonic(CounterSel.B, Halves.HIGH),
    BitScramblerLexer.ADDBL: _Mnemonic(CounterSel.B, Halves.LOW),
    BitScramblerLexer.LDCTDA: _Mnemonic(CounterSel.A, Halves.FULL),
    BitScramblerLexer.LDCTDAH: _Mnemonic(CounterSel.A, Halves.HIGH),
    BitScramblerLexer.LDCTDAL: _Mnemonic(CounterSel.A, Halves.LOW),
    BitScramblerLexer.LDCTDB: _Mnemonic(CounterSel.B, Halves.FULL),
    BitScramblerLexer.LDCTDBH: _Mnemonic(CounterSel.B, Halves.HIGH),
    BitScramblerLexer.LDCTDBL: _Mnemonic(CounterSel.B, Halves.LOW),
    BitScramblerLexer.LDCTIA: _Mnemonic(CounterSel.A, Halves.FULL),
    BitScramblerLexer.LDCTIAH: _Mnemonic(CounterSel.A, Halves.HIGH),
    BitScramblerLexer.LDCTIAL: _Mnemonic(CounterSel.A, Halves.LOW),
    BitScramblerLexer.LDCTIB: _Mnemonic(CounterSel.B, Halves.FULL),
    BitScramblerLexer.LDCTIBH: _Mnemonic(CounterSel.B, Halves.HIGH),
    BitScramblerLexer.LDCTIBL: _Mnemonic(CounterSel.B, Halves.LOW),
    BitScramblerLexer.ADDCTIA: _Mnemonic(CounterSel.A, Halves.FULL),
    BitScramblerLexer.ADDCTIAH: _Mnemonic(CounterSel.A, Halves.HIGH),
    BitScramblerLexer.ADDCTIAL: _Mnemonic(CounterSel.A, Halves.LOW),
    BitScramblerLexer.ADDCTIB: _Mnemonic(CounterSel.B, Halves.FULL),
    BitScramblerLexer.ADDCTIBH: _Mnemonic(CounterSel.B, Halves.HIGH),
    BitScramblerLexer.ADDCTIBL: _Mnemonic(CounterSel.B, Halves.LOW),
}


def _location(token: Token) -> Location:
    """One-based location of a single lexer token."""
    return Location(token.line, token.column + 1, token.text)


def _token_location(node: ParserRuleContext | TerminalNode) -> Location:
    """Location of a rule context or of a single terminal node."""
    return _location(node.start if isinstance(node, ParserRuleContext) else node.getSymbol())


def _atom(node: ParserRuleContext | TerminalNode | Token) -> Atom:
    """An operand atom from a rule context, a terminal node or a labeled token."""
    if isinstance(node, Token):
        return Atom(node.text, _location(node))
    return Atom(node.getText(), _token_location(node))


class ProgramBuilder(BitScramblerVisitor):
    """Collects the parse tree into an ordered list of :data:`Statement`."""

    def visitProgram(self, ctx: BitScramblerParser.ProgramContext) -> list[Statement]:
        statements: list[Statement] = []
        for line in ctx.line():
            statements.extend(self.visit(line))
        return statements

    # Lines ----------------------------------------------------------------

    def visitBlankLine(self, ctx: BitScramblerParser.BlankLineContext) -> list[Statement]:  # noqa: ARG002
        return []

    def visitContentLine(self, ctx: BitScramblerParser.ContentLineContext) -> list[Statement]:
        # labelDef* lineContent? labelDef*: children are in document order,
        # so a plain walk reproduces the source order exactly.
        statements: list[Statement] = []
        for child in ctx.children:
            if isinstance(child, BitScramblerParser.LabelDefContext):
                name = child.LABEL().getText()[:-1]  # drop the colon
                statements.append(LabelStmt(name, _token_location(child)))
            elif isinstance(child, ParserRuleContext):
                # The trailing NEWLINE is a TerminalNode; visiting it would
                # append None to the IR via the visitor's default result.
                statements.append(self.visit(child))
        return statements

    # Meta statements ------------------------------------------------------

    def visitCfgStmt(self, ctx: BitScramblerParser.CfgStmtContext) -> CfgStmt:
        # ctx is the CfgStmtContext itself; the grammar guarantees exactly
        # one of the alternatives. Matching on the token accessors instead
        # of a silent fallback means a newly added cfg key whose case is
        # forgotten here fails loudly instead of parsing as lut_width_bits.
        value: ParserRuleContext
        if ctx.K_PREFETCH():
            key, value = CfgKey.PREFETCH, ctx.cfgBoolean()
        elif ctx.K_TRAILING_BYTES():
            key, value = CfgKey.TRAILING_BYTES, ctx.NUMBER()
        elif ctx.K_EOF_ON():
            key, value = CfgKey.EOF_ON, (ctx.K_UPSTREAM() or ctx.K_DOWNSTREAM())
        elif ctx.K_LUT_WIDTH_BITS():
            key, value = CfgKey.LUT_WIDTH_BITS, ctx.NUMBER()
        elif ctx.K_LOOP_ENDS_ON():
            key, value = CfgKey.LOOP_ENDS_ON, (ctx.K_EQUAL() or ctx.K_EQUAL_OR_GREATER())
        else:
            raise AssertionError(f'Unknown cfg statement at {_token_location(ctx)}')
        return CfgStmt(key, Atom(value.getText(), _token_location(value)), _token_location(ctx))

    def visitLutStmt(self, ctx: BitScramblerParser.LutStmtContext) -> LutStmt:
        values = tuple(Atom(v.getText(), _token_location(v)) for v in ctx.lutValue())
        return LutStmt(values, _token_location(ctx))

    # Bundles and sub-instructions ------------------------------------------

    def visitBundle(self, ctx: BitScramblerParser.BundleContext) -> BundleStmt:
        subs = tuple(self.visit(sub) for sub in ctx.subInstr())
        return BundleStmt(subs, subs[0].location)

    def visitSubSet(self, ctx: BitScramblerParser.SubSetContext) -> SetSub:
        inst = ctx.setInstr()
        out, ins = inst.outSpec(), inst.inSpec()
        return SetSub(
            out_start=_atom(out.first),
            out_end=_atom(out.last) if out.last is not None else None,
            in_start=_atom(ins.first),
            in_end=_atom(ins.last) if ins.last is not None else None,
            location=_token_location(inst),
        )

    def visitSubWrite(self, ctx: BitScramblerParser.SubWriteContext) -> WidthSub:
        inst = ctx.writeInstr()
        return WidthSub(_atom(inst.NUMBER()), is_read=False, location=_token_location(inst))

    def visitSubRead(self, ctx: BitScramblerParser.SubReadContext) -> WidthSub:
        inst = ctx.readInstr()
        return WidthSub(_atom(inst.NUMBER()), is_read=True, location=_token_location(inst))

    def visitSubLoop(self, ctx: BitScramblerParser.SubLoopContext) -> LoopSub:
        inst = ctx.loopInstr()
        return LoopSub(
            counter=CounterSel.A if inst.LOOPA() else CounterSel.B,
            end_val=_atom(inst.endVal),
            ctr_add=_atom(inst.ctrAdd),
            target=_atom(inst.tgt.identifier()),
            location=_token_location(inst),
        )

    def visitSubAdd(self, ctx: BitScramblerParser.SubAddContext) -> AddSub:
        inst = ctx.addInstr()
        mnemonic = _MNEMONICS[inst.addMnemonic().start.type]
        return AddSub(mnemonic.counter, mnemonic.halves, _atom(inst.NUMBER()), _token_location(inst))

    def visitSubIf(self, ctx: BitScramblerParser.SubIfContext) -> IfSub:
        inst = ctx.ifInstr()
        return IfSub(
            negated=bool(inst.IFN()),
            cond=_atom(inst.condSource().sourceBit()),
            target=_atom(inst.labelRef().identifier()),
            location=_token_location(inst),
        )

    def visitSubLdctd(self, ctx: BitScramblerParser.SubLdctdContext) -> LdctdSub:
        inst = ctx.ldctdInstr()
        mnemonic = _MNEMONICS[inst.ldctdMnemonic().start.type]
        return LdctdSub(mnemonic.counter, mnemonic.halves, _atom(inst.NUMBER()), _token_location(inst))

    def visitSubLdcti(self, ctx: BitScramblerParser.SubLdctiContext) -> LdctiSub:
        inst = ctx.ldctiInstr()
        mnemonic = _MNEMONICS[inst.ldctiMnemonic().start.type]
        return LdctiSub(mnemonic.counter, mnemonic.halves, _token_location(inst))

    def visitSubAddcti(self, ctx: BitScramblerParser.SubAddctiContext) -> AddctiSub:
        inst = ctx.addctiInstr()
        mnemonic = _MNEMONICS[inst.addctiMnemonic().start.type]
        return AddctiSub(mnemonic.counter, mnemonic.halves, _token_location(inst))

    def visitSubJmp(self, ctx: BitScramblerParser.SubJmpContext) -> JmpSub:
        inst = ctx.jmpInstr()
        return JmpSub(_atom(inst.labelRef().identifier()), _token_location(inst))

    def visitSubNop(self, ctx: BitScramblerParser.SubNopContext) -> NopSub:
        return NopSub(_token_location(ctx.nopInstr()))
