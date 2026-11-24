#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Regenerate the golden ``.bsbin`` files from ESP-IDF's reference assembler.

Each ``tests/testcases/*.bsasm`` is compiled by ESP-IDF ``tools/bsasm.py`` and
the resulting binary is committed next to its source as ``<name>.bsbin``. The
test suite then asserts that this repository's ``bsasm`` produces byte-identical
output, so the goldens pin the full binary format against regressions.

The reference assembler lives in a separate esp-idf checkout, so its path is a
required argument rather than a vendored dependency::

    python tests/make_golden.py /path/to/esp-idf/tools/bsasm.py

Only run this when adding or changing a test case; the goldens are committed and
need no regeneration for ordinary development.
"""

import argparse
import subprocess
import sys
from pathlib import Path

TESTCASES = Path(__file__).resolve().parent / 'testcases'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('bsasm', type=Path, help='path to ESP-IDF tools/bsasm.py (the reference assembler)')
    args = parser.parse_args()

    reference = args.bsasm.resolve()
    if not reference.is_file():
        sys.exit(f'reference assembler not found: {reference}')

    sources = sorted(TESTCASES.glob('*.bsasm'))
    if not sources:
        sys.exit(f'no .bsasm sources found in {TESTCASES}')

    for source in sources:
        golden = source.with_suffix('.bsbin')
        subprocess.run([sys.executable, str(reference), str(source), str(golden)], check=True)
        print(f'{source.name} -> {golden.name} ({golden.stat().st_size} bytes)')
    print(f'Wrote {len(sources)} golden binaries to {TESTCASES}.')


if __name__ == '__main__':
    main()
