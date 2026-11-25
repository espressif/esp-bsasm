# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Human-readable diagnostic text for lexer and parser errors.

Used by the ANTLR listener and error strategy in :mod:`bsasm.parsing` and by
every consumer of its diagnostics (CLI, editor, Python API), so wording
cannot diverge. The helpers build their text from the recognizer's
structured state - the offending span and the expected-token set - instead
of scraping ANTLR's own message strings: the runtime's data is the stable
interface, its phrasing is not.
"""

from antlr4 import Parser, Token
from antlr4.Lexer import Lexer

# Human-readable spellings for the non-literal token types that can appear
# in an expected-token set. Keyword tokens need no entry: they render
# through their literal names ('set', 'equal', ...).
TOKEN_LABELS = {
    'COMMA': "','",
    'NUMBER': 'a number',
    'NAME': 'an identifier',
    'LABEL': 'a label definition',
    'NEWLINE': 'end of line',
    'RANGE': "'..'",
}


def lexer_offending_text(recognizer: Lexer) -> str:
    """The character(s) the lexer choked on.

    Reconstructed the same way the runtime builds its own 'token recognition
    error at: ...' message (see ``Lexer.notifyListeners``), so the text
    stays right even if that wording changes.
    """
    text = recognizer._input.getText(recognizer._tokenStartCharIndex, recognizer._input.index)
    display: str = recognizer.getErrorDisplay(text)
    return display


def parser_message(recognizer: Parser, offending_text: str, *, include_expected: bool) -> str:
    """A readable parser error: what was found, then what would have fit.

    ``include_expected`` is off where the offending token is not itself the
    problem (a *missing* token points at what follows the gap), matching the
    cases ANTLR phrases without 'expecting ...'.
    """
    message = f'unexpected {offending_text!r}'
    if include_expected:
        expected = expected_tokens(recognizer)
        if expected:
            message += f', expected {expected}'
    return message


def expected_tokens(recognizer: Parser) -> str:
    """Readable rendering of the parser's expected-token set at this point."""
    interval = recognizer.getExpectedTokens()
    labels = sorted(_token_label(recognizer, token_type) for token_type in interval)
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


def _token_label(recognizer: Parser, token_type: int) -> str:
    """How one token type should read inside an expected-token list."""
    if token_type == Token.EOF:
        return 'end of file'
    name = recognizer.symbolicNames[token_type]
    if name in TOKEN_LABELS:
        return TOKEN_LABELS[name]
    # literalNames stops at the last literal token; word-shaped tokens
    # (NAME, NUMBER, ...) have no entry at all.
    literal: str | None = recognizer.literalNames[token_type] if token_type < len(recognizer.literalNames) else None
    if literal is not None:
        # A keyword: the literal name is the spelling users type ('set',
        # 'equal'), already single-quoted by the runtime.
        return literal
    return f'`{name}`'
