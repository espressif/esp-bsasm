# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Operand-parsing cases the binary corpus does not cover.

``set`` endpoints are NUMBER tokens (hex/binary/sign included). Spellings
that mean the same integer must assemble to the same binary; values outside
0..31 (outputs) or 0..63 (numeric inputs) stay clean errors, never a traceback.
"""

from pathlib import Path

import pytest

TESTCASES_DIR = Path(__file__).resolve().parent / 'testcases'

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


def test_cli_reports_packed_lut_word_count(run_bsasm, tmp_path: Path) -> None:
    # lut8.bsasm holds 5 values of 8 bits -> 2 32-bit words in the binary.
    # An explicit outfile keeps the written binary out of tests/testcases/.
    source = TESTCASES_DIR / 'lut8.bsasm'
    outfile = tmp_path / 'lut8.bsbin'
    run = run_bsasm([str(source), str(outfile)], cwd=tmp_path)
    assert run.returncode == 0
    assert outfile.exists()
    assert '2 32-bit words of LUT' in run.stdout + run.stderr
