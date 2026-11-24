# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Language server for bsasm (LSP over stdio).

Reuses the very same grammar and parser as the assembler, so everything the
editor shows - diagnostics, semantic highlighting, symbol outline, jump
targets - is by construction consistent with what ``python -m bsasm``
produces. Run with ``python -m bsasm.lsp`` or the ``bsasm-lsp`` console
script. The VS Code extension in ``editors/vscode/`` launches this module.

Requires the ``lsp`` extra: ``pip install esp-bsasm[lsp]``.
"""

from dataclasses import dataclass

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from bsasm.errors import AssemblerError, AssemblerSyntaxError, Location
from bsasm.generated.BitScramblerLexer import BitScramblerLexer
from bsasm.isa import CFG_VALUES, VALID_WIDTHS
from bsasm.model import COND_MUX_SLOT, BundleStmt, IfSub, JmpSub, LabelStmt, LoopSub, LutWidth, Statement
from bsasm.parsing import parse
from bsasm.sema import analyze, source_spellings

# ---------------------------------------------------------------------------
# Document analysis: one parse of a document yields everything the server
# needs - diagnostics (collecting listener, all errors), the full token
# stream (including hidden-channel comments) for semantic highlighting, and
# the parsed statements for symbols and cross references.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DocDiagnostic:
    """One diagnostic produced by :func:`parse_document`."""

    location: Location
    message: str
    related: Location | None = None  # second site, e.g. a mux-conflict pair


@dataclass
class ParsedDocument:
    """Everything the language server derives from one document."""

    source: str
    diagnostics: list[DocDiagnostic]  # in error order
    tokens: list  # ANTLR CommonToken list, document order, hidden channel included
    statements: list[Statement]  # empty when the syntax is broken
    lut_width: LutWidth | None  # set only when the whole analysis passes


def _semantic_diagnostic(error: AssemblerError) -> DocDiagnostic:
    """Diagnostic for one semantic error found by ``analyze``."""
    if isinstance(error, AssemblerSyntaxError):
        return DocDiagnostic(error.first, error.message, error.second)
    return DocDiagnostic(Location(1, 1, ''), str(error))


def parse_document(source: str) -> ParsedDocument:
    """Parse ``source`` collecting all diagnostics and the token stream."""
    parsed = parse(source)
    diagnostics = [_semantic_diagnostic(error) for error in parsed.errors]
    lut_width = None
    if not diagnostics:
        # Syntax is clean: the same analysis the CLI and assemble() run.
        program, semantic_errors = analyze(parsed.statements)
        diagnostics.extend(_semantic_diagnostic(e) for e in semantic_errors)
        if not semantic_errors:
            lut_width = program.meta.lut_width

    return ParsedDocument(
        source=parsed.source,
        diagnostics=diagnostics,
        tokens=parsed.tokens,
        statements=parsed.statements,
        lut_width=lut_width,
    )


# ---------------------------------------------------------------------------
# Semantic tokens: the whole file is colored from the token stream (comments
# ride the hidden channel), so no separate TextMate grammar is needed and
# highlighting can never drift from the grammar.
# ---------------------------------------------------------------------------

_TOKEN_KINDS: dict[int, str] = {
    BitScramblerLexer.NUMBER: 'number',
    BitScramblerLexer.COMMENT: 'comment',
    BitScramblerLexer.LABEL: 'function',
    BitScramblerLexer.NAME: 'variable',
    BitScramblerLexer.AUX_CMP: 'variable',
    BitScramblerLexer.REL_OPERAND: 'variable',
    BitScramblerLexer.RANGE: 'operator',
}
# Separator tokens (COMMA, NEWLINE, EOF) are not colored.

_MNEMONIC_TOKENS = (
    BitScramblerLexer.CFG,
    BitScramblerLexer.LUT,
    BitScramblerLexer.SET,
    BitScramblerLexer.WRITE,
    BitScramblerLexer.READ,
    BitScramblerLexer.LOOPA,
    BitScramblerLexer.LOOPB,
    BitScramblerLexer.ADDA,
    BitScramblerLexer.ADDAH,
    BitScramblerLexer.ADDAL,
    BitScramblerLexer.ADDB,
    BitScramblerLexer.ADDBH,
    BitScramblerLexer.ADDBL,
    BitScramblerLexer.IF,
    BitScramblerLexer.IFN,
    BitScramblerLexer.LDCTDA,
    BitScramblerLexer.LDCTDAH,
    BitScramblerLexer.LDCTDAL,
    BitScramblerLexer.LDCTDB,
    BitScramblerLexer.LDCTDBH,
    BitScramblerLexer.LDCTDBL,
    BitScramblerLexer.LDCTIA,
    BitScramblerLexer.LDCTIAH,
    BitScramblerLexer.LDCTIAL,
    BitScramblerLexer.LDCTIB,
    BitScramblerLexer.LDCTIBH,
    BitScramblerLexer.LDCTIBL,
    BitScramblerLexer.ADDCTIA,
    BitScramblerLexer.ADDCTIAH,
    BitScramblerLexer.ADDCTIAL,
    BitScramblerLexer.ADDCTIB,
    BitScramblerLexer.ADDCTIBH,
    BitScramblerLexer.ADDCTIBL,
    BitScramblerLexer.JMP,
    BitScramblerLexer.NOP,
)

# cfg keys are properties of the program; cfg values enumerate their options.
_CFG_KEY_TOKENS = (
    BitScramblerLexer.K_PREFETCH,
    BitScramblerLexer.K_TRAILING_BYTES,
    BitScramblerLexer.K_EOF_ON,
    BitScramblerLexer.K_LUT_WIDTH_BITS,
    BitScramblerLexer.K_LOOP_ENDS_ON,
)
_CFG_VALUE_TOKENS = (
    BitScramblerLexer.K_UPSTREAM,
    BitScramblerLexer.K_DOWNSTREAM,
    BitScramblerLexer.K_EQUAL,
    BitScramblerLexer.K_EQUAL_OR_GREATER,
    BitScramblerLexer.K_TRUE,
    BitScramblerLexer.K_FALSE,
)
for _token in _MNEMONIC_TOKENS:
    _TOKEN_KINDS[_token] = 'macro'
for _token in _CFG_KEY_TOKENS:
    _TOKEN_KINDS[_token] = 'property'
for _token in _CFG_VALUE_TOKENS:
    _TOKEN_KINDS[_token] = 'enumMember'


# Standard LSP token types, ordered by how often they occur; every name maps
# to a default theme style in VS Code.
SEMANTIC_TOKEN_TYPES = ['macro', 'property', 'enumMember', 'variable', 'number', 'comment', 'operator', 'function']


def _semantic_kind(token) -> str | None:  # noqa: ANN001 - ANTLR token
    return _TOKEN_KINDS.get(token.type)


def semantic_tokens(source: str) -> list[tuple[int, int, int, str]]:
    """All colorable tokens of ``source`` as (line, column, length, kind).

    Line and column are 0-based, matching the LSP wire format.
    """
    doc = parse_document(source)
    result = []
    for token in doc.tokens:
        kind = _semantic_kind(token)
        if kind is None:
            continue
        result.append((token.line - 1, token.column, len(token.text), kind))
    return result


# ---------------------------------------------------------------------------
# Hover documentation: keyword-focused, derived from the same language rules
# the assembler enforces. Deliberately link-free: external URLs rot, and the
# docs live in the shipped package.
# ---------------------------------------------------------------------------

_HOVER_DOCS: dict[int, str] = {
    BitScramblerLexer.CFG: 'Per-program settings, one ``cfg <key> <value>`` pair per line.',
    BitScramblerLexer.LUT: 'Define the lookup-table contents, one ``lut`` line per row; '
    'the word width comes from ``cfg lut_width_bits``.',
    BitScramblerLexer.SET: 'Route input bits to output bits: ``set <out> <in>`` — each operand '
    'is a single bit or an ``a..b`` range.',
    BitScramblerLexer.WRITE: 'Number of bits (0/8/16/32) this instruction writes to the output '
    'FIFO. A bundle without ``write`` writes 0 bits.',
    BitScramblerLexer.READ: 'Number of bits (0/8/16/32) this instruction reads from the input '
    'FIFO. A bundle without ``read`` reads 0 bits.',
    BitScramblerLexer.IF: '``IF <source> <target>`` — jump to the target label when the selected source compares true.',
    BitScramblerLexer.IFN: '``IFN <source> <target>`` — jump to the target label when the '
    'selected source compares false.',
    BitScramblerLexer.JMP: '``jmp <target>`` — unconditional jump to the target label.',
    BitScramblerLexer.NOP: 'Placeholder bundle: one hardware instruction that does nothing.',
    BitScramblerLexer.K_PREFETCH: '``cfg prefetch true|false`` — pre-fetch the next instruction '
    'while the current one runs (default true).',
    BitScramblerLexer.K_TRAILING_BYTES: '``cfg trailing_bytes N`` (0..8191) — keep transmitting '
    'N extra bytes after the last instruction finishes.',
    BitScramblerLexer.K_EOF_ON: '``cfg eof_on upstream|downstream`` — which side signals EOF for this program.',
    BitScramblerLexer.K_LUT_WIDTH_BITS: '``cfg lut_width_bits 8|16|32`` — LUT word width; also '
    'changes which input bits feed the LUT.',
    BitScramblerLexer.K_LOOP_ENDS_ON: '``cfg loop_ends_on equal|equal_or_greater`` — when a loop '
    'terminates relative to ``end_val``.',
    BitScramblerLexer.K_UPSTREAM: '``eof_on`` value: the input (upstream) side signals EOF.',
    BitScramblerLexer.K_DOWNSTREAM: '``eof_on`` value: the output (downstream) side signals EOF.',
    BitScramblerLexer.K_EQUAL: '``loop_ends_on`` value: the loop ends when the counter equals '
    '``end_val`` (suitable for counting down).',
    BitScramblerLexer.K_EQUAL_OR_GREATER: '``loop_ends_on`` value: the loop ends when the counter '
    'is greater than or equal to ``end_val`` (hardware default).',
    BitScramblerLexer.K_TRUE: 'Boolean ``cfg`` value: true.',
    BitScramblerLexer.K_FALSE: 'Boolean ``cfg`` value: false.',
}

for _t in (BitScramblerLexer.LOOPA, BitScramblerLexer.LOOPB):
    _HOVER_DOCS[_t] = (
        '``LOOPc <end_val> <ctr_add> <target>`` — repeat the instruction bundle at the target '
        'label until counter c reaches ``end_val``, adding ``ctr_add`` (-16..15) each iteration. '
        'End condition: ``cfg loop_ends_on``.'
    )
for _t in (BitScramblerLexer.ADDA, BitScramblerLexer.ADDAH, BitScramblerLexer.ADDAL):
    _HOVER_DOCS[_t] = '``ADDc <value>`` — add the value to counter a; ``H``/``L`` variants touch '
    'only the upper/lower half, the bare form updates both halves.'
for _t in (BitScramblerLexer.ADDB, BitScramblerLexer.ADDBH, BitScramblerLexer.ADDBL):
    _HOVER_DOCS[_t] = '``ADDc <value>`` — add the value to counter b; ``H``/``L`` variants touch '
    'only the upper/lower half, the bare form updates both halves.'
for _t in (
    BitScramblerLexer.LDCTDA,
    BitScramblerLexer.LDCTDAH,
    BitScramblerLexer.LDCTDAL,
    BitScramblerLexer.LDCTDB,
    BitScramblerLexer.LDCTDBH,
    BitScramblerLexer.LDCTDBL,
):
    _HOVER_DOCS[_t] = '``LDCTDc <value>`` — load counter c with the immediate value; ``H``/``L`` '
    'variants write only the upper/lower half.'
for _t in (BitScramblerLexer.LDCTIA, BitScramblerLexer.LDCTIAH, BitScramblerLexer.LDCTIAL):
    _HOVER_DOCS[_t] = '``LDCTIc`` — load counter c from the mux output selected in this '
    'instruction; ``H``/``L`` variants write only the upper/lower half.'
for _t in (BitScramblerLexer.ADDCTIA, BitScramblerLexer.ADDCTIAH, BitScramblerLexer.ADDCTIAL):
    _HOVER_DOCS[_t] = '``ADDCTIc`` — add the mux output of this instruction to counter a; not '
    'available on every chip (the build with the chip cfg decides).'
for _t in (BitScramblerLexer.ADDCTIB, BitScramblerLexer.ADDCTIBH, BitScramblerLexer.ADDCTIBL):
    _HOVER_DOCS[_t] = '``ADDCTIc`` — add the mux output of this instruction to counter b; not '
    'available on every chip (the build with the chip cfg decides).'


def hover(source: str, line: int, character: int) -> str | None:
    """Markdown documentation for the keyword under the cursor, or None.

    ``line`` and ``character`` are 0-based, matching the LSP wire format.
    """
    doc = parse_document(source)
    token = _token_at(doc.tokens, line, character)
    if token is None:
        return None
    return _HOVER_DOCS.get(token.type)


# ---------------------------------------------------------------------------
# Symbols and cross references
# ---------------------------------------------------------------------------


def _token_at(tokens: list, line: int, character: int, *, at_end: bool = False):
    """The ANTLR token covering ``(line, character)``, both 0-based.

    When ``at_end`` is True, a cursor sitting just after a token (the usual
    LSP position after the last character of a word) still hits that token,
    unless another token starts at the same column.
    """
    ending = None
    for token in tokens:
        if token.line - 1 != line:
            continue
        start = token.column
        end = start + len(token.text)
        if start <= character < end:
            return token
        if at_end and character == end and token.text:
            ending = token
    return ending


def _label_name_at(doc: ParsedDocument, line: int, character: int) -> str:
    """Label under the cursor, resolved via the token stream and statement spans.

    Jump targets may be keyword tokens (``labelRef`` accepts every mnemonic),
    so the name comes from the statement that occupies this token, not from
    a guessed identifier charset. A mnemonic that merely shares spelling
    with a label does not match.
    """
    token = _token_at(doc.tokens, line, character, at_end=True)
    if token is None:
        return ''
    tline = token.line - 1
    tstart = token.column
    tend = tstart + len(token.text)
    for name, line_no, col, length in (
        *_label_definitions(doc.statements),
        *_label_usages(doc.statements),
    ):
        if line_no != tline:
            continue
        if not (col >= tstart and col + length <= tend):
            continue
        if tstart <= character < tend or character == tend:
            return name
    return ''


def _label_usages(statements: list) -> list[tuple[str, int, int, int]]:
    """All jump targets as (name, line, column, length), 0-based."""
    result = []
    for st in statements:
        if not isinstance(st, BundleStmt):
            continue
        for sub in st.subs:
            if isinstance(sub, LoopSub | IfSub | JmpSub):
                loc = sub.target.location
                result.append((sub.target.text.lower(), loc.line - 1, loc.column - 1, len(loc.text)))
    return result


def _label_definitions(statements: list) -> list[tuple[str, int, int, int]]:
    """All label definitions as (name, line, column, length), 0-based."""
    return [
        (st.name.lower(), st.location.line - 1, st.location.column - 1, len(st.name))
        for st in statements
        if isinstance(st, LabelStmt)
    ]


def symbols(source: str) -> list[dict]:
    """Document symbols: one entry per label (the program's outline)."""
    doc = parse_document(source)
    return [
        {'name': name, 'kind': 'function', 'location': (line, column, length)}
        for name, line, column, length in _label_definitions(doc.statements)
    ]


def definition(source: str, line: int, character: int) -> tuple[int, int, int] | None:
    """Go-to-definition: resolve the label under (or referenced from) the cursor."""
    doc = parse_document(source)
    word = _label_name_at(doc, line, character)
    if not word:
        return None
    for name, line_no, col, length in _label_definitions(doc.statements):
        if name == word:
            return (line_no, col, length)
    return None


def references(
    source: str,
    line: int,
    character: int,
    include_declaration: bool = True,
) -> list[tuple[int, int, int]]:
    """Find references: the label definition and all jump targets to it.

    ``include_declaration=False`` drops the definition, honoring the LSP
    ``ReferenceContext`` flag.
    """
    doc = parse_document(source)
    word = _label_name_at(doc, line, character)
    if not word:
        return []
    definitions = [
        (line_no, col, length) for name, line_no, col, length in _label_definitions(doc.statements) if name == word
    ]
    usages = [(line_no, col, length) for name, line_no, col, length in _label_usages(doc.statements) if name == word]
    # Definition first, usages after.
    return definitions + usages if include_declaration else usages


# ---------------------------------------------------------------------------
# Completions
# ---------------------------------------------------------------------------


def _keyword_spelling(token_type: int) -> str:
    """Lexer token name as the keyword users type (``K_EOF_ON`` -> ``eof_on``)."""
    name = BitScramblerLexer.symbolicNames[token_type]
    if name.startswith('K_'):
        return name.removeprefix('K_').lower()
    return name.lower()


def _mnemonic_items() -> list[dict]:
    return [{'label': _keyword_spelling(t), 'kind': 'keyword', 'detail': 'instruction'} for t in _MNEMONIC_TOKENS]


def _cfg_key_items() -> list[dict]:
    return [{'label': _keyword_spelling(t), 'kind': 'keyword', 'detail': 'cfg key'} for t in _CFG_KEY_TOKENS]


def _source_items(lut_width: LutWidth | None) -> list[dict]:
    """Every mux-source spelling, including ``+a`` where it is legal.

    Source names come from :func:`bsasm.sema.source_spellings`, so the list
    cannot drift from what :func:`bsasm.sema._parse_input` accepts. LUT bits
    depend on ``cfg lut_width_bits``: when the document parses, ``lut_width``
    filters them exactly; otherwise all 32 are offered without relative forms.
    """
    items = []
    for src in source_spellings():
        if src.lut_index is not None:
            if lut_width is not None and src.lut_index >= int(lut_width):
                continue  # outside the cfg lut_width_bits range
            # Relative LUT bits need a known width to be meaningful.
            relative_ok = src.allows_relative and lut_width is not None
        else:
            relative_ok = src.allows_relative
        items.append({'label': src.name, 'kind': 'variable', 'detail': src.detail})
        if relative_ok:
            items.append({'label': f'{src.name}+a', 'kind': 'variable', 'detail': f'{src.detail}, relative'})
    return items


_MNEMONIC_SPELLINGS = frozenset(_keyword_spelling(t) for t in _MNEMONIC_TOKENS)


def _completion_context(doc: ParsedDocument, line: int, character: int) -> tuple[str, str | None]:
    """Classify what belongs at the cursor as ``(category, cfg_key)``.

    Only the current line is examined, and only the part before the cursor:
    completion must work while the line is still being typed (and may be
    syntactically broken). A comma starts a fresh sub-instruction, and a
    leading label definition is ignored.
    """
    lines = doc.source.split('\n')
    if not 0 <= line < len(lines):
        return 'none', None
    text = lines[line][:character]
    if '#' in text:  # inside a comment
        return 'none', None

    segment = text.rsplit(',', 1)[-1]
    trailing_space = bool(segment) and segment[-1].isspace()
    words = segment.split()
    while words and words[0].endswith(':'):  # label definition before content
        words = words[1:]
    if not words:
        return 'statement', None

    first = words[0].lower()
    count = len(words)
    if first not in _MNEMONIC_SPELLINGS:
        # An unrecognised first word is a mnemonic being typed.
        return ('statement', None) if count == 1 else ('none', None)
    if count == 1 and not trailing_space:
        return 'statement', None  # still typing the mnemonic itself
    if first == 'cfg':
        # 'cfg ' -> keys; a partial key ('cfg pref') -> keys; a complete key
        # ('cfg prefetch', with or without the following space) -> its values.
        if count == 1:
            return 'cfg_key', None
        key = words[1].lower()
        if count == 2 and not trailing_space:
            return ('cfg_value', key) if key in CFG_VALUES else ('cfg_key', None)
        return ('cfg_value', key) if key in CFG_VALUES else ('none', None)
    if first in ('write', 'read'):
        return 'width', None
    if first == 'jmp':
        return 'label', None
    if first == 'set':
        # outSpec is an output bit number (0..31); inSpec is a mux source.
        if count == 1 or (count == 2 and not trailing_space):
            return 'output', None
        return 'source', None
    if first in ('if', 'ifn'):
        # condSource is a mux source; the second operand is a label.
        if count == 1 or (count == 2 and not trailing_space):
            return 'source', None
        return 'label', None
    if first in ('loopa', 'loopb'):
        return ('label', None) if count >= 3 else ('none', None)
    # lut / add / ldctd / ldcti / addcti / nop take numbers or no operand.
    return 'none', None


def completions_at(doc: ParsedDocument, line: int, character: int) -> list[dict]:
    """Completion items appropriate for the cursor position in ``doc``.

    Never offers every category at once: after ``cfg`` only cfg keys appear,
    after a cfg key only its values, at a jump target only labels, and so on.
    Source lists still honour the parsed ``cfg lut_width_bits``.
    """
    category, key = _completion_context(doc, line, character)
    if category == 'statement':
        return _mnemonic_items()
    if category == 'cfg_key':
        return _cfg_key_items()
    if category == 'cfg_value':
        return [{'label': value, 'kind': 'value', 'detail': 'cfg value'} for value in CFG_VALUES.get(key or '', ())]
    if category == 'source':
        return _source_items(doc.lut_width)
    if category == 'output':
        # Output bits occupy the mux slots below the IF/IFN condition slot.
        return [{'label': str(bit), 'kind': 'value', 'detail': 'output bit'} for bit in range(COND_MUX_SLOT)]
    if category == 'width':
        return [{'label': str(int(width)), 'kind': 'value', 'detail': 'bit width'} for width in VALID_WIDTHS]
    if category == 'label':
        names = sorted({token.text[:-1] for token in doc.tokens if token.type == BitScramblerLexer.LABEL})
        return [{'label': name, 'kind': 'function', 'detail': 'label'} for name in names]
    return []


# ---------------------------------------------------------------------------
# The LSP server itself. The pure functions above carry all the logic and
# are unit-tested directly; these handlers are thin LSP adapters.
# ---------------------------------------------------------------------------

server = LanguageServer(name='bsasm-language-server', version='0.1.0')

_DIAGNOSTIC_SOURCE = 'bsasm'


def _location_range(location: Location) -> types.Range:
    start = types.Position(line=max(0, location.line - 1), character=max(0, location.column - 1))
    end = types.Position(
        line=start.line,
        character=start.character + max(1, len(location.text)),
    )
    return types.Range(start=start, end=end)


def _publish_diagnostics(ls: LanguageServer, uri: str, source: str) -> None:
    diagnostics = []
    for item in parse_document(source).diagnostics:
        related = None
        if item.related is not None:
            related = [
                types.DiagnosticRelatedInformation(
                    location=types.Location(uri=uri, range=_location_range(item.related)),
                    message=item.message,
                )
            ]
        diagnostics.append(
            types.Diagnostic(
                range=_location_range(item.location),
                message=item.message,
                severity=types.DiagnosticSeverity.Error,
                source=_DIAGNOSTIC_SOURCE,
                related_information=related,
            )
        )
    ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics))


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: LanguageServer, params: types.DidOpenTextDocumentParams) -> None:
    _publish_diagnostics(ls, params.text_document.uri, params.text_document.text)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: LanguageServer, params: types.DidChangeTextDocumentParams) -> None:
    document = ls.workspace.get_text_document(params.text_document.uri)
    _publish_diagnostics(ls, params.text_document.uri, document.source)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: LanguageServer, params: types.DidSaveTextDocumentParams) -> None:
    # DidSaveTextDocumentParams.text_document is a TextDocumentIdentifier (uri
    # only) per the LSP spec - unlike didOpen there is no full TextDocumentItem.
    # The workspace copy already reflects the latest didChange content.
    document = ls.workspace.get_text_document(params.text_document.uri)
    _publish_diagnostics(ls, params.text_document.uri, document.source)


@server.feature(
    types.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
    types.SemanticTokensLegend(token_types=SEMANTIC_TOKEN_TYPES, token_modifiers=[]),
)
def semantic_tokens_full(ls: LanguageServer, params: types.SemanticTokensParams) -> types.SemanticTokens:
    document = ls.workspace.get_text_document(params.text_document.uri)
    spans = semantic_tokens(document.source)
    kind_index = {kind: i for i, kind in enumerate(SEMANTIC_TOKEN_TYPES)}

    # LSP wire format: delta-encoded [line, char, length, type, modifiers].
    data: list[int] = []
    prev_line, prev_col = 0, 0
    for line, column, length, kind in sorted(spans):
        data.extend(
            [
                line - prev_line,
                column - prev_col if line == prev_line else column,
                length,
                kind_index[kind],
                0,
            ]
        )
        prev_line, prev_col = line, column
    return types.SemanticTokens(data=data)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def on_hover(ls: LanguageServer, params: types.HoverParams) -> types.Hover | None:
    document = ls.workspace.get_text_document(params.text_document.uri)
    text = hover(document.source, params.position.line, params.position.character)
    if text is None:
        return None
    return types.Hover(contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value=text))


@server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbols(ls: LanguageServer, params: types.DocumentSymbolParams) -> list[types.SymbolInformation]:
    document = ls.workspace.get_text_document(params.text_document.uri)
    result = []
    for entry in symbols(document.source):
        line, column, length = entry['location']
        result.append(
            types.SymbolInformation(
                name=entry['name'],
                kind=types.SymbolKind.Function,
                location=types.Location(
                    uri=params.text_document.uri,
                    range=types.Range(
                        start=types.Position(line=line, character=column),
                        end=types.Position(line=line, character=column + length),
                    ),
                ),
            )
        )
    return result


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def on_definition(ls: LanguageServer, params: types.DefinitionParams) -> list[types.Location] | None:
    document = ls.workspace.get_text_document(params.text_document.uri)
    hit = definition(document.source, params.position.line, params.position.character)
    if hit is None:
        return None
    line, column, length = hit
    return [
        types.Location(
            uri=params.text_document.uri,
            range=types.Range(
                start=types.Position(line=line, character=column),
                end=types.Position(line=line, character=column + length),
            ),
        )
    ]


@server.feature(types.TEXT_DOCUMENT_REFERENCES)
def on_references(ls: LanguageServer, params: types.ReferenceParams) -> list[types.Location]:
    document = ls.workspace.get_text_document(params.text_document.uri)
    result = []
    for line, column, length in references(
        document.source,
        params.position.line,
        params.position.character,
        include_declaration=params.context.include_declaration,
    ):
        result.append(
            types.Location(
                uri=params.text_document.uri,
                range=types.Range(
                    start=types.Position(line=line, character=column),
                    end=types.Position(line=line, character=column + length),
                ),
            )
        )
    return result


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION,
    types.CompletionOptions(trigger_characters=[' ']),
)
def completion(ls: LanguageServer, params: types.CompletionParams) -> types.CompletionList:
    kind_map = {
        'keyword': types.CompletionItemKind.Keyword,
        'value': types.CompletionItemKind.EnumMember,
        'variable': types.CompletionItemKind.Variable,
        'function': types.CompletionItemKind.Function,
    }
    document = ls.workspace.get_text_document(params.text_document.uri)
    doc = parse_document(document.source)
    items = completions_at(doc, params.position.line, params.position.character)
    return types.CompletionList(
        is_incomplete=False,
        items=[
            types.CompletionItem(label=item['label'], kind=kind_map[item['kind']], detail=item['detail'])
            for item in items
        ],
    )


def main() -> None:
    server.start_io()


if __name__ == '__main__':
    main()
