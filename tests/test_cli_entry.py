# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""CLI process-boundary cases that the binary corpus does not cover.

Error paths must exit 2 with the assembler's own message, never a traceback.
Default output naming is a suffix swap, not a global '.bsasm' string replace.
"""

from pathlib import Path


def test_unwritable_output_reports_clean_error(run_bsasm, tmp_path: Path) -> None:
    good = tmp_path / 'ok.bsasm'
    good.write_text('main:\n    write 8\n', encoding='utf-8')
    outfile = tmp_path / 'out.d'  # a directory: open() fails with IsADirectoryError
    outfile.mkdir()
    run = run_bsasm([str(good), str(outfile)], cwd=tmp_path)
    combined = run.stdout + run.stderr
    assert run.returncode == 2
    assert 'Traceback' not in combined
    assert 'Error writing' in combined


def test_undecodable_input_reports_clean_error(run_bsasm, tmp_path: Path) -> None:
    bad = tmp_path / 'bad.bsasm'
    bad.write_bytes(b'main:\n    write \xff\xfe\n')
    run = run_bsasm([str(bad)], cwd=tmp_path)
    combined = run.stdout + run.stderr
    assert run.returncode == 2
    assert 'Traceback' not in combined
    assert 'Error decoding' in combined


def test_undecodable_chipcfg_reports_clean_error(run_bsasm, tmp_path: Path) -> None:
    good = tmp_path / 'ok.bsasm'
    good.write_text('main:\n    write 8\n', encoding='utf-8')
    cfg = tmp_path / 'cfg.json'
    cfg.write_bytes(b'\xff\xfe{}')
    run = run_bsasm([str(good), '-c', str(cfg)], cwd=tmp_path)
    combined = run.stdout + run.stderr
    assert run.returncode == 2
    assert 'Traceback' not in combined
    assert 'Invalid chip capabilities' in combined


def test_default_outfile_keeps_directory_names(run_bsasm, tmp_path: Path) -> None:
    src_dir = tmp_path / 'bsasm.dir'
    src_dir.mkdir()
    good = src_dir / 'prog.bsasm'
    good.write_text('main:\n    write 8\n', encoding='utf-8')
    run = run_bsasm([str(good)], cwd=tmp_path)
    assert run.returncode == 0
    assert (src_dir / 'prog.bsbin').exists()
    assert not (tmp_path / 'prog.bsbin').exists()


def test_default_outfile_replaces_only_the_final_suffix(run_bsasm, tmp_path: Path) -> None:
    good = tmp_path / 'xbsasm.bsasm'
    good.write_text('main:\n    write 8\n', encoding='utf-8')
    run = run_bsasm([str(good)], cwd=tmp_path)
    assert run.returncode == 0
    assert (tmp_path / 'xbsasm.bsbin').exists()
