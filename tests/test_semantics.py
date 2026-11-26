# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Operand-parsing cases the binary corpus does not cover.

``set`` endpoints are NUMBER tokens (hex/binary/sign included). Spellings
that mean the same integer must assemble to the same binary; values outside
0..31 (outputs) or 0..63 (numeric inputs) stay clean errors, never a traceback.
"""

from pathlib import Path

import pytest

import bsasm
from bsasm.errors import AssemblerError, AssemblerErrors
from bsasm.lsp import parse_document

TESTCASES_DIR = Path(__file__).resolve().parent / 'testcases'


CASE_VARIANT_PROGRAMS = [
    'CFG PREFETCH TRUE\nCFG LUT_WIDTH_BITS 8\nmain:\n    SET 0 O0, WRITE 8\n',
    'Cfg Prefetch True\nCfg Lut_Width_Bits 8\nMaIn:\n    Set 0 o0, WrItE 8\n',
    'cfg eof_on UPSTREAM\nmain:\n    LOOPA 10 1 main\n    AdDaH 5\nsecond:\n    JMP main\n',
]


@pytest.mark.parametrize('program', CASE_VARIANT_PROGRAMS)
def test_keyword_casing_does_not_change_output(program: str, run_bsasm, tmp_path: Path) -> None:
    def assemble(text: str, name: str) -> bytes:
        source = tmp_path / f'{name}.bsasm'
        source.write_text(text, encoding='utf-8')
        outfile = tmp_path / f'{name}.bsbin'
        run = run_bsasm([str(source), str(outfile)], cwd=tmp_path)
        assert run.returncode == 0, run.stdout + run.stderr
        return outfile.read_bytes()

    assert assemble(program, 'variant') == assemble(program.lower(), 'lower')


EQUIVALENT_SET_LINES = [
    ('set 0x10 5', 'set 16 5'),
    ('set 0b10 5', 'set 2 5'),
    ('set 0o20 5', 'set 16 5'),
    ('set +1 0', 'set 1 0'),
    ('set 08 5', 'set 8 5'),
    ('set 0..0x0f 0', 'set 0..15 0'),
    ('set 0 0x10', 'set 0 16'),
    ('set 0 0b100000', 'set 0 32'),
    ('set 0 0x10+a', 'set 0 16+a'),
]


@pytest.mark.parametrize('spelling,decimal', EQUIVALENT_SET_LINES)
def test_set_number_spellings_match_decimal(spelling: str, decimal: str, run_bsasm, tmp_path: Path) -> None:
    def assemble(line: str, name: str) -> bytes:
        source = tmp_path / f'{name}.bsasm'
        source.write_text(f'main:\n    {line}, write 8\n', encoding='utf-8')
        outfile = tmp_path / f'{name}.bsbin'
        run = run_bsasm([str(source), str(outfile)], cwd=tmp_path)
        assert run.returncode == 0, run.stdout + run.stderr
        return outfile.read_bytes()

    assert assemble(spelling, 'alt') == assemble(decimal, 'dec')


def test_signed_hex_immediate_matches_decimal(run_bsasm, tmp_path: Path) -> None:
    def assemble(imm: str, name: str) -> bytes:
        source = tmp_path / f'{name}.bsasm'
        source.write_text(f'main:\n    adda {imm}, write 8\n', encoding='utf-8')
        outfile = tmp_path / f'{name}.bsbin'
        run = run_bsasm([str(source), str(outfile)], cwd=tmp_path)
        assert run.returncode == 0, run.stdout + run.stderr
        return outfile.read_bytes()

    assert assemble('-0x10', 'hex') == assemble('-16', 'dec')


@pytest.mark.parametrize('operand', ['32', '-1', '0x20'])
def test_set_rejects_out_of_range_outputs(operand: str, run_bsasm, tmp_path: Path) -> None:
    source = tmp_path / 'prog.bsasm'
    source.write_text(f'main:\n    set {operand} 5, write 8\n', encoding='utf-8')
    run = run_bsasm([str(source)], cwd=tmp_path)
    combined = run.stdout + run.stderr
    assert run.returncode == 2
    assert 'Traceback' not in combined
    assert 'out of range' in combined


def test_mux_conflict_fails_at_assemble_time(run_bsasm, tmp_path: Path) -> None:
    source = tmp_path / 'prog.bsasm'
    source.write_text('main:\n    set 0 a0, set 1 32, write 8\n', encoding='utf-8')
    run = run_bsasm([str(source)], cwd=tmp_path)
    assert run.returncode == 2
    combined = run.stdout + run.stderr
    assert 'Traceback' not in combined
    assert 'Cannot have both counters/LUT' in combined


def test_relative_and_non_relative_sources_conflict() -> None:
    assert 'Cannot have these inputs as both relative and not-relative' in _error_text('set 0 0+a, set 1 0')


def test_too_many_instructions_is_a_clean_cli_error(run_bsasm, tmp_path: Path) -> None:
    source = tmp_path / 'prog.bsasm'
    source.write_text('nop\n' * 9, encoding='utf-8')
    run = run_bsasm([str(source)], cwd=tmp_path)
    combined = run.stdout + run.stderr
    assert run.returncode == 2
    assert 'Traceback' not in combined
    assert 'more than 8 instructions' in combined


def test_public_api_reports_all_errors() -> None:
    with pytest.raises(AssemblerErrors) as ctx:
        bsasm.assemble('cfg prefetch 2\ncfg lut_width_bits 7\n')
    assert len(ctx.value.errors) == 2
    assert all(isinstance(error, AssemblerError) for error in ctx.value.errors)
    assert 'prefetch' in str(ctx.value)
    assert 'lut_width_bits' in str(ctx.value)


def test_cli_reports_all_semantic_errors(run_bsasm, tmp_path: Path) -> None:
    # Same set of errors as the LSP reports (test_lsp.py); the CLI prints
    # each diagnostic on its own line.
    source = tmp_path / 'prog.bsasm'
    source.write_text('cfg prefetch 2\ncfg lut_width_bits 7\n', encoding='utf-8')
    run = run_bsasm([str(source)], cwd=tmp_path)
    combined = run.stdout + run.stderr
    assert run.returncode == 2
    assert combined.count('not an allowed value') == 2
    assert 'prefetch' in combined
    assert 'lut_width_bits' in combined
    assert 'Traceback' not in combined


def test_cli_and_lsp_report_the_same_errors(run_bsasm, tmp_path: Path) -> None:
    src = 'cfg prefetch 2\ncfg trailing_bytes 99999\nmain:\n    write 12\n'
    source = tmp_path / 'prog.bsasm'
    source.write_text(src, encoding='utf-8')
    run = run_bsasm([str(source)], cwd=tmp_path)
    cli_lines = [line for line in (run.stdout + run.stderr).splitlines() if line.startswith('ERROR: ')]
    lsp_messages = [d.message for d in parse_document(src).diagnostics]
    assert run.returncode == 2
    assert len(cli_lines) == len(lsp_messages) == 3
    for message in lsp_messages:
        assert any(message in line for line in cli_lines)


def test_cli_reports_packed_lut_word_count(run_bsasm, tmp_path: Path) -> None:
    # lut8.bsasm holds 5 values of 8 bits -> 2 32-bit words in the binary.
    # An explicit outfile keeps the written binary out of tests/testcases/.
    source = TESTCASES_DIR / 'lut8.bsasm'
    outfile = tmp_path / 'lut8.bsbin'
    run = run_bsasm([str(source), str(outfile)], cwd=tmp_path)
    assert run.returncode == 0
    assert outfile.exists()
    assert '2 32-bit words of LUT' in run.stdout + run.stderr


def test_input_range_spans_the_0_31_and_32_63_boundary() -> None:
    # A range may span the 0..31 / 32..63 boundary when the multiplexed half
    # is a plain reg_mem1 bit (no ctrsel/lutsel requirement).
    bsasm.encode(bsasm.assemble('set 0..31 32\n'))


def test_invalid_input_range_messages() -> None:
    assert 'l0..o0 is not a valid range of input selections' in _error_text('set 0 l0..o0')
    assert 'Try splitting up the range.' in _error_text('set 0 l0..o0')
    assert 'Did you forget an L at the end of the range?' in _error_text('set 0 l0..15')


def test_backwards_input_range() -> None:
    bsasm.encode(bsasm.assemble('set 0..15 a15..a0\n'))


def test_jump_target_past_end_reports_program_size() -> None:
    assert "jump target 'end' points past the end of the program" in _error_text('jmp end\nnop\nend:\n')


# ---------------------------------------------------------------------------
# Semantic diagnostics the corpus does not reach
# ---------------------------------------------------------------------------


def _error_text(source: str) -> str:
    with pytest.raises(AssemblerError) as ctx:
        bsasm.assemble(source)
    return str(ctx.value)


def test_cfg_loop_ends_on_rejects_non_keyword_values() -> None:
    # The grammar accepts only the two value keywords; anything else is a
    # syntax error, never a silently-defaulted header byte.
    assert 'unexpected' in _error_text('cfg loop_ends_on bogus')
    assert 'expected one of' in _error_text('cfg loop_ends_on 2')


def test_lut_input_out_of_configured_width() -> None:
    assert 'LUT is configured to be only 8 bits wide' in _error_text('cfg lut_width_bits 8\nset 0 l20')
    assert 'LUT is configured to be only 16 bits wide' in _error_text('cfg lut_width_bits 16\nset 0 l20')
    # The default 32-bit LUT admits l20.
    bsasm.encode(bsasm.assemble('set 0 l20\n'))


def test_oversized_lut_is_a_clean_error() -> None:
    # The header's LUT length is a 16-bit word count; exceeding it used to
    # escape as a raw struct.error from the encoder.
    source = 'cfg lut_width_bits 32\nlut ' + ','.join(['0'] * 65536) + '\n'
    assert 'more than 65535 LUT values' in _error_text(source)


def test_parsed_statements_contain_only_real_statements() -> None:
    parsed = bsasm.parse('main:\nwrite 8\ncfg prefetch true\n')
    assert all(statement is not None for statement in parsed.statements)


def test_invalid_input_name_is_reported() -> None:
    assert "Input 'bogus' is not valid." in _error_text('set 0 bogus')


def test_lut_input_cannot_be_relatively_addressed() -> None:
    # 'h' is the fixed-high comparator at input 95: above 64, so a '+a'
    # suffix is meaningless on it.
    assert "LUT input 'h' cannot be relatively addressed." in _error_text('set 0 h+a')


def test_range_length_mismatch_is_reported() -> None:
    assert 'ranges not the same length' in _error_text('set 0..3 0..1')


def test_duplicate_output_across_sets_is_reported() -> None:
    assert 'output 0 already set earlier in instruction' in _error_text('set 0 1, set 0 2')


def test_multiple_opcodes_in_one_bundle_is_reported() -> None:
    # Width subs (write/read) are not opcodes: 'write 8, adda 1' is fine.
    bsasm.encode(bsasm.assemble('write 8, adda 1\n'))
    assert 'Cannot have multiple opcodes' in _error_text('adda 1, addb 2')


def test_duplicate_read_or_write_is_reported() -> None:
    # One read and one write in the same bundle is the normal case.
    bsasm.encode(bsasm.assemble('read 8, write 16\n'))
    assert 'Cannot have multiple writes' in _error_text('write 8, write 16')
    assert 'Cannot have multiple reads' in _error_text('read 8, read 16')
    # An explicit zero still counts, so a second write is a duplicate.
    assert 'Cannot have multiple writes' in _error_text('write 0, write 0')
    messages = [d.message for d in parse_document('write 8, write 16\n').diagnostics]
    assert messages == ['Cannot have multiple writes in one instruction']


def test_optional_instruction_group_is_off_by_default() -> None:
    message = _error_text('addctia\n')
    assert "extra instructions 'addcti' are not enabled" in message
    assert 'frozenset' not in message
    assert '--enable' not in message
    # Group names are data, matched case-insensitively, not keywords.
    bsasm.encode(bsasm.assemble('addctia\n', ['ADDCTI']))


def test_unknown_instruction_group_is_rejected() -> None:
    with pytest.raises(AssemblerError, match='Unknown extra instructions') as ctx:
        bsasm.assemble('write 8\n', ['addctia'])
    assert type(ctx.value) is AssemblerError

    with pytest.raises(AssemblerError, match='collection of names'):
        bsasm.assemble('addctia\n', 'addcti')
