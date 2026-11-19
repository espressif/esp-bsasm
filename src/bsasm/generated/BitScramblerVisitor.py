# Generated from BitScrambler.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .BitScramblerParser import BitScramblerParser
else:
    from BitScramblerParser import BitScramblerParser

# This class defines a complete generic visitor for a parse tree produced by BitScramblerParser.

class BitScramblerVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by BitScramblerParser#program.
    def visitProgram(self, ctx:BitScramblerParser.ProgramContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#BlankLine.
    def visitBlankLine(self, ctx:BitScramblerParser.BlankLineContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#ContentLine.
    def visitContentLine(self, ctx:BitScramblerParser.ContentLineContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#labelDef.
    def visitLabelDef(self, ctx:BitScramblerParser.LabelDefContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#lineContent.
    def visitLineContent(self, ctx:BitScramblerParser.LineContentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#cfgStmt.
    def visitCfgStmt(self, ctx:BitScramblerParser.CfgStmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#cfgBoolean.
    def visitCfgBoolean(self, ctx:BitScramblerParser.CfgBooleanContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#lutStmt.
    def visitLutStmt(self, ctx:BitScramblerParser.LutStmtContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#lutValue.
    def visitLutValue(self, ctx:BitScramblerParser.LutValueContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#bundle.
    def visitBundle(self, ctx:BitScramblerParser.BundleContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubSet.
    def visitSubSet(self, ctx:BitScramblerParser.SubSetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubWrite.
    def visitSubWrite(self, ctx:BitScramblerParser.SubWriteContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubRead.
    def visitSubRead(self, ctx:BitScramblerParser.SubReadContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubLoop.
    def visitSubLoop(self, ctx:BitScramblerParser.SubLoopContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubAdd.
    def visitSubAdd(self, ctx:BitScramblerParser.SubAddContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubIf.
    def visitSubIf(self, ctx:BitScramblerParser.SubIfContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubLdctd.
    def visitSubLdctd(self, ctx:BitScramblerParser.SubLdctdContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubLdcti.
    def visitSubLdcti(self, ctx:BitScramblerParser.SubLdctiContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubAddcti.
    def visitSubAddcti(self, ctx:BitScramblerParser.SubAddctiContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubJmp.
    def visitSubJmp(self, ctx:BitScramblerParser.SubJmpContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#SubNop.
    def visitSubNop(self, ctx:BitScramblerParser.SubNopContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#setInstr.
    def visitSetInstr(self, ctx:BitScramblerParser.SetInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#writeInstr.
    def visitWriteInstr(self, ctx:BitScramblerParser.WriteInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#readInstr.
    def visitReadInstr(self, ctx:BitScramblerParser.ReadInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#loopInstr.
    def visitLoopInstr(self, ctx:BitScramblerParser.LoopInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#addInstr.
    def visitAddInstr(self, ctx:BitScramblerParser.AddInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#ifInstr.
    def visitIfInstr(self, ctx:BitScramblerParser.IfInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#ldctdInstr.
    def visitLdctdInstr(self, ctx:BitScramblerParser.LdctdInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#ldctiInstr.
    def visitLdctiInstr(self, ctx:BitScramblerParser.LdctiInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#addctiInstr.
    def visitAddctiInstr(self, ctx:BitScramblerParser.AddctiInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#jmpInstr.
    def visitJmpInstr(self, ctx:BitScramblerParser.JmpInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#nopInstr.
    def visitNopInstr(self, ctx:BitScramblerParser.NopInstrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#addMnemonic.
    def visitAddMnemonic(self, ctx:BitScramblerParser.AddMnemonicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#ldctdMnemonic.
    def visitLdctdMnemonic(self, ctx:BitScramblerParser.LdctdMnemonicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#ldctiMnemonic.
    def visitLdctiMnemonic(self, ctx:BitScramblerParser.LdctiMnemonicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#addctiMnemonic.
    def visitAddctiMnemonic(self, ctx:BitScramblerParser.AddctiMnemonicContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#outSpec.
    def visitOutSpec(self, ctx:BitScramblerParser.OutSpecContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#inSpec.
    def visitInSpec(self, ctx:BitScramblerParser.InSpecContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#condSource.
    def visitCondSource(self, ctx:BitScramblerParser.CondSourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#CmpSource.
    def visitCmpSource(self, ctx:BitScramblerParser.CmpSourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#RelSource.
    def visitRelSource(self, ctx:BitScramblerParser.RelSourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#NumericSource.
    def visitNumericSource(self, ctx:BitScramblerParser.NumericSourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#NamedSource.
    def visitNamedSource(self, ctx:BitScramblerParser.NamedSourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#labelRef.
    def visitLabelRef(self, ctx:BitScramblerParser.LabelRefContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by BitScramblerParser#identifier.
    def visitIdentifier(self, ctx:BitScramblerParser.IdentifierContext):
        return self.visitChildren(ctx)



del BitScramblerParser