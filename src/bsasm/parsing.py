# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""ANTLR driver: turn bsasm source into typed statements and diagnostics.

``BitScrambler.g4`` owns the syntax; this module wires up the generated
lexer/parser, converts ANTLR diagnostics into :class:`AssemblerSyntaxError`,
and hands the parse tree to :class:`~bsasm.builder.ProgramBuilder`. Every
syntax problem is collected in one pass.
"""

from dataclasses import dataclass

from antlr4 import CommonTokenStream, InputStream, Lexer, Parser, Token
from antlr4.error.ErrorListener import ErrorListener

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


class _DiagnosticListener(ErrorListener):
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
        e: Exception | None,
    ) -> None:
        if isinstance(recognizer, Lexer):
            text = lexer_offending_text(msg)
            message = f'unexpected character {text!r}'
        else:
            text = offending_symbol.text if offending_symbol is not None else '<end of file>'
            message = parser_message(msg, text)
        # ANTLR lines are 1-based and columns 0-based; ours are both 1-based.
        self.errors.append(AssemblerSyntaxError(Location(line, column + 1, text), message))


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
    tree = parser.program()

    tokens = [t for t in token_stream.tokens if t.type != Token.EOF]
    statements: list[Statement] = [] if listener.errors else ProgramBuilder().visit(tree)
    return ParsedSource(source=source, tokens=tokens, statements=statements, errors=listener.errors)
