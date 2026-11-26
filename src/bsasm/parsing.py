# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""ANTLR driver: turn bsasm source into typed statements and diagnostics.

``BitScrambler.g4`` owns the syntax; this module wires up the generated
lexer/parser, converts ANTLR diagnostics into :class:`AssemblerSyntaxError`,
and hands the parse tree to :class:`~bsasm.builder.ProgramBuilder`. Every
syntax problem is collected in one pass.

Parser errors are reported by :class:`_DiagnosticErrorStrategy`, the ANTLR
extension point where the *kind* of error (mismatched, extraneous, missing,
no viable alternative) is still known structurally - so diagnostics never
depend on the wording of the runtime's own messages.
"""

from dataclasses import dataclass

from antlr4 import CommonTokenStream, InputStream, Lexer, Parser, Token
from antlr4.error.ErrorListener import ErrorListener
from antlr4.error.Errors import InputMismatchException, NoViableAltException, RecognitionException
from antlr4.error.ErrorStrategy import DefaultErrorStrategy

from bsasm.builder import ProgramBuilder
from bsasm.diagnostics import lexer_offending_text, parser_message
from bsasm.errors import AssemblerSyntaxError, Location
from bsasm.generated.BitScramblerLexer import BitScramblerLexer
from bsasm.generated.BitScramblerParser import BitScramblerParser
from bsasm.model import Statement


@dataclass(frozen=True, slots=True)
class ParsedSource:
    """Everything derived from one parse: IR, tokens and all diagnostics."""

    source: str
    tokens: list[Token]
    statements: list[Statement]
    errors: list[AssemblerSyntaxError]


def _offending_text(token: Token | None) -> str:
    """The token to quote in a diagnostic; the EOF token has no text."""
    if token is None or token.type == Token.EOF:
        return '<end of file>'
    text: str = token.text
    return text


class _DiagnosticListener(ErrorListener):
    """Collects lexer diagnostics (and any parser error the strategy missed).

    Parser errors normally arrive through :class:`_DiagnosticErrorStrategy`;
    the parser branch below is a fallback for runtime paths the strategy
    does not override (the grammar has no predicates, so none exist today).
    """

    def __init__(self) -> None:
        super().__init__()
        self.errors: list[AssemblerSyntaxError] = []

    def syntaxError(
        self,
        recognizer: Lexer | Parser,
        offending_symbol: Token | None,
        line: int,
        column: int,
        msg: str,
        e: RecognitionException | None,
    ) -> None:
        if isinstance(recognizer, Lexer):
            text = lexer_offending_text(recognizer)
            message = f'unexpected character {text!r}'
        else:
            text = _offending_text(offending_symbol)
            message = parser_message(recognizer, text, include_expected=False)
        # ANTLR lines are 1-based and columns 0-based; ours are both 1-based.
        self.errors.append(AssemblerSyntaxError(Location(line, column + 1, text), message))


class _DiagnosticErrorStrategy(DefaultErrorStrategy):
    """Reports parser errors as located diagnostics at the point they are classified.

    Only the four ``report*`` entry points are overridden; error *recovery*
    (single-token insertion/deletion, resync) is inherited unchanged, so the
    parse still collects every problem in one pass. The recovery-suppression
    guard and ``beginErrorCondition`` calls mirror the base implementation
    exactly.
    """

    def __init__(self, errors: list[AssemblerSyntaxError]) -> None:
        super().__init__()
        self._errors = errors

    def reportInputMismatch(self, recognizer: Parser, e: InputMismatchException) -> None:
        self._report(recognizer, e.offendingToken, include_expected=True)

    def reportNoViableAlternative(self, recognizer: Parser, e: NoViableAltException) -> None:
        self._report(recognizer, e.offendingToken, include_expected=False)

    def reportUnwantedToken(self, recognizer: Parser) -> None:
        if self.inErrorRecoveryMode(recognizer):
            return
        self.beginErrorCondition(recognizer)
        self._report(recognizer, recognizer.getCurrentToken(), include_expected=True)

    def reportMissingToken(self, recognizer: Parser) -> None:
        if self.inErrorRecoveryMode(recognizer):
            return
        self.beginErrorCondition(recognizer)
        # The current token follows the gap; listing expectations reads wrong.
        self._report(recognizer, recognizer.getCurrentToken(), include_expected=False)

    def _report(self, recognizer: Parser, token: Token, *, include_expected: bool) -> None:
        text = _offending_text(token)
        message = parser_message(recognizer, text, include_expected=include_expected)
        self._errors.append(AssemblerSyntaxError(Location(token.line, token.column + 1, text), message))


def parse(source: str) -> ParsedSource:
    """Parse bsasm ``source`` into statements plus every syntax error.

    A trailing newline is appended when missing, as in the original assembler:
    a file ending inside a bundle/comment behaves like one ending at a newline.
    ``statements`` is empty when errors were found - a recovered tree is not a
    program the user wrote. Hidden-channel tokens (comments) stay in ``tokens``.
    """
    if not source.endswith('\n'):
        source += '\n'

    listener = _DiagnosticListener()
    lexer = BitScramblerLexer(InputStream(source))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    token_stream = CommonTokenStream(lexer)
    parser = BitScramblerParser(token_stream)
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    # The Python runtime exposes no setter; assigning the handler is the
    # documented port of Java's setErrorHandler().
    parser._errHandler = _DiagnosticErrorStrategy(listener.errors)
    tree = parser.program()

    # The parse above consumes to EOF, which already fetched every token;
    # fill() makes that guarantee explicit instead of incidental.
    token_stream.fill()
    tokens = [t for t in token_stream.tokens if t.type != Token.EOF]
    statements: list[Statement] = [] if listener.errors else ProgramBuilder().visit(tree)
    return ParsedSource(source=source, tokens=tokens, statements=statements, errors=listener.errors)
