# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Assemble each ``tests/testcases/*.bsasm`` and compare byte-for-byte with a golden.

Each golden ``<name>.bsbin`` next to its source was compiled by ESP-IDF's
reference ``tools/bsasm.py`` (regenerate with ``tests/make_golden.py``). Asserting
byte equality pins the entire binary - header, every instruction bit and the LUT
words - so a regression in any encoded field fails the suite. This replaces the
old JSON sidecar check, which compared only a subset of decoded fields and
ignored extra keys and list tails.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from bsbin import unpack_binary

TESTCASES_DIR = Path(__file__).resolve().parent / 'testcases'
SRC_DIR = TESTCASES_DIR.parent.parent / 'src'


@dataclass(frozen=True, slots=True)
class Case:
    """One golden test case.

    Keep annotations as runtime objects here: ESP-IDF's pytest plugin loads
    test modules with a custom loader that does not always register the module
    in ``sys.modules``. Python's dataclass implementation needs that
    registration when resolving postponed (string) annotations; ``slots=True``
    is safe once annotations are evaluated at runtime.
    """

    name: str
    source: Path
    golden: Path


def _load_cases() -> list[Case]:
    return [
        Case(name=source.stem, source=source, golden=source.with_suffix('.bsbin'))
        for source in sorted(TESTCASES_DIR.glob('*.bsasm'))
    ]


# Extra instructions the corpus programs exercise; the caller (the test
# harness) enables them explicitly, since nothing is enabled by default
# (see ``bsasm.isa.OPTIONAL_INSTRUCTION_GROUPS``).
ENABLED_GROUPS: dict[str, frozenset[str]] = {
    'opcodes2': frozenset({'addcti'}),
}


def _mismatch_detail(actual: Path, golden: Path) -> str:
    """Byte-level diff plus decoded fields, to locate a regression."""
    got = actual.read_bytes()
    want = golden.read_bytes()
    lines = [
        f'binary differs from golden {golden.name}',
        f'  length: got {len(got)} bytes, golden {len(want)} bytes',
    ]
    for offset in range(min(len(got), len(want))):
        if got[offset] != want[offset]:
            lines.append(
                f'  first differing byte at offset {offset}: got 0x{got[offset]:02x}, golden 0x{want[offset]:02x}'
            )
            break
    for label, path in (('actual', actual), ('golden', golden)):
        lines.append(f'  decoded {label}:')
        lines.extend(f'    {line}' for line in json.dumps(unpack_binary(path), indent=2).splitlines())
    return '\n'.join(lines)


def test_assemble_subprocess(tmp_path: Path) -> None:
    """Verify ``python -m bsasm`` as a real process, byte-exact against golden."""
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
    golden = TESTCASES_DIR / 'sanity.bsbin'
    assert outfile.read_bytes() == golden.read_bytes(), _mismatch_detail(outfile, golden)


@pytest.mark.parametrize('case', _load_cases(), ids=lambda case: case.name)
def test_assemble(case: Case, run_bsasm, tmp_path: Path) -> None:
    outfile = tmp_path / f'{case.name}.bsbin'
    enable_args: list[str] = []
    for group in sorted(ENABLED_GROUPS.get(case.name, frozenset())):
        enable_args += ['--enable-extra-inst', group]
    result = run_bsasm([str(case.source), str(outfile), *enable_args], cwd=tmp_path)
    captured = (result.stdout + result.stderr).strip()
    assert result.returncode == 0, (
        f'{case.name} was expected to succeed, assembler exited {result.returncode}\n{captured}'
    )
    assert case.golden.is_file(), (
        f'{case.name}: missing golden {case.golden.name} next to the .bsasm; regenerate with tests/make_golden.py'
    )
    assert outfile.read_bytes() == case.golden.read_bytes(), _mismatch_detail(outfile, case.golden)
