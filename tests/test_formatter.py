# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Tests for the canonical source formatter and its CLI."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from bsasm import assemble, encode
from bsasm.cli import main
from bsasm.errors import AssemblerErrors
from bsasm.formatting import FormatOptions, format_source
from bsasm.isa import OPTIONAL_INSTRUCTION_GROUPS


def test_format_source_canonicalizes_whitespace_and_preserves_spelling() -> None:
    source = '#Example\nCFG\tprefetch\tTRUE\nmain:\n\tSET 0 .. 7  8..15,\tWRITE 32  # output\n'
    expected = '#Example\nCFG prefetch TRUE\nmain:\n    SET 0..7 8..15, WRITE 32    # output\n'
    assert format_source(source) == expected


def test_format_source_keeps_consecutive_one_line_bundles_together() -> None:
    source = 'main:\nwrite 8\nread 32\nother:\nnop\n'
    expected = 'main:\n    write 8\n    read 32\nother:\n    nop\n'
    assert format_source(source) == expected
    assert format_source(expected) == expected


def test_format_source_indents_a_bundle_with_a_trailing_label() -> None:
    # The first statement on the line decides the layout class: a line led by
    # an instruction is instruction-block text even when a label trails it.
    assert format_source('main:\nnop done:\n') == 'main:\n    nop done:\n'
    already = 'main:\n    nop done:\ndone:\n    nop\n'
    assert format_source(already) == already


def test_format_source_keeps_a_leading_label_at_column_zero() -> None:
    already = 'main: nop\n'
    assert format_source('main:   nop\n') == already
    assert format_source(already) == already


def test_format_source_separates_a_multi_line_bundle() -> None:
    source = 'main:\nset 0 1,\nwrite 8\nread 32\n'
    expected = 'main:\n    set 0 1,\n    write 8\n\n    read 32\n'
    assert format_source(source) == expected
    assert format_source(expected) == expected


def test_format_source_preserves_author_blank_lines_between_bundles() -> None:
    source = 'main:\nwrite 8\n\n\n\nread 32\nnop\n'
    expected = 'main:\n    write 8\n\n    read 32\n    nop\n'
    assert format_source(source) == expected


def test_format_source_does_not_separate_a_comma_continuation() -> None:
    source = 'main:\nset 0 1,\n\n# inside continuation\nwrite 8\nread 32\n'
    expected = 'main:\n    set 0 1,\n\n# inside continuation\n    write 8\n\n    read 32\n'
    assert format_source(source) == expected


def test_bundle_trailing_comment_continuation_stays_before_separator() -> None:
    source = (
        'main:\n'
        '    write 8                     # first explanation\n'
        '                                # continued explanation\n'
        '    read 8\n'
    )
    expected = (
        'main:\n'
        '    write 8                     # first explanation\n'
        '                                # continued explanation\n'
        '\n'
        '    read 8\n'
    )
    assert format_source(source) == expected


def test_format_source_preserves_continuation_lines_and_blank_lines() -> None:
    source = 'loop:\nset 0 1,\nset 1 2,\n\n# comment\nwrite 8\n'
    expected = 'loop:\n    set 0 1,\n    set 1 2,\n\n# comment\n    write 8\n'
    # The blank line is consumed by a comma continuation, and the final
    # write is part of the same bundle.
    assert format_source(source) == expected
    assert format_source(expected) == expected


def test_format_source_keeps_aligned_comment_continuations() -> None:
    source = (
        'cfg eof_on downstream\n'
        'cfg trailing_bytes 8            #If we have an EOF on the input, we still\n'
        '                                #need to process the 64 bits in M0/M1\n'
        'cfg prefetch true                #We expect M0/M1 to be filled\n'
    )
    expected = (
        'cfg eof_on downstream\n'
        'cfg trailing_bytes 8            #If we have an EOF on the input, we still\n'
        '                                #need to process the 64 bits in M0/M1\n'
        'cfg prefetch true               #We expect M0/M1 to be filled\n'
    )
    assert format_source(source) == expected


def test_comment_only_indentation_has_three_canonical_levels() -> None:
    source = (
        '  # still instruction-block commentary\n'
        '    set 0 1,  # inline commentary\n'
        '    write 8\n'
        'label:  # label commentary\n'
        '                    # continuation aligned to a trailing comment\n'
        '# top-level commentary\n'
    )
    expected = (
        '    # still instruction-block commentary\n'
        '    set 0 1,                    # inline commentary\n'
        '    write 8\n'
        '\n'
        'label:                          # label commentary\n'
        '                                # continuation aligned to a trailing comment\n'
        '# top-level commentary\n'
    )
    assert format_source(source) == expected


def test_format_source_indents_comments_that_introduce_instructions() -> None:
    source = (
        'cfg trailing_bytes 32\n'
        '\n'
        '# WS2812 symbol definition in RMT data format\n'
        'lut 0x80030009   # Zero\n'
        '\n'
        '# Output the WS2812 reset symbol first\n'
        '# The reset code is saved in LUT index 2 (0b10)\n'
        'set 17 H, set 16 L\n'
        'set 31..0 L31..L0, write 32\n'
        '\n'
        'byteLoop:\n'
        '    nop\n'
    )
    expected = (
        'cfg trailing_bytes 32\n'
        '\n'
        '# WS2812 symbol definition in RMT data format\n'
        'lut 0x80030009                  # Zero\n'
        '\n'
        '    # Output the WS2812 reset symbol first\n'
        '    # The reset code is saved in LUT index 2 (0b10)\n'
        '    set 17 H, set 16 L\n'
        '    set 31..0 L31..L0, write 32\n'
        '\n'
        'byteLoop:\n'
        '    nop\n'
    )
    assert format_source(source) == expected
    assert format_source(expected) == expected


def test_format_source_keeps_column_zero_comments_before_meta_statements_and_labels() -> None:
    source = (
        '# header\n'
        '\n'
        'cfg trailing_bytes 0\n'
        '\n'
        '# before label\n'
        'byteLoop:\n'
        '    nop\n'
    )  # fmt: skip
    assert format_source(source) == source


def test_comment_leading_an_instruction_uses_configured_indent() -> None:
    assert format_source('# note\nwrite 8\n', FormatOptions(indent_width=2)) == '  # note\n  write 8\n'


def test_formatter_is_safe_on_syntax_errors() -> None:
    with pytest.raises(AssemblerErrors):
        format_source('set 0 1,\n')


def test_formatter_normalizes_crlf_and_final_newline() -> None:
    assert format_source('cfg eof_on downstream\r\nwrite 8') == 'cfg eof_on downstream\n    write 8\n'


def test_formatter_allows_semantic_errors() -> None:
    assert format_source('jmp  nowhere') == '    jmp nowhere\n'


def test_formatter_normalizes_outer_blank_lines() -> None:
    assert format_source('\n\nwrite 8\n\n\n') == '    write 8\n'
    assert format_source('') == ''


def test_format_options_control_indent_and_comment_column() -> None:
    source = 'main:\nwrite 8 # note\n'
    assert format_source(source, FormatOptions(indent_width=2)) == 'main:\n  write 8       # note\n'
    assert format_source(source, FormatOptions(comment_column=20)) == 'main:\n    write 8         # note\n'
    assert format_source(source, FormatOptions(use_tabs=True)) == 'main:\n\twrite 8                     # note\n'
    with pytest.raises(ValueError):
        FormatOptions(indent_width=0)


CORPUS = Path(__file__).resolve().parent / 'testcases'


@pytest.mark.parametrize('path', sorted(CORPUS.glob('*.bsasm')), ids=lambda path: path.stem)
def test_formatting_golden_corpus_is_idempotent_and_semantics_preserving(path: Path) -> None:
    source = path.read_text(encoding='utf-8')
    formatted = format_source(source)

    assert format_source(formatted) == formatted
    assert encode(assemble(source, OPTIONAL_INSTRUCTION_GROUPS)) == encode(
        assemble(formatted, OPTIONAL_INSTRUCTION_GROUPS)
    )


def test_cli_formats_file_in_place(tmp_path: Path) -> None:
    source = tmp_path / 'input.bsasm'
    source.write_text('main:\nwrite\t8', encoding='utf-8')

    result = CliRunner().invoke(main, ['format', str(source)])

    assert result.exit_code == 0, result.output
    assert source.read_text(encoding='utf-8') == 'main:\n    write 8\n'


def test_cli_check_reports_changes_without_writing(tmp_path: Path) -> None:
    source = tmp_path / 'input.bsasm'
    original = 'write\t8\n'
    source.write_text(original, encoding='utf-8')

    result = CliRunner().invoke(main, ['format', '--check', str(source)])

    assert result.exit_code == 1
    assert 'Would reformat' in result.output
    assert source.read_text(encoding='utf-8') == original


def test_cli_check_accepts_already_formatted_file(tmp_path: Path) -> None:
    source = tmp_path / 'input.bsasm'
    original = '    write 8\n'
    source.write_text(original, encoding='utf-8')

    result = CliRunner().invoke(main, ['format', '--check', str(source)])

    assert result.exit_code == 0
    assert 'All 1 file(s) already formatted' in result.output
    assert source.read_text(encoding='utf-8') == original


def test_cli_check_reports_only_files_that_would_change(tmp_path: Path) -> None:
    changed = tmp_path / 'changed.bsasm'
    unchanged = tmp_path / 'unchanged.bsasm'
    changed.write_text('write\t8\n', encoding='utf-8')
    unchanged.write_text('    read 8\n', encoding='utf-8')

    result = CliRunner().invoke(main, ['format', '--check', str(changed), str(unchanged)])

    assert result.exit_code == 1
    assert f'Would reformat {changed}' in result.output
    assert f'Would reformat {unchanged}' not in result.output
    assert '1 file(s) would be reformatted' in result.output
    assert changed.read_text(encoding='utf-8') == 'write\t8\n'


def test_cli_diff_does_not_write(tmp_path: Path) -> None:
    source = tmp_path / 'input.bsasm'
    original = 'write\t8\n'
    source.write_text(original, encoding='utf-8')

    result = CliRunner().invoke(main, ['format', '--diff', str(source)])

    assert result.exit_code == 0, result.output
    assert '--- ' in result.output and '+++ ' in result.output
    assert '-write' in result.output
    assert '+    write 8' in result.output
    assert source.read_text(encoding='utf-8') == original


def test_cli_check_and_diff_combined(tmp_path: Path) -> None:
    source = tmp_path / 'input.bsasm'
    original = 'write\t8\n'
    source.write_text(original, encoding='utf-8')

    result = CliRunner().invoke(main, ['format', '--check', '--diff', str(source)])

    assert result.exit_code == 1
    assert 'Would reformat' in result.output
    assert '-write' in result.output
    assert '+    write 8' in result.output
    assert source.read_text(encoding='utf-8') == original


def test_cli_diff_is_colored_only_when_color_is_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / 'input.bsasm'
    source.write_text('write\t8\n', encoding='utf-8')

    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('FORCE_COLOR', '1')
    colored = CliRunner().invoke(main, ['format', '--diff', str(source)])
    assert '\x1b[' in colored.output
    assert '-write' in colored.output  # ANSI wraps the text, it does not replace it

    monkeypatch.setenv('NO_COLOR', '1')
    plain = CliRunner().invoke(main, ['format', '--diff', str(source)])
    assert '\x1b[' not in plain.output


def test_cli_reports_in_place_summary(tmp_path: Path) -> None:
    source = tmp_path / 'input.bsasm'
    source.write_text('write\t8\n', encoding='utf-8')

    result = CliRunner().invoke(main, ['format', str(source)])

    assert result.exit_code == 0, result.output
    assert '1 file(s) reformatted' in result.output


def test_cli_format_options_reach_the_formatter(tmp_path: Path) -> None:
    source = tmp_path / 'input.bsasm'
    source.write_text('main:\nwrite 8 # note\n', encoding='utf-8')

    result = CliRunner().invoke(main, ['format', '--indent-width', '2', str(source)])

    assert result.exit_code == 0, result.output
    assert source.read_text(encoding='utf-8') == 'main:\n  write 8       # note\n'


def test_cli_formats_stdin_to_stdout() -> None:
    result = CliRunner().invoke(main, ['format', '-'], input='write\t8')

    assert result.exit_code == 0, result.output
    assert result.output == '    write 8\n'


def test_cli_rejects_stdin_mixed_with_files(tmp_path: Path) -> None:
    source = tmp_path / 'input.bsasm'
    source.write_text('write 8\n', encoding='utf-8')

    result = CliRunner().invoke(main, ['format', '-', str(source)], input='read 8\n')

    assert result.exit_code == 2
    assert 'standard input cannot be combined' in result.output


def test_cli_supports_stdin() -> None:
    result = CliRunner().invoke(main, ['format', '-'], input='write\t8\n')
    assert result.exit_code == 0, result.output
    assert result.output == '    write 8\n'
