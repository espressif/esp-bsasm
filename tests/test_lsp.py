# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the language-server logic (pure functions, no LSP transport)."""

from bsasm.lsp import completions
from bsasm.lsp import definition
from bsasm.lsp import hover
from bsasm.lsp import parse_document
from bsasm.lsp import references
from bsasm.lsp import semantic_tokens
from bsasm.lsp import symbols
from bsasm.model import LutWidth

PROGRAM = """# comment line
main:
    set 0..7 8..15, write 8
    loopa 2 1 main
"""


def test_standard_token_kinds() -> None:
    kinds = {kind for _, _, _, kind in semantic_tokens(PROGRAM)}
    assert 'macro' in kinds  # mnemonics
    assert 'function' in kinds  # label definitions
    assert 'variable' in kinds  # label references
    assert 'number' in kinds
    assert 'comment' in kinds


def test_cfg_keys_and_values_get_distinct_kinds() -> None:
    kinds = {kind for _, _, _, kind in semantic_tokens('cfg eof_on upstream\n')}
    assert 'macro' in kinds  # the cfg directive
    assert 'property' in kinds  # the eof_on key
    assert 'enumMember' in kinds  # the upstream value


def test_symbols_are_labels() -> None:
    assert symbols(PROGRAM) == [{'name': 'main', 'kind': 'function', 'location': (1, 0, 4)}]


def test_definition_resolves_usage() -> None:
    # The 'main' jump target sits at line 3 (0-based), column 14.
    assert definition(PROGRAM, 3, 14) == (1, 0, 4)


def test_definition_on_label_self() -> None:
    assert definition(PROGRAM, 1, 1) == (1, 0, 4)


def test_references_include_definition_and_usages() -> None:
    assert references(PROGRAM, 1, 0) == [(1, 0, 4), (3, 14, 4)]
    assert references(PROGRAM, 3, 14) == [(1, 0, 4), (3, 14, 4)]
    assert references(PROGRAM, 3, 14, include_declaration=False) == [(3, 14, 4)]


def test_unknown_word_has_no_navigation() -> None:
    assert definition(PROGRAM, 3, 0) is None
    assert references(PROGRAM, 3, 0) == []


def test_definition_on_label_colon() -> None:
    # 'main:' is one LABEL token; the colon is outside len('main').
    assert definition(PROGRAM, 1, 4) == (1, 0, 4)


def test_mnemonic_is_not_a_label_reference() -> None:
    # labelRef accepts every keyword token, so 'loopa' as a jump target is
    # LOOPA, not NAME. The LOOPA mnemonic of the same bundle must not resolve.
    source = 'loopa:\n    loopa 2 1 loopa, write 8\n'
    assert definition(source, 0, 0) == (0, 0, 5)
    assert definition(source, 1, 5) is None  # the LOOPA mnemonic
    assert definition(source, 1, 14) == (0, 0, 5)  # the jump target
    assert references(source, 1, 5) == []
    assert references(source, 1, 14) == [(0, 0, 5), (1, 14, 5)]


def test_valid_program_has_no_diagnostics() -> None:
    assert parse_document(PROGRAM).diagnostics == []


def test_undefined_jump_target_is_reported() -> None:
    doc = parse_document('main:\n    jmp nowhere\n')
    assert len(doc.diagnostics) == 1
    diag = doc.diagnostics[0]
    assert (diag.location.line, diag.location.column) == (2, 9)
    assert 'Label not found' in diag.message


def test_duplicate_label_is_reported() -> None:
    doc = parse_document('main:\nmain:\n    write 8\n')
    assert any('already defined' in d.message for d in doc.diagnostics)


def test_mux_conflict_is_reported_at_analysis_time() -> None:
    doc = parse_document('main:\n    set 0 a0, set 1 32, write 8\n')
    assert len(doc.diagnostics) == 1
    diag = doc.diagnostics[0]
    assert diag.location.line == 2
    assert 'Cannot have both counters/LUT' in diag.message
    assert diag.related is not None
    assert diag.related.line == 2


def test_expected_token_collapse_names_identifiers() -> None:
    message = parse_document('main:\n    jmp 3\n').diagnostics[0].message
    assert 'expected an identifier' in message
    assert 'ADDB' not in message


def test_broken_syntax_skips_semantic_checks() -> None:
    messages = [d.message for d in parse_document('bogus_op\n    jmp nowhere\n').diagnostics]
    assert messages
    assert all('nowhere' not in message for message in messages)


def test_keyword_hover_has_documentation() -> None:
    text = hover(PROGRAM, 3, 5)  # loopa
    assert text is not None
    assert 'repeat the instruction bundle' in text


def test_hover_covers_cfg_keys() -> None:
    # The sample must be legal syntax: 'cfg trailing_bytes 8' (space, no '=').
    text = 'cfg trailing_bytes 8\nmain:\n    write 8\n'
    assert parse_document(text).diagnostics == []
    hover_text = hover(text, 0, 8)  # trailing_bytes
    assert hover_text is not None
    assert 'extra bytes' in hover_text


def test_hover_returns_none_outside_keywords() -> None:
    assert hover(PROGRAM, 1, 2) is None  # label definition
    assert hover(PROGRAM, 2, 26) is None  # number
    assert hover(PROGRAM, 2, 7) is None  # whitespace between tokens


def test_completion_groups() -> None:
    labels = {item['label'] for item in completions()}
    assert {'set', 'loopa', 'ldctibh', 'jmp', 'nop', 'cfg'} <= labels
    assert {'a15', 'b0', 'o31', 'l7', 'l', 'h', 'b<=o0'} <= labels
    # reg_mem1 high bits and the relative spellings were missing before.
    assert {'32', '63', '0+a', 'a0+a', 'b15+a', '32+a'} <= labels


def test_lut_bit_completions_follow_cfg_width() -> None:
    all_labels = {item['label'] for item in completions()}
    assert 'l31' in all_labels
    assert 'l31+a' not in all_labels  # unknown width: no relative LUT bits

    eight = {item['label'] for item in completions(LutWidth.BITS8)}
    assert 'l7' in eight
    assert 'l7+a' in eight
    assert 'l8' not in eight
    assert 'l8+a' not in eight

    thirtytwo = {item['label'] for item in completions(LutWidth.BITS32)}
    assert 'l31' in thirtytwo
    assert 'l31+a' in thirtytwo
