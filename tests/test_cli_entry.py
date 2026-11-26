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

import pytest

from bsasm import __version__
from bsasm.cli import read_text_file, run
from bsasm.errors import AssemblerError


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
    code, out, err = invoke_run(['bsasm', 'compile', str(bad)])
    assert code == 2
    combined = out + err
    assert 'Traceback' not in combined
    assert 'line 1' in combined  # the assembler's own diagnostic


def test_unified_compile_subcommand(tmp_path) -> None:
    good = tmp_path / 'ok.bsasm'
    good.write_text('main:\n    write 8\n', encoding='utf-8')
    code, out, err = invoke_run(['bsasm', 'compile', str(good)])
    assert code == 0
    assert 'Written' in out
    assert err == ''


def test_format_errors_use_the_process_boundary(tmp_path) -> None:
    source = tmp_path / 'invalid.bsasm'
    original = 'set 0 1,\n'
    source.write_text(original, encoding='utf-8')

    code, out, err = invoke_run(['bsasm', 'format', str(source)])

    assert code == 2
    assert 'line 2' in out + err
    assert source.read_text(encoding='utf-8') == original


def test_format_syntax_error_from_stdin_uses_process_boundary(monkeypatch) -> None:
    monkeypatch.setattr(sys, 'stdin', io.StringIO('set 0 1,\n'))

    code, out, err = invoke_run(['bsasm', 'format', '-'])

    assert code == 2
    assert 'line 2' in out + err


def test_format_processes_remaining_files_after_a_failure(tmp_path: Path) -> None:
    good = tmp_path / 'good.bsasm'
    good.write_text('write\t8\n', encoding='utf-8')
    bad = tmp_path / 'bad.bsasm'
    bad.write_text('set 0 1 @\n', encoding='utf-8')

    code, out, err = invoke_run(['bsasm', 'format', str(good), str(bad)])

    assert code == 2
    combined = out + err
    assert str(bad) in combined  # the failing file is named with its diagnostics
    assert good.read_text(encoding='utf-8') == '    write 8\n'  # still reformatted


def test_format_check_reports_every_failing_file(tmp_path: Path) -> None:
    bad1 = tmp_path / 'bad1.bsasm'
    bad2 = tmp_path / 'bad2.bsasm'
    bad1.write_text('set 0 1 @\n', encoding='utf-8')
    bad2.write_text('write 8 %\n', encoding='utf-8')

    code, out, err = invoke_run(['bsasm', 'format', '--check', str(bad1), str(bad2)])

    assert code == 2
    combined = out + err
    assert str(bad1) in combined and str(bad2) in combined


def test_format_check_with_failures_exits_2_not_1(tmp_path: Path) -> None:
    changed = tmp_path / 'changed.bsasm'
    changed.write_text('write\t8\n', encoding='utf-8')
    bad = tmp_path / 'bad.bsasm'
    bad.write_text('set 0 1 @\n', encoding='utf-8')

    code, out, err = invoke_run(['bsasm', 'format', '--check', str(changed), str(bad)])

    assert code == 2  # a hard error, not the --check "would change" status
    assert 'Would reformat' in out + err


def test_compile_without_subcommand_is_rejected(tmp_path) -> None:
    good = tmp_path / 'ok.bsasm'
    good.write_text('main:\n    write 8\n', encoding='utf-8')
    code, out, err = invoke_run(['bsasm', str(good)])
    assert code != 0
    assert 'No such command' in err
    assert out == ''


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


def test_unwritable_directory_makes_format_fail_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / 'prog.bsasm'
    original = 'write\t8\n'
    source.write_text(original, encoding='utf-8')

    # chmod-based setup is unreliable when CI runs as root; force the same
    # filesystem failure at the atomic-write boundary instead.
    def deny_temporary_file(*args: object, **kwargs: object) -> None:
        raise PermissionError('read-only directory')

    monkeypatch.setattr('bsasm.cli.tempfile.mkstemp', deny_temporary_file)
    code, out, err = invoke_run(['bsasm', 'format', str(source)])

    assert code == 2
    combined = out + err
    assert 'Traceback' not in combined
    assert 'Error writing' in combined
    assert source.read_text(encoding='utf-8') == original


def test_read_text_file_translates_os_errors(tmp_path: Path) -> None:
    # click.Path rejects directories and unreadable files before the CLI
    # helper runs, so exercise the helper's OSError branch directly.
    with pytest.raises(AssemblerError, match='Error opening'):
        read_text_file(str(tmp_path))


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
