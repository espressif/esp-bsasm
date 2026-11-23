# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""ANTLR driver: turns bsasm source text into a list of typed statements.

The syntax itself is defined in ``BitScrambler.g4``; this module wires up the
generated lexer/parser, converts ANTLR's diagnostics into the assembler's own
:class:`~bsasm.errors.AssemblerSyntaxError` and hands the parse tree to the
builder. Statements are built by :class:`bsasm.builder.ProgramBuilder`.

:func:`parse` aborts on the first syntax error (the CLI). :func:`parse_collecting`
records every syntax error the recognizer reports so the language server can
show them all; the lexer/parser wiring is otherwise identical.
"""

from dataclasses import dataclass

from antlr4 import CommonTokenStream
from antlr4 import InputStream
from antlr4 import Lexer
from antlr4 import Parser
from antlr4 import Token
from antlr4.error.ErrorListener import ErrorListener

from bsasm.builder import ProgramBuilder
from bsasm.errors import AssemblerSyntaxError
from bsasm.errors import Location
from bsasm.generated.BitScramblerLexer import BitScramblerLexer
from bsasm.generated.BitScramblerParser import BitScramblerParser
from bsasm.model import Statement

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


def _syntax_diagnostic(
    recognizer: Lexer | Parser,
    offending_symbol: Token | None,
    line: int,
    column: int,
    msg: str,
) -> tuple[Location, str]:
    if isinstance(recognizer, Lexer):
        text = _lexer_offending_text(msg)
        message = f'unexpected character {text!r}'
    else:
        text = offending_symbol.text if offending_symbol is not None else '<end of file>'
        message = _parser_message(msg, text)
    # ANTLR lines are 1-based already; its columns are 0-based, ours are not.
    return Location(line, column + 1, text), message


class _FailFastListener(ErrorListener):
    """Raise an :class:`AssemblerSyntaxError` on the first lexer or parser problem.

    ANTLR's default recovery would happily continue after an error and
    produce a parse tree for a program the user never wrote, so every error
    aborts assembly immediately.
    """

    def syntaxError(
        self,
        recognizer: Lexer | Parser,
        offending_symbol: Token | None,
        line: int,
        column: int,
        msg: str,
        e: Exception | None,
    ) -> None:
        location, message = _syntax_diagnostic(recognizer, offending_symbol, line, column, msg)
        raise AssemblerSyntaxError(location, message)


class _CollectingListener(ErrorListener):
    """Collect every syntax error instead of aborting on the first one."""

    def __init__(self) -> None:
        super().__init__()
        self.errors: list[tuple[Location, str]] = []

    def syntaxError(
        self,
        recognizer: Lexer | Parser,
        offending_symbol: Token | None,
        line: int,
        column: int,
        msg: str,
        e: Exception | None,
    ) -> None:
        self.errors.append(_syntax_diagnostic(recognizer, offending_symbol, line, column, msg))


def _lexer_offending_text(msg: str) -> str:
    # The Python runtime's lexer message looks like
    # "token recognition error at: '#'" - the quoted part is the character.
    prefix = 'token recognition error at: '
    if msg.startswith(prefix):
        return msg[len(prefix) :].strip('\'"')
    return msg


def _parser_message(msg: str, text: str) -> str:
    # ANTLR parser messages are spelled for grammar developers, not for
    # users ('mismatched input 'x' expecting {...}'). Extract the offending
    # token and, when possible, render the expected set readably.
    expected = _expected_tokens(msg)
    message = f'unexpected {text!r}'
    if expected:
        message += f', expected {expected}'
    return message


def _expected_tokens(msg: str) -> str:
    if 'expecting' not in msg:
        return ''
    tail = msg.rsplit('expecting', 1)[1].strip()
    if not (tail.startswith('{') and tail.endswith('}')):
        # A single token name, e.g. "expecting NUMBER".
        return TOKEN_LABELS.get(tail.strip("'"), f'`{tail}`')
    names = [name.strip() for name in tail[1:-1].split(',')]
    labels = sorted(TOKEN_LABELS.get(name, f'`{name}`') for name in names)
    if len(labels) > 6:
        # A wide expected set containing NAME is an identifier position: the
        # grammar accepts every keyword as an identifier there, so listing
        # them all is noise ('jmp 3' -> "expected an identifier").
        if 'an identifier' in labels:
            return 'an identifier'
        return f'one of {", ".join(labels[:6])}, ...'
    if len(labels) == 1:
        return labels[0]
    return f'one of {", ".join(labels)}'


def _parse_with_listener(source: str, listener: ErrorListener) -> tuple[str, object, list[Token]]:
    """Shared lexer/parser setup. ``source`` is returned with a trailing newline."""
    if not source.endswith('\n'):
        source += '\n'

    lexer = BitScramblerLexer(InputStream(source))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    token_stream = CommonTokenStream(lexer)
    parser = BitScramblerParser(token_stream)
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    tree = parser.program()
    tokens = [t for t in token_stream.tokens if t.type != Token.EOF]
    return source, tree, tokens


def parse(source: str) -> list[Statement]:
    """Parse bsasm ``source`` into a list of typed statements.

    The source is always assembled with a trailing newline (appended here if
    missing), mirroring the original assembler: it makes 'file ends inside a
    bundle/comment' behave like 'file ends at end of line'.
    """
    _, tree, _ = _parse_with_listener(source, _FailFastListener())
    statements: list[Statement] = ProgramBuilder().visit(tree)
    return statements


@dataclass(frozen=True, slots=True)
class CollectedParse:
    """Result of :func:`parse_collecting`."""

    source: str
    tokens: list[Token]
    statements: list[Statement]
    errors: list[tuple[Location, str]]


def parse_collecting(source: str) -> CollectedParse:
    """Parse like :func:`parse`, but collect every syntax error instead of aborting.

    ``statements`` is empty when any syntax error was found: a recovered
    tree is not a program the user wrote. Hidden-channel tokens (comments)
    are included in ``tokens``.
    """
    collector = _CollectingListener()
    source, tree, tokens = _parse_with_listener(source, collector)
    statements: list[Statement] = []
    if not collector.errors:
        statements = ProgramBuilder().visit(tree)
    return CollectedParse(source=source, tokens=tokens, statements=statements, errors=collector.errors)
