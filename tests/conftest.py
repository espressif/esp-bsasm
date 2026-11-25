# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Shared pytest fixtures for the esp-bsasm test suite."""

import io
import os
import runpy
import sys
from collections.abc import Callable, Iterator
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
SRC_DIR = TESTS_DIR.parent / 'src'

# Prefer this checkout over an ESP-IDF tools/bsasm.py sitting on PYTHONPATH.
_src = str(SRC_DIR)
if sys.path[:1] != [_src]:
    sys.path.insert(0, _src)


@dataclass(frozen=True, slots=True)
class BsasmRun:
    returncode: int
    stdout: str
    stderr: str


def invoke_bsasm(args: list[str], *, cwd: Path) -> BsasmRun:
    """Run ``python -m bsasm`` in-process with the given argv and cwd."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    old_argv = sys.argv
    old_cwd = Path.cwd()
    try:
        os.chdir(cwd)
        sys.argv = ['bsasm', 'compile', *args]
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                runpy.run_module('bsasm', run_name='__main__')
        except SystemExit as exc:
            code = 0 if exc.code is None else exc.code
            if not isinstance(code, int):
                code = 1
            return BsasmRun(returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())
        return BsasmRun(returncode=0, stdout=stdout.getvalue(), stderr=stderr.getvalue())
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)


@pytest.fixture(scope='session', autouse=True)
def _ensure_this_repo_bsasm() -> None:
    """Fail fast if tests picked up a different ``bsasm`` module."""
    import bsasm

    actual = Path(bsasm.__file__).resolve()
    expected = (SRC_DIR / 'bsasm' / '__init__.py').resolve()
    if actual != expected:
        pytest.fail(
            f'tests imported the wrong bsasm module: {actual}\n'
            f'expected: {expected}\n'
            'Install this repository (`pip install -e ".[test]"`) and make sure '
            "ESP-IDF's tools/ directory is not ahead of it on PYTHONPATH."
        )


@pytest.fixture(autouse=True, scope='session')
def bsasm_terminal_env() -> Iterator[None]:
    """Keep CLI output stable across TTY and CI (COLUMNS, NO_COLOR, TERM)."""
    keys = ('COLUMNS', 'LINES', 'NO_COLOR', 'FORCE_COLOR', 'PY_COLORS', 'TERM')
    saved = {k: os.environ.get(k) for k in keys}
    os.environ['COLUMNS'] = '1000'
    os.environ['LINES'] = '40'
    os.environ['NO_COLOR'] = '1'
    # A color-capable terminal: TERM=dumb would suppress colors even for
    # FORCE_COLOR, making the color tests depend on the dev's terminal.
    os.environ['TERM'] = 'xterm-256color'
    for k in ('FORCE_COLOR', 'PY_COLORS'):
        os.environ.pop(k, None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture
def run_bsasm() -> Callable[..., BsasmRun]:
    return invoke_bsasm
