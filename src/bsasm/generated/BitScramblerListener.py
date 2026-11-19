# Generated from BitScrambler.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .BitScramblerParser import BitScramblerParser
else:
    from BitScramblerParser import BitScramblerParser

# This class defines a complete listener for a parse tree produced by BitScramblerParser.
class BitScramblerListener(ParseTreeListener):

    # Enter a parse tree produced by BitScramblerParser#program.
    def enterProgram(self, ctx:BitScramblerParser.ProgramContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#program.
    def exitProgram(self, ctx:BitScramblerParser.ProgramContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#BlankLine.
    def enterBlankLine(self, ctx:BitScramblerParser.BlankLineContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#BlankLine.
    def exitBlankLine(self, ctx:BitScramblerParser.BlankLineContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#ContentLine.
    def enterContentLine(self, ctx:BitScramblerParser.ContentLineContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#ContentLine.
    def exitContentLine(self, ctx:BitScramblerParser.ContentLineContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#labelDef.
    def enterLabelDef(self, ctx:BitScramblerParser.LabelDefContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#labelDef.
    def exitLabelDef(self, ctx:BitScramblerParser.LabelDefContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#lineContent.
    def enterLineContent(self, ctx:BitScramblerParser.LineContentContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#lineContent.
    def exitLineContent(self, ctx:BitScramblerParser.LineContentContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#cfgStmt.
    def enterCfgStmt(self, ctx:BitScramblerParser.CfgStmtContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#cfgStmt.
    def exitCfgStmt(self, ctx:BitScramblerParser.CfgStmtContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#cfgBoolean.
    def enterCfgBoolean(self, ctx:BitScramblerParser.CfgBooleanContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#cfgBoolean.
    def exitCfgBoolean(self, ctx:BitScramblerParser.CfgBooleanContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#lutStmt.
    def enterLutStmt(self, ctx:BitScramblerParser.LutStmtContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#lutStmt.
    def exitLutStmt(self, ctx:BitScramblerParser.LutStmtContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#lutValue.
    def enterLutValue(self, ctx:BitScramblerParser.LutValueContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#lutValue.
    def exitLutValue(self, ctx:BitScramblerParser.LutValueContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#bundle.
    def enterBundle(self, ctx:BitScramblerParser.BundleContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#bundle.
    def exitBundle(self, ctx:BitScramblerParser.BundleContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubSet.
    def enterSubSet(self, ctx:BitScramblerParser.SubSetContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubSet.
    def exitSubSet(self, ctx:BitScramblerParser.SubSetContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubWrite.
    def enterSubWrite(self, ctx:BitScramblerParser.SubWriteContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubWrite.
    def exitSubWrite(self, ctx:BitScramblerParser.SubWriteContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubRead.
    def enterSubRead(self, ctx:BitScramblerParser.SubReadContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubRead.
    def exitSubRead(self, ctx:BitScramblerParser.SubReadContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubLoop.
    def enterSubLoop(self, ctx:BitScramblerParser.SubLoopContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubLoop.
    def exitSubLoop(self, ctx:BitScramblerParser.SubLoopContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubAdd.
    def enterSubAdd(self, ctx:BitScramblerParser.SubAddContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubAdd.
    def exitSubAdd(self, ctx:BitScramblerParser.SubAddContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubIf.
    def enterSubIf(self, ctx:BitScramblerParser.SubIfContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubIf.
    def exitSubIf(self, ctx:BitScramblerParser.SubIfContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubLdctd.
    def enterSubLdctd(self, ctx:BitScramblerParser.SubLdctdContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubLdctd.
    def exitSubLdctd(self, ctx:BitScramblerParser.SubLdctdContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubLdcti.
    def enterSubLdcti(self, ctx:BitScramblerParser.SubLdctiContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubLdcti.
    def exitSubLdcti(self, ctx:BitScramblerParser.SubLdctiContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubAddcti.
    def enterSubAddcti(self, ctx:BitScramblerParser.SubAddctiContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubAddcti.
    def exitSubAddcti(self, ctx:BitScramblerParser.SubAddctiContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubJmp.
    def enterSubJmp(self, ctx:BitScramblerParser.SubJmpContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubJmp.
    def exitSubJmp(self, ctx:BitScramblerParser.SubJmpContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#SubNop.
    def enterSubNop(self, ctx:BitScramblerParser.SubNopContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#SubNop.
    def exitSubNop(self, ctx:BitScramblerParser.SubNopContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#setInstr.
    def enterSetInstr(self, ctx:BitScramblerParser.SetInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#setInstr.
    def exitSetInstr(self, ctx:BitScramblerParser.SetInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#writeInstr.
    def enterWriteInstr(self, ctx:BitScramblerParser.WriteInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#writeInstr.
    def exitWriteInstr(self, ctx:BitScramblerParser.WriteInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#readInstr.
    def enterReadInstr(self, ctx:BitScramblerParser.ReadInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#readInstr.
    def exitReadInstr(self, ctx:BitScramblerParser.ReadInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#loopInstr.
    def enterLoopInstr(self, ctx:BitScramblerParser.LoopInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#loopInstr.
    def exitLoopInstr(self, ctx:BitScramblerParser.LoopInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#addInstr.
    def enterAddInstr(self, ctx:BitScramblerParser.AddInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#addInstr.
    def exitAddInstr(self, ctx:BitScramblerParser.AddInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#ifInstr.
    def enterIfInstr(self, ctx:BitScramblerParser.IfInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#ifInstr.
    def exitIfInstr(self, ctx:BitScramblerParser.IfInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#ldctdInstr.
    def enterLdctdInstr(self, ctx:BitScramblerParser.LdctdInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#ldctdInstr.
    def exitLdctdInstr(self, ctx:BitScramblerParser.LdctdInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#ldctiInstr.
    def enterLdctiInstr(self, ctx:BitScramblerParser.LdctiInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#ldctiInstr.
    def exitLdctiInstr(self, ctx:BitScramblerParser.LdctiInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#addctiInstr.
    def enterAddctiInstr(self, ctx:BitScramblerParser.AddctiInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#addctiInstr.
    def exitAddctiInstr(self, ctx:BitScramblerParser.AddctiInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#jmpInstr.
    def enterJmpInstr(self, ctx:BitScramblerParser.JmpInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#jmpInstr.
    def exitJmpInstr(self, ctx:BitScramblerParser.JmpInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#nopInstr.
    def enterNopInstr(self, ctx:BitScramblerParser.NopInstrContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#nopInstr.
    def exitNopInstr(self, ctx:BitScramblerParser.NopInstrContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#addMnemonic.
    def enterAddMnemonic(self, ctx:BitScramblerParser.AddMnemonicContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#addMnemonic.
    def exitAddMnemonic(self, ctx:BitScramblerParser.AddMnemonicContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#ldctdMnemonic.
    def enterLdctdMnemonic(self, ctx:BitScramblerParser.LdctdMnemonicContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#ldctdMnemonic.
    def exitLdctdMnemonic(self, ctx:BitScramblerParser.LdctdMnemonicContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#ldctiMnemonic.
    def enterLdctiMnemonic(self, ctx:BitScramblerParser.LdctiMnemonicContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#ldctiMnemonic.
    def exitLdctiMnemonic(self, ctx:BitScramblerParser.LdctiMnemonicContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#addctiMnemonic.
    def enterAddctiMnemonic(self, ctx:BitScramblerParser.AddctiMnemonicContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#addctiMnemonic.
    def exitAddctiMnemonic(self, ctx:BitScramblerParser.AddctiMnemonicContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#outSpec.
    def enterOutSpec(self, ctx:BitScramblerParser.OutSpecContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#outSpec.
    def exitOutSpec(self, ctx:BitScramblerParser.OutSpecContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#inSpec.
    def enterInSpec(self, ctx:BitScramblerParser.InSpecContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#inSpec.
    def exitInSpec(self, ctx:BitScramblerParser.InSpecContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#condSource.
    def enterCondSource(self, ctx:BitScramblerParser.CondSourceContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#condSource.
    def exitCondSource(self, ctx:BitScramblerParser.CondSourceContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#CmpSource.
    def enterCmpSource(self, ctx:BitScramblerParser.CmpSourceContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#CmpSource.
    def exitCmpSource(self, ctx:BitScramblerParser.CmpSourceContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#RelSource.
    def enterRelSource(self, ctx:BitScramblerParser.RelSourceContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#RelSource.
    def exitRelSource(self, ctx:BitScramblerParser.RelSourceContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#NumericSource.
    def enterNumericSource(self, ctx:BitScramblerParser.NumericSourceContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#NumericSource.
    def exitNumericSource(self, ctx:BitScramblerParser.NumericSourceContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#NamedSource.
    def enterNamedSource(self, ctx:BitScramblerParser.NamedSourceContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#NamedSource.
    def exitNamedSource(self, ctx:BitScramblerParser.NamedSourceContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#labelRef.
    def enterLabelRef(self, ctx:BitScramblerParser.LabelRefContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#labelRef.
    def exitLabelRef(self, ctx:BitScramblerParser.LabelRefContext):
        pass


    # Enter a parse tree produced by BitScramblerParser#identifier.
    def enterIdentifier(self, ctx:BitScramblerParser.IdentifierContext):
        pass

    # Exit a parse tree produced by BitScramblerParser#identifier.
    def exitIdentifier(self, ctx:BitScramblerParser.IdentifierContext):
        pass



del BitScramblerParser