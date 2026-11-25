# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""CLI process-boundary cases that the binary corpus does not cover.

Error paths must exit 2 with the assembler's own message, never a traceback.
Default output naming is a suffix swap, not a global '.bsasm' string replace.
"""

import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bsasm import __version__
from bsasm.cli import run


def invoke_run(argv: list[str]) -> tuple[int | None, str, str]:
    """Call the console-script boundary directly, capturing its exit status."""
    stdout, stderr = io.StringIO(), io.StringIO()
    old_argv = sys.argv
    sys.argv = argv
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code: int | None = run()
            except SystemExit as exc:
                # SystemExit.code is int | str | None; a str never comes from
                # log.die, so normalize it to a plain failure code.
                code = 1 if isinstance(exc.code, str) else exc.code
    finally:
        sys.argv = old_argv
    return code, stdout.getvalue(), stderr.getvalue()


def test_version_option_reports_package_version() -> None:
    code, out, err = invoke_run(['bsasm', '--version'])
    assert code == 0
    assert out.strip() == f'bsasm, version {__version__}'
    assert err == ''


def test_console_entry_reports_tool_errors_with_exit_2(tmp_path) -> None:
    bad = tmp_path / 'bad.bsasm'
    bad.write_text('bogus_op\n', encoding='utf-8')
    code, out, err = invoke_run(['bsasm', str(bad)])
    assert code == 2
    combined = out + err
    assert 'Traceback' not in combined
    assert 'line 1' in combined  # the assembler's own diagnostic


def test_console_entry_success_exits_zero(tmp_path) -> None:
    good = tmp_path / 'ok.bsasm'
    good.write_text('main:\n    write 8\n', encoding='utf-8')
    code, out, _ = invoke_run(['bsasm', str(good)])
    assert code == 0
    assert 'Written' in out


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


def test_optional_instruction_rejected_unless_enabled(run_bsasm, tmp_path: Path) -> None:
    good = tmp_path / 'ok.bsasm'
    good.write_text('main:\n    addctia\n', encoding='utf-8')

    run = run_bsasm([str(good)], cwd=tmp_path)
    combined = run.stdout + run.stderr
    assert run.returncode == 2
    assert 'Traceback' not in combined
    assert "extra instructions 'addcti' are not enabled" in combined
    assert 'frozenset' not in combined
    assert '--enable' not in combined

    run = run_bsasm([str(good), '--enable-extra-inst', 'ADDCTI, addcti'], cwd=tmp_path)
    assert run.returncode == 0


def test_unknown_enable_group_is_rejected(run_bsasm, tmp_path: Path) -> None:
    good = tmp_path / 'ok.bsasm'
    good.write_text('main:\n    write 8\n', encoding='utf-8')
    run = run_bsasm([str(good), '--enable-extra-inst', 'addcti,addctia'], cwd=tmp_path)
    combined = run.stdout + run.stderr
    assert run.returncode == 2
    assert 'Traceback' not in combined
    assert 'Unknown extra instructions' in combined
    assert 'addctia' in combined
    assert 'addcti,addctia' not in combined
