# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""ANTLR driver: turns bsasm source text into a list of typed statements.

The syntax itself is defined in ``BitScrambler.g4``; this module wires up the
generated lexer/parser, converts ANTLR's diagnostics into the assembler's own
:class:`~bsasm.errors.AssemblerSyntaxError` and hands the parse tree to the
builder. Statements are built by :class:`bsasm.builder.ProgramBuilder`.
"""

from antlr4 import CommonTokenStream
from antlr4 import InputStream
from antlr4 import Lexer
from antlr4 import Parser
from antlr4 import Token
from antlr4.error.ErrorListener import ErrorListener

from bsasm.builder import ProgramBuilder
from bsasm.builder import Statement
from bsasm.errors import AssemblerSyntaxError
from bsasm.errors import Location
from bsasm.generated.BitScramblerLexer import BitScramblerLexer
from bsasm.generated.BitScramblerParser import BitScramblerParser

# Human-readable spellings for the token names ANTLR mentions in its
# 'expecting {...}' diagnostics.
TOKEN_LABELS = {
    'COMMA': "','",
    'NUMBER': 'a number',
    'NAME': 'an identifier',
    'LABEL': 'a label definition',
    'NEWLINE': 'end of line',
    'RANGE': "'..'",
}


class _DiagnosticErrorListener(ErrorListener):
    """Raise an :class:`AssemblerSyntaxError` on the first lexer or parser problem.

    ANTLR's default recovery would happily continue after an error and
    produce a parse tree for a program the user never wrote, so every error
    aborts assembly immediately.
    """

    def __init__(self, is_lexer: bool) -> None:
        super().__init__()
        self._is_lexer = is_lexer

    def syntaxError(
        self,
        recognizer: Lexer | Parser,
        offending_symbol: Token | None,
        line: int,
        column: int,
        msg: str,
        e: Exception | None,
    ) -> None:
        if self._is_lexer:
            text = _lexer_offending_text(msg)
            message = f'unexpected character {text!r}'
        else:
            text = offending_symbol.text if offending_symbol is not None else '<end of file>'
            message = _parser_message(msg, text, recognizer)
        # ANTLR lines are 1-based already; its columns are 0-based, ours are not.
        raise AssemblerSyntaxError(Location(line, column + 1, text), message)


def _lexer_offending_text(msg: str) -> str:
    # The Python runtime's lexer message looks like
    # "token recognition error at: '#'" - the quoted part is the character.
    prefix = 'token recognition error at: '
    if msg.startswith(prefix):
        return msg[len(prefix) :].strip('\'"')
    return msg


def _parser_message(msg: str, text: str, recognizer: Parser) -> str:
    # ANTLR parser messages are spelled for grammar developers, not for
    # users ('mismatched input 'x' expecting {...}'). Extract the offending
    # token and, when possible, render the expected set readably.
    expected = _expected_tokens(msg, recognizer)
    message = f'unexpected {text!r}'
    if expected:
        message += f', expected {expected}'
    return message


def _expected_tokens(msg: str, recognizer: Parser) -> str:
    if 'expecting' not in msg:
        return ''
    tail = msg.rsplit('expecting', 1)[1].strip()
    if not (tail.startswith('{') and tail.endswith('}')):
        # A single token name, e.g. "expecting NUMBER".
        return TOKEN_LABELS.get(tail.strip("'"), f'`{tail}`')
    names = [name.strip() for name in tail[1:-1].split(',')]
    labels = sorted(TOKEN_LABELS.get(name, f'`{name}`') for name in names)
    if len(labels) > 6:
        return f'one of {", ".join(labels[:6])}, ...'
    if len(labels) == 1:
        return labels[0]
    return f'one of {", ".join(labels)}'


def parse(source: str) -> list:
    """Parse bsasm ``source`` into a list of typed statements.

    The source is always assembled with a trailing newline (appended here if
    missing), mirroring the original assembler: it makes 'file ends inside a
    bundle/comment' behave like 'file ends at end of line'.
    """
    if not source.endswith('\n'):
        source += '\n'

    lexer = BitScramblerLexer(InputStream(source))
    lexer.removeErrorListeners()
    lexer.addErrorListener(_DiagnosticErrorListener(is_lexer=True))
    parser = BitScramblerParser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(_DiagnosticErrorListener(is_lexer=False))

    statements: list[Statement] = ProgramBuilder().visit(parser.program())
    return statements
