# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Canonical formatting for BitScrambler assembly source.

The formatter works on the ANTLR token stream rather than the semantic
model: original keyword, label, number and source-bit spellings survive,
comments are retained, and syntactically invalid input is rejected before
any edit is produced.
"""

from collections import defaultdict
from dataclasses import dataclass

from antlr4 import Token

from bsasm.errors import AssemblerErrors
from bsasm.generated.BitScramblerLexer import BitScramblerLexer as Lexer
from bsasm.model import BundleStmt, CfgStmt, LabelStmt, LutStmt, Statement
from bsasm.parsing import parse


@dataclass(frozen=True, slots=True)
class FormatOptions:
    """Style knobs shared by the public API, the CLI and the language server.

    ``comment_column`` defaults to eight times the indent width, which keeps
    the historical column 32 for the default four-space indentation.
    """

    indent_width: int = 4
    comment_column: int | None = None
    use_tabs: bool = False

    def __post_init__(self) -> None:
        if self.indent_width < 1:
            raise ValueError('indent_width must be positive')
        if self.comment_column is not None and self.comment_column < 1:
            raise ValueError('comment_column must be positive')

    @property
    def indent(self) -> str:
        return '\t' if self.use_tabs else ' ' * self.indent_width

    @property
    def align_column(self) -> int:
        return 8 * self.indent_width if self.comment_column is None else self.comment_column

    def width(self, text: str) -> int:
        """Display columns of *text*, expanding tabs to ``indent_width``."""
        if not self.use_tabs:
            return len(text)
        width = 0
        for char in text:
            width = (width // self.indent_width + 1) * self.indent_width if char == '\t' else width + 1
        return width


@dataclass(frozen=True, slots=True)
class _Line:
    """One physical line, reduced to the facts the layout pass needs."""

    code: str
    comment: str | None
    comment_column: int
    statement: Statement | None
    ends_with_comma: bool

    @property
    def is_blank(self) -> bool:
        return not self.code and self.comment is None

    @property
    def is_comment_only(self) -> bool:
        return not self.code and self.comment is not None


def _build_line(tokens: tuple[Token, ...], statement: Statement | None) -> _Line:
    comment = None
    comment_column = 0
    code_tokens: list[Token] = []
    for token in tokens:
        if token.type == Lexer.COMMENT:
            comment = token.text.rstrip()
            comment_column = token.column
        else:
            # format_source already excludes NEWLINE tokens.
            code_tokens.append(token)

    code = ''
    previous_type = None
    for token in code_tokens:
        text = token.text
        if token.type == Lexer.COMMA:
            code += ','
        elif token.type == Lexer.RANGE:
            code += '..'
        elif not code or previous_type == Lexer.RANGE:
            code += text
        else:
            code += f' {text}'
        previous_type = token.type

    return _Line(
        code=code,
        comment=comment,
        comment_column=comment_column,
        statement=statement,
        ends_with_comma=bool(code_tokens) and code_tokens[-1].type == Lexer.COMMA,
    )


def _comment_continuation_end(index: int, lines: list[_Line], options: FormatOptions) -> int:
    """Last line of the trailing-comment block that follows *index*.

    Membership is decided structurally: the line must be comment-only and
    start to the right of the code indentation. A comment at column zero is
    new top-level text, not a continuation of the comment above it.
    """
    end = index
    while (
        end + 1 < len(lines) and lines[end + 1].is_comment_only and lines[end + 1].comment_column > options.indent_width
    ):
        end += 1
    return end


def _statement_spans(
    statements: tuple[Statement, ...], lines: list[_Line], options: FormatOptions
) -> list[tuple[int, int]]:
    """Physical (start, end) line span of every statement, in source order."""
    spans = []
    for index, statement in enumerate(statements):
        start = statement.location.line - 1
        next_start = statements[index + 1].location.line - 1 if index + 1 < len(statements) else len(lines)
        end = start
        cursor = start
        # A trailing comma continues the bundle across blank and comment-only
        # lines; the first following line with code closes it.
        while cursor < next_start and cursor < len(lines) and lines[cursor].ends_with_comma:
            following = cursor + 1
            while following < next_start and lines[following].code == '':
                following += 1
            if following >= next_start or following >= len(lines):
                break
            end = following
            cursor = following
        spans.append((start, _comment_continuation_end(end, lines, options)))
    return spans


def _stays_at_column_zero(statement: Statement | None) -> bool:
    """Whether a statement belongs to the top-level layout class."""
    return isinstance(statement, (CfgStmt, LutStmt, LabelStmt))


def _indented_comment_leaders(lines: list[_Line], spans: list[tuple[int, int]]) -> set[int]:
    """Column-zero comment blocks that head an indented instruction block.

    A column-zero comment is top-level text only when it heads a label,
    ``cfg`` or ``lut``, or sits inside a comma continuation; it then keeps
    that column. If the next statement is an instruction, the comment
    describes that block and follows its indent. Blank lines inside the
    block do not break the association.
    """
    in_continuation = {index for start, end in spans for index in range(start, end + 1)}
    leaders: set[int] = set()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.is_comment_only or line.comment_column != 0 or index in in_continuation:
            index += 1
            continue
        block: list[int] = []
        cursor = index
        while cursor < len(lines) and (lines[cursor].is_blank or lines[cursor].is_comment_only):
            current = lines[cursor]
            if current.is_comment_only:
                if current.comment_column != 0 or cursor in in_continuation:
                    break
                block.append(cursor)
            cursor += 1
        if cursor < len(lines):
            following = lines[cursor].statement
            if following is not None and not _stays_at_column_zero(following):
                leaders.update(block)
        index = cursor
    return leaders


def _render_line(line: _Line, options: FormatOptions, is_continuation: bool, is_leader: bool = False) -> str:
    if line.is_comment_only:
        if is_continuation:
            indent = ' ' * options.align_column
        elif line.comment_column != 0 or is_leader:
            indent = options.indent
        else:
            indent = ''
        return indent + (line.comment or '')

    # The statement that STARTS the line decides the layout class: labels and
    # meta statements live at column zero even when an instruction shares the
    # line ('main: set 0 1'); a line led by an instruction is instruction-block
    # text, even when a label trails it ('set 0 1 done:').
    if _stays_at_column_zero(line.statement):
        indent = ''
    else:
        indent = options.indent

    text = indent + line.code
    if line.comment is not None:
        text += ' ' * max(2, options.align_column - options.width(text)) + line.comment
    return text


def format_source(source: str, options: FormatOptions | None = None) -> str:
    """Return the canonical formatting of *source*.

    Formatting is syntax-safe: any syntax error raises
    :class:`~bsasm.errors.AssemblerErrors` and leaves the caller to decide how
    to report it. Semantic errors such as an unresolved label do not prevent
    whitespace formatting because the language structure is still known.

    The style is fixed per :class:`FormatOptions`: labels, ``cfg`` and ``lut``
    at column zero, instructions indented one level, and a comment block that
    introduces an instruction indented with it; comments heading a label,
    ``cfg`` or ``lut`` stay at column zero, as do notes inside a multi-line
    bundle. One space separates ordinary tokens, none surrounds ``..``, one
    follows a comma, and trailing comments align to a configurable column.
    A blank line is forced only around bundles that span several physical
    lines; otherwise the author's blank lines are kept but collapsed to at
    most one. Files end in one newline, and empty input stays empty.
    """
    options = options if options is not None else FormatOptions()
    parsed = parse(source)
    if parsed.errors:
        raise AssemblerErrors(parsed.errors)

    by_line: dict[int, list[Token]] = defaultdict(list)
    for token in parsed.tokens:
        if token.type != Lexer.NEWLINE:
            by_line[token.line - 1].append(token)

    normalized = parsed.source.replace('\r\n', '\n').replace('\r', '\n')
    count = max(len(normalized.splitlines()), max(by_line, default=-1) + 1)
    statements = tuple(parsed.statements)
    # Several statements can share a line ('a: set 0 1 trailing:'); the first
    # one - in source order, the same order the builder emits statements -
    # decides how the line is laid out.
    starts: dict[int, Statement] = {}
    for statement in statements:
        starts.setdefault(statement.location.line - 1, statement)
    lines = [_build_line(tuple(by_line.get(index, ())), starts.get(index)) for index in range(count)]

    spans = _statement_spans(statements, lines, options)
    # Only multi-line bundles force separation. Consecutive one-line bundles
    # keep the author's layout instead of being turned into a list of
    # paragraphs.
    multiline = {
        index
        for index, ((start, end), statement) in enumerate(zip(spans, statements))
        if end > start and isinstance(statement, BundleStmt)
    }
    # A label is the header of the bundle that follows it; never put a
    # separator between the two even when that bundle spans several lines.
    forced_before = {
        spans[index + 1][0]
        for index in range(len(spans) - 1)
        if (index in multiline or index + 1 in multiline) and not isinstance(statements[index], LabelStmt)
    }

    continuations: set[int] = set()
    for index, line in enumerate(lines):
        if line.comment is not None and line.code:
            continuations.update(range(index + 1, _comment_continuation_end(index, lines, options) + 1))
    leaders = _indented_comment_leaders(lines, spans)
    rendered = [
        _render_line(line, options, index in continuations, index in leaders) for index, line in enumerate(lines)
    ]

    output: list[str] = []
    index = 0
    while index < count and lines[index].is_blank:
        index += 1
    while index < count:
        if lines[index].is_blank:
            following = index
            while following < count and lines[following].is_blank:
                following += 1
            if following < count and output and output[-1] != '':
                output.append('')
            index = following
            continue
        if index in forced_before and output and output[-1] != '':
            output.append('')
        output.append(rendered[index])
        index += 1

    return '\n'.join(output).rstrip('\n') + '\n' if output else ''
