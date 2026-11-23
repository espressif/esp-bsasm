# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Assemble each ``tests/testcases/*.bsasm`` and check the sidecar ``.json``.

The cases started as a copy of ESP-IDF ``tools/test_bsasm``. Same input
program should produce the same decoded fields as IDF's ``bsasm.py``.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from bsbin import assert_expected_subset
from bsbin import unpack_binary

TESTCASES_DIR = Path(__file__).resolve().parent / 'testcases'
SRC_DIR = TESTCASES_DIR.parent.parent / 'src'


@dataclass(frozen=True, slots=True)
class Case:
    """One sidecar test case.

    Keep annotations as runtime objects here: ESP-IDF's pytest plugin loads
    test modules with a custom loader that does not always register the module
    in ``sys.modules``. Python's dataclass implementation needs that
    registration when resolving postponed (string) annotations; ``slots=True``
    is safe once annotations are evaluated at runtime.
    """

    name: str
    source: Path
    expect: Path


def _load_cases() -> list[Case]:
    return [
        Case(name=source.stem, source=source, expect=source.with_suffix('.json'))
        for source in sorted(TESTCASES_DIR.glob('*.bsasm'))
    ]


def test_assemble_subprocess(tmp_path: Path) -> None:
    """Verify ``python -m bsasm`` as a real process, not only in-process CLI."""
    outfile = tmp_path / 'sanity.bsbin'
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join([str(SRC_DIR), env.get('PYTHONPATH', '')]).rstrip(os.pathsep)
    result = subprocess.run(
        [sys.executable, '-m', 'bsasm', str(TESTCASES_DIR / 'sanity.bsasm'), str(outfile)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    captured = (result.stdout + result.stderr).strip()
    assert result.returncode == 0, f'subprocess assembler exited {result.returncode}\n{captured}'
    assert outfile.is_file()


@pytest.mark.parametrize('case', _load_cases(), ids=lambda case: case.name)
def test_assemble(case: Case, run_bsasm, tmp_path: Path) -> None:
    outfile = tmp_path / f'{case.name}.bsbin'
    result = run_bsasm([str(case.source), str(outfile)], cwd=tmp_path)
    captured = (result.stdout + result.stderr).strip()
    assert result.returncode == 0, (
        f'{case.name} was expected to succeed, assembler exited {result.returncode}\n{captured}'
    )
    assert case.expect.is_file(), (
        f'{case.name}: missing expect JSON next to the .bsasm; decoded output:\n'
        f'{json.dumps(unpack_binary(outfile), indent=4)}'
    )
    expected = json.loads(case.expect.read_text(encoding='utf-8'))
    assert_expected_subset(unpack_binary(outfile), expected, '')
