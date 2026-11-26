# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the language-server logic (pure functions, no LSP transport)."""

import pytest
from lsprotocol import types

from bsasm import lsp
from bsasm.lsp import completions_at, definition, hover, parse_document, references, semantic_tokens, symbols

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


def test_editor_accepts_every_instruction() -> None:
    # The editor does not know the target chip, so extra instructions are not
    # an error here. The assembler rejects them unless the caller enables them.
    assert parse_document('addctia\n').diagnostics == []


def test_undefined_jump_target_is_reported() -> None:
    doc = parse_document('main:\n    jmp nowhere\n')
    assert len(doc.diagnostics) == 1
    diag = doc.diagnostics[0]
    assert (diag.location.line, diag.location.column) == (2, 9)
    assert 'Label not found' in diag.message


def test_all_semantic_errors_are_reported() -> None:
    # Every entry point reports the full set; this checks the editor path.
    src = 'cfg prefetch 2\ncfg lut_width_bits 7\ncfg trailing_bytes 99999\nmain:\n    write 12\n    read 7\n'
    messages = [d.message for d in parse_document(src).diagnostics]
    assert len(messages) == 5
    assert any('allowed value for prefetch' in m for m in messages)
    assert any('allowed value for lut_width_bits' in m for m in messages)
    assert any('out of range' in m for m in messages)
    assert any('bits to write' in m for m in messages)
    assert any('bits to read' in m for m in messages)


def test_all_invalid_lut_values_are_reported() -> None:
    # One bad value must not hide the others in the same LUT statement.
    doc = parse_document('cfg lut_width_bits 8\nlut 300, -200, 7\n')
    assert len(doc.diagnostics) == 2
    assert all('out of range' in d.message for d in doc.diagnostics)


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


def test_too_many_instructions_is_reported() -> None:
    # The encoder used to be the only place that checked the 8-instruction
    # hardware limit; the editor showed no diagnostic for a 9-instruction file.
    doc = parse_document('nop\n' * 9)
    assert len(doc.diagnostics) == 1
    assert 'more than 8 instructions' in doc.diagnostics[0].message
    assert doc.diagnostics[0].location.line == 9


def test_failed_bundle_does_not_shift_jump_bounds() -> None:
    # 'write 12' fails to build, but it still occupies a bundle slot. The jump
    # to 'target' (bundle 2) must not be judged against the 2 successfully-built
    # insts, which would spuriously report it as pointing past the end.
    src = 'main:\n    write 12\n    nop\ntarget:\n    jmp target\n'
    messages = [d.message for d in parse_document(src).diagnostics]
    assert len(messages) == 1
    assert 'bits to write' in messages[0]
    assert not any('past the end' in m for m in messages)


def test_hardware_limit_counts_bundles_not_built_insts() -> None:
    # Nine bundles even though one fails to build: the limit is about what the
    # user wrote, so it must still fire alongside the bad-width error.
    src = 'write 12\n' + 'nop\n' * 8
    messages = [d.message for d in parse_document(src).diagnostics]
    assert any('bits to write' in m for m in messages)
    assert any('more than 8 instructions' in m for m in messages)


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


def test_hover_keeps_text_wrapped_across_lines() -> None:
    # A following string literal is not part of the assignment unless the
    # whole value is parenthesized. ADDCTIBH's second sentence must survive.
    text = hover('addctibh\n', 0, 0)
    assert text is not None
    assert 'counter b' in text
    assert 'upper/lower half' in text
    assert 'bare form writes both halves' in text


def test_hover_covers_cfg_keys() -> None:
    # The sample must be legal syntax: 'cfg trailing_bytes 8' (space, no '=').
    text = 'cfg trailing_bytes 8\nmain:\n    write 8\n'
    assert parse_document(text).diagnostics == []
    hover_text = hover(text, 0, 8)  # trailing_bytes
    assert hover_text is not None
    assert 'extra bytes' in hover_text


def test_spans_are_positional() -> None:
    spans = semantic_tokens(PROGRAM)
    # 0-based positions, non-negative, ordered by (line, column).
    assert spans == sorted(spans)
    assert all(line >= 0 and col >= 0 and length > 0 for line, col, length, _ in spans)


def test_syntax_error_is_collected_with_location() -> None:
    doc = parse_document('nop, \nnonsense !!\n')
    assert doc.diagnostics
    first = doc.diagnostics[0]
    assert first.location.line >= 1  # one-based, matching the CLI
    assert first.message


def test_hover_returns_none_outside_keywords() -> None:
    assert hover(PROGRAM, 1, 2) is None  # label definition
    assert hover(PROGRAM, 2, 26) is None  # number
    assert hover(PROGRAM, 2, 7) is None  # whitespace between tokens


def test_cfg_value_table_matches_grammar_keys() -> None:
    # A new cfg key in the grammar must also get an entry here, or its value
    # position silently stops completing.
    from bsasm.isa import CFG_VALUES
    from bsasm.lsp import _CFG_KEY_TOKENS, _keyword_spelling

    assert set(CFG_VALUES) == {_keyword_spelling(token) for token in _CFG_KEY_TOKENS}


def test_completion_after_cfg_offers_only_cfg_keys() -> None:
    doc = parse_document('cfg \nmain:\n    nop\n')
    labels = {item['label'] for item in completions_at(doc, 0, 4)}
    assert labels == {'prefetch', 'trailing_bytes', 'eof_on', 'lut_width_bits', 'loop_ends_on'}
    assert 'loopa' not in labels  # the regression: cfg used to offer every mnemonic
    assert 'upstream' not in labels  # values belong to the next position


@pytest.mark.parametrize(
    'key,expected',
    [
        ('prefetch', {'true', 'false', '1', '0'}),
        ('eof_on', {'upstream', 'downstream'}),
        ('lut_width_bits', {'8', '16', '32'}),
        ('loop_ends_on', {'equal', 'equal_or_greater'}),
        ('trailing_bytes', set()),  # arbitrary integer, nothing enumerable
    ],
)
def test_completion_after_cfg_key_offers_only_its_values(key: str, expected: set[str]) -> None:
    line = f'cfg {key} '
    doc = parse_document(line + '\n')
    assert {item['label'] for item in completions_at(doc, 0, len(line))} == expected


@pytest.mark.parametrize(
    'line,column,expected,absent',
    [
        ('cfg pref\n', 9, {'prefetch'}, {'true'}),  # still typing a key
        ('cfg prefetch\n', 12, {'true', 'false', '1', '0'}, {'prefetch'}),  # full key, no space yet
    ],
)
def test_completion_without_trailing_space(line: str, column: int, expected: set[str], absent: set[str]) -> None:
    doc = parse_document(line)
    labels = {item['label'] for item in completions_at(doc, 0, column)}
    assert expected <= labels
    assert not absent & labels


def test_completion_at_line_start_offers_mnemonics_only() -> None:
    doc = parse_document('main:\n    nop\n')
    labels = {item['label'] for item in completions_at(doc, 1, 4)}
    assert {'loopa', 'cfg', 'set', 'write'} <= labels
    assert 'a0' not in labels
    assert 'upstream' not in labels


def test_completion_after_set_offers_output_bits() -> None:
    # The first 'set' operand is an output bit number (0..31), not a mux source.
    doc = parse_document('main:\n    set \n')
    labels = {item['label'] for item in completions_at(doc, 1, 8)}
    assert labels == {str(bit) for bit in range(32)}
    assert 'a0' not in labels
    assert 'h' not in labels
    assert 'l0' not in labels


def test_completion_after_set_offers_sources() -> None:
    doc = parse_document('main:\n    set 0 \n')
    labels = {item['label'] for item in completions_at(doc, 1, 10)}
    assert {'0', '31', 'l0', 'h', 'a0', 'b<=o0', '0+a'} <= labels
    # reg_mem1 high bits and the relative spellings were missing before.
    assert {'32', '63', 'a0+a', 'b15+a', '32+a'} <= labels
    assert 'loopa' not in labels


def test_completion_sources_follow_cfg_lut_width() -> None:
    # At the input-operand position (after 'set 0 ') the parsed lut_width is
    # available even though the cursor is mid-line, so LUT bits filter exactly.
    eight = parse_document('cfg lut_width_bits 8\nmain:\n    set 0 1\n')
    labels8 = {item['label'] for item in completions_at(eight, 2, 10)}
    assert {'l7', 'l7+a'} <= labels8
    assert not {'l8', 'l8+a'} & labels8

    full = parse_document('cfg lut_width_bits 32\nmain:\n    set 0 1\n')
    labels32 = {item['label'] for item in completions_at(full, 2, 10)}
    assert {'l31', 'l31+a'} <= labels32


@pytest.mark.parametrize(
    'source,line,column,expected',
    [
        ('main:\n    nop\nother:\n    jmp \n', 3, 8, {'main', 'other'}),
        ('main:\n    if h \n', 1, 9, {'main'}),
    ],
)
def test_completion_at_label_position_offers_labels(source: str, line: int, column: int, expected: set[str]) -> None:
    doc = parse_document(source)
    assert {item['label'] for item in completions_at(doc, line, column)} == expected


def test_completion_after_if_offers_sources() -> None:
    doc = parse_document('main:\n    if \n')
    assert 'h' in {item['label'] for item in completions_at(doc, 1, 8)}


def test_completion_after_write_offers_widths() -> None:
    doc = parse_document('main:\n    write \n')
    assert {item['label'] for item in completions_at(doc, 1, 10)} == {'0', '8', '16', '32'}


def test_completion_after_comma_offers_mnemonics() -> None:
    doc = parse_document('main:\n    set 0 1, \n')
    labels = {item['label'] for item in completions_at(doc, 1, 13)}
    assert 'write' in labels
    assert 'a0' not in labels


def test_completion_in_comment_and_after_lut_is_empty() -> None:
    doc = parse_document('main:\n    # cfg \n    lut \n')
    assert completions_at(doc, 1, 9) == []
    assert completions_at(doc, 2, 8) == []


# ---------------------------------------------------------------------------
# Handlers (pygls dispatch; test_lsp_stdio.py drives the real server)
# ---------------------------------------------------------------------------


class _FakeDocument:
    """Just enough of a TextDocumentItem for the handlers in bsasm.lsp."""

    def __init__(self, source: str) -> None:
        self.source = source


class _FakeWorkspace:
    def __init__(self, source: str) -> None:
        self.document = _FakeDocument(source)

    def get_text_document(self, uri: str) -> _FakeDocument:
        return self.document


class _FakeLanguageServer:
    """Records published diagnostics against a mutable workspace document."""

    def __init__(self, source: str) -> None:
        self.workspace = _FakeWorkspace(source)
        self.published: list[types.PublishDiagnosticsParams] = []
        self.logs: list[str] = []

    def text_document_publish_diagnostics(self, params: types.PublishDiagnosticsParams) -> None:
        self.published.append(params)

    def window_log_message(self, params: types.LogMessageParams) -> None:
        self.logs.append(params.message)


def test_did_open_publishes_diagnostics() -> None:
    ls = _FakeLanguageServer(PROGRAM)
    lsp.did_open(
        ls,
        types.DidOpenTextDocumentParams(
            text_document=types.TextDocumentItem(uri='file:///t.bsasm', language_id='bsasm', version=1, text=PROGRAM)
        ),
    )
    assert len(ls.published) == 1
    assert ls.published[0].diagnostics == []


def test_did_open_publishes_semantic_errors() -> None:
    ls = _FakeLanguageServer('jmp nowhere\n')
    lsp.did_open(
        ls,
        types.DidOpenTextDocumentParams(
            text_document=types.TextDocumentItem(
                uri='file:///t.bsasm', language_id='bsasm', version=1, text='jmp nowhere\n'
            )
        ),
    )
    assert [d.message for d in ls.published[0].diagnostics] == ["'nowhere': Label not found."]


def test_did_open_publishes_related_information() -> None:
    # Conflicting sources have a second location: the editor shows it as
    # related information.
    ls = _FakeLanguageServer('set 0 a0, set 1 32\n')
    lsp.did_open(
        ls,
        types.DidOpenTextDocumentParams(
            text_document=types.TextDocumentItem(
                uri='file:///t.bsasm', language_id='bsasm', version=1, text='set 0 a0, set 1 32\n'
            )
        ),
    )
    diagnostics = ls.published[0].diagnostics
    assert diagnostics
    assert diagnostics[0].related_information


def test_on_hover_returns_none_outside_keywords() -> None:
    # A number token has no hover documentation.
    assert (
        lsp.on_hover(
            _FakeLanguageServer('main:\n    write 8\n'),
            types.HoverParams(
                text_document=types.TextDocumentIdentifier(uri='u'),
                position=types.Position(line=1, character=9),
            ),
        )
        is None
    )


def test_on_definition_returns_none_for_non_labels() -> None:
    assert (
        lsp.on_definition(
            _FakeLanguageServer('main:\n    write 8\n'),
            types.DefinitionParams(
                text_document=types.TextDocumentIdentifier(uri='u'),
                position=types.Position(line=1, character=9),
            ),
        )
        is None
    )


def test_did_change_and_did_save_republish() -> None:
    ls = _FakeLanguageServer(PROGRAM)
    lsp.did_change(
        ls,
        types.DidChangeTextDocumentParams(
            text_document=types.VersionedTextDocumentIdentifier(uri='file:///t.bsasm', version=2),
            content_changes=[types.TextDocumentContentChangeWholeDocument(text=PROGRAM)],
        ),
    )
    assert ls.published[-1].diagnostics == []

    ls.workspace.document.source = 'jmp nowhere\n'
    lsp.did_change(
        ls,
        types.DidChangeTextDocumentParams(
            text_document=types.VersionedTextDocumentIdentifier(uri='file:///t.bsasm', version=3),
            content_changes=[types.TextDocumentContentChangeWholeDocument(text='jmp nowhere\n')],
        ),
    )
    assert ls.published[-1].diagnostics

    ls.workspace.document.source = PROGRAM
    lsp.did_save(ls, types.DidSaveTextDocumentParams(text_document=types.TextDocumentIdentifier(uri='file:///t.bsasm')))
    assert ls.published[-1].diagnostics == []


def test_semantic_tokens_full_returns_delta_encoded_data() -> None:
    result = lsp.semantic_tokens_full(
        _FakeLanguageServer(PROGRAM),
        types.SemanticTokensParams(text_document=types.TextDocumentIdentifier(uri='u')),
    )
    assert result.data  # LSP wire format: delta-encoded [line, char, length, type, modifiers]


def test_document_symbols_lists_labels() -> None:
    result = lsp.document_symbols(
        _FakeLanguageServer(PROGRAM),
        types.DocumentSymbolParams(text_document=types.TextDocumentIdentifier(uri='u')),
    )
    assert [
        (s.name, s.location.range.start.line, s.location.range.start.character, s.location.range.end.character)
        for s in result
    ] == [('main', 1, 0, 4)]


def test_on_hover_returns_docs_for_keywords() -> None:
    token = next(t for t in parse_document(PROGRAM).tokens if lsp._HOVER_DOCS.get(t.type))
    hover = lsp.on_hover(
        _FakeLanguageServer(PROGRAM),
        types.HoverParams(
            text_document=types.TextDocumentIdentifier(uri='u'),
            position=types.Position(line=token.line - 1, character=token.column),
        ),
    )
    assert hover is not None
    assert isinstance(hover.contents, types.MarkupContent)
    assert hover.contents.value == lsp._HOVER_DOCS[token.type]


def test_on_definition_returns_label_location() -> None:
    result = lsp.on_definition(
        _FakeLanguageServer(PROGRAM),
        types.DefinitionParams(
            text_document=types.TextDocumentIdentifier(uri='u'),
            position=types.Position(line=3, character=14),  # the 'main' jump target
        ),
    )
    assert result is not None
    assert [(loc.range.start.line, loc.range.start.character, loc.range.end.character) for loc in result] == [(1, 0, 4)]


def test_on_references_returns_definition_and_usages() -> None:
    result = lsp.on_references(
        _FakeLanguageServer(PROGRAM),
        types.ReferenceParams(
            text_document=types.TextDocumentIdentifier(uri='u'),
            position=types.Position(line=1, character=0),
            context=types.ReferenceContext(include_declaration=True),
        ),
    )
    assert [(loc.range.start.line, loc.range.start.character) for loc in result] == [(1, 0), (3, 14)]


def test_document_formatting_replaces_the_whole_source() -> None:
    result = lsp.document_formatting(
        _FakeLanguageServer('main:\nwrite\t8'),
        types.DocumentFormattingParams(
            text_document=types.TextDocumentIdentifier(uri='u'),
            options=types.FormattingOptions(tab_size=4, insert_spaces=True),
        ),
    )
    assert len(result) == 1
    assert result[0].new_text == 'main:\n    write 8\n'
    assert result[0].range.start == types.Position(line=0, character=0)
    assert result[0].range.end == types.Position(line=1, character=7)


def test_document_formatting_range_uses_lsp_utf16_columns() -> None:
    source = '    # 🙂\n'
    result = lsp.document_formatting(
        _FakeLanguageServer(source + '\r\n'),
        types.DocumentFormattingParams(
            text_document=types.TextDocumentIdentifier(uri='u'),
            options=types.FormattingOptions(tab_size=4, insert_spaces=True),
        ),
    )
    assert len(result) == 1
    assert result[0].range.end == types.Position(line=2, character=0)


def test_document_formatting_leaves_invalid_syntax_untouched() -> None:
    server = _FakeLanguageServer('set 0 1,\n')
    result = lsp.document_formatting(
        server,
        types.DocumentFormattingParams(
            text_document=types.TextDocumentIdentifier(uri='u'),
            options=types.FormattingOptions(tab_size=4, insert_spaces=True),
        ),
    )
    assert result == []
    assert any('syntax errors' in message for message in server.logs)


def test_document_formatting_returns_no_edits_for_canonical_source() -> None:
    result = lsp.document_formatting(
        _FakeLanguageServer('main:\n    write 8\n'),
        types.DocumentFormattingParams(
            text_document=types.TextDocumentIdentifier(uri='u'),
            options=types.FormattingOptions(tab_size=4, insert_spaces=True),
        ),
    )
    assert result == []


def test_document_formatting_honors_lsp_options() -> None:
    result = lsp.document_formatting(
        _FakeLanguageServer('main:\nwrite 8'),
        types.DocumentFormattingParams(
            text_document=types.TextDocumentIdentifier(uri='u'),
            options=types.FormattingOptions(tab_size=2, insert_spaces=False),
        ),
    )
    assert len(result) == 1
    assert result[0].new_text == 'main:\n\twrite 8\n'


def test_completion_handler_returns_items() -> None:
    result = lsp.completion(
        _FakeLanguageServer(PROGRAM),
        types.CompletionParams(
            text_document=types.TextDocumentIdentifier(uri='u'),
            position=types.Position(line=1, character=8),
            context=types.CompletionContext(
                trigger_kind=types.CompletionTriggerKind.TriggerCharacter, trigger_character=' '
            ),
        ),
    )
    assert result.is_incomplete is False
    assert 'cfg' in {item.label for item in result.items}
