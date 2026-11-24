# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Human-readable diagnostic text for lexer and parser errors.

Used by the ANTLR listener in :mod:`bsasm.parsing` and by every consumer of
its diagnostics (CLI, editor, Python API), so wording cannot diverge. Keeping
the text helpers here leaves the ANTLR wiring free of diagnostic formatting.
"""

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


def lexer_offending_text(msg: str) -> str:
    """The character the lexer choked on, extracted from its message."""
    # The Python runtime's lexer message looks like
    # "token recognition error at: '#'" - the quoted part is the character.
    prefix = 'token recognition error at: '
    if msg.startswith(prefix):
        return msg[len(prefix) :].strip('\'"')
    return msg


def parser_message(msg: str, offending_text: str) -> str:
    """Rewrite an ANTLR parser message for users.

    ANTLR messages are spelled for grammar developers ('mismatched input
    'x' expecting {...}'); extract the offending token and, when possible,
    render the expected set readably.
    """
    expected = expected_tokens(msg)
    message = f'unexpected {offending_text!r}'
    if expected:
        message += f', expected {expected}'
    return message


def expected_tokens(msg: str) -> str:
    """Readable rendering of the tokens ANTLR says it was expecting."""
    if 'expecting' not in msg:
        return ''
    tail = msg.rsplit('expecting', 1)[1].strip()
    if not (tail.startswith('{') and tail.endswith('}')):
        # A single token name, e.g. "expecting NUMBER".
        return TOKEN_LABELS.get(tail.strip('"\''), f'`{tail}`')
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
