#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Regenerate the ANTLR lexer/parser for the BitScrambler grammar.

The generated Python modules are committed under src/bsasm/generated/ so
that assembling a program never needs a JDK; only the antlr4-python3-runtime
pip package is required at run time. This script is for grammar development:
it regenerates the modules with the ANTLR tool jar vendored in vendor/ and
can verify in CI (--check) that the committed modules are in sync with
BitScrambler.g4.

The vendored jar is the only ANTLR tool ever used: it is part of the
repository, so regeneration is reproducible, works offline, and never
depends on (or trusts) a download. A missing jar is an error, not a prompt
to fetch one.

Usage:
    python regenerate.py           # regenerate in place
    python regenerate.py --check   # fail if out of sync
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

# Keep this in sync with the antlr4-python3-runtime pin in pyproject.toml.
ANTLR_VERSION = '4.13.2'

HERE = Path(__file__).resolve().parent
GRAMMAR = HERE / 'BitScrambler.g4'
GENERATED = HERE / 'src' / 'bsasm' / 'generated'
# The exact jar the committed generated sources were produced with.
VENDORED_JAR = HERE / 'vendor' / f'antlr-{ANTLR_VERSION}-complete.jar'
# Files ANTLR generates from this grammar; anything else in generated/ (the
# __init__.py) is left alone.
GENERATED_FILES = [
    'BitScrambler.interp',
    'BitScrambler.tokens',
    'BitScramblerLexer.interp',
    'BitScramblerLexer.py',
    'BitScramblerLexer.tokens',
    'BitScramblerListener.py',
    'BitScramblerParser.py',
    'BitScramblerVisitor.py',
]


def generate(dest: Path) -> None:
    if not VENDORED_JAR.exists():
        sys.exit(
            f'{VENDORED_JAR} not found. The ANTLR {ANTLR_VERSION} tool jar is vendored in this\n'
            'repository and is never downloaded; restore it from version control.'
        )
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        'java',
        '-jar',
        str(VENDORED_JAR),
        '-Dlanguage=Python3',
        '-visitor',
        '-listener',
        '-Xexact-output-dir',
        '-o',
        str(dest),
        # Bare filename with cwd=HERE: ANTLR embeds the grammar path it was
        # given into the generated header, so an absolute path here would
        # make the committed output machine-specific and break --check.
        GRAMMAR.name,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=HERE)
    except FileNotFoundError:
        sys.exit('java not found; a JDK (any version supported by ANTLR 4) is needed to regenerate the parser')
    except subprocess.CalledProcessError as e:
        sys.exit(f'ANTLR generation failed:\n{e.stderr}')
    if result.stderr:
        # ANTLR warnings (e.g. a new grammar ambiguity) do not fail the
        # build; show them instead of letting them go unnoticed.
        sys.stderr.write(result.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='verify generated files match the grammar, do not write')
    args = parser.parse_args()

    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp)
            generate(fresh)
            mismatched = [
                name for name in GENERATED_FILES if (fresh / name).read_bytes() != (GENERATED / name).read_bytes()
            ]
        if mismatched:
            names = ', '.join(mismatched)
            sys.exit(
                f'{GENERATED} is out of sync with {GRAMMAR.name} for: {names}\nRun regenerate.py and commit the result.'
            )
        print(f'{GENERATED} is in sync with {GRAMMAR.name}.')
        return

    if not GRAMMAR.exists():
        sys.exit(f'{GRAMMAR} not found')
    generate(GENERATED)
    print(f'Regenerated {len(GENERATED_FILES)} files in {GENERATED}.')


if __name__ == '__main__':
    main()
