# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Command line interface of the BitScrambler assembler."""

import json
from pathlib import Path

import rich_click as click
from esp_pylib.errors import FatalError
from esp_pylib.excepthook import install_exception_reporting
from esp_pylib.logger import log

from bsasm.encoder import encode
from bsasm.encoder import reformat_lut
from bsasm.errors import AssemblerError
from bsasm.model import Chipcfg
from bsasm.parsing import parse
from bsasm.sema import DEFAULT_CHIPCFG
from bsasm.sema import analyze


def read_file(filename: str) -> str:
    try:
        with open(filename, encoding='utf-8') as f:
            return f.read()
    except OSError as e:
        # Raise the tool error instead of SystemExit: the exception hook
        # filters SystemExit, so the IDE error handler would never see it.
        raise AssemblerError(f'Error opening {filename}: {e}') from e
    except UnicodeDecodeError as e:
        raise AssemblerError(f'Error decoding {filename}: {e}') from e


def write_file(filename: str, data: bytes) -> None:
    try:
        with open(filename, 'wb') as f:
            f.write(data)
    except OSError as e:
        raise AssemblerError(f'Error writing {filename}: {e}') from e


@click.command(
    context_settings={'help_option_names': ['-h', '--help']},
    help='BitScrambler program assembler',
)
@click.argument('infile', type=click.Path(exists=True, dir_okay=False))
@click.argument('outfile', required=False)
@click.option(
    '-c',
    'chipcfg_path',
    type=click.Path(exists=True, dir_okay=False),
    help=('Set chip capabilities json file; if set, returns an error when an unsupported instruction is assembled'),
)
def main(infile: str, outfile: str | None, chipcfg_path: str | None) -> None:
    chipcfg: Chipcfg
    if chipcfg_path is not None:
        try:
            with open(chipcfg_path, encoding='utf-8') as chipcfg_json:
                chipcfg = json.load(chipcfg_json)
        except OSError as e:
            raise AssemblerError(f'Error opening {chipcfg_path}: {e}') from e
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise AssemblerError(f'Invalid chip capabilities json {chipcfg_path}: {e}') from e
    else:
        chipcfg = DEFAULT_CHIPCFG

    if outfile is None:
        # Default output name: the input path with a '.bsbin' suffix. A
        # literal str.replace-style '.bsasm' strip (the original assembler's
        # re.sub, unescaped and unanchored) ate directory names that contain
        # 'bsasm' - the suffix swap is deterministic instead.
        outfile = str(Path(infile).with_suffix('.bsbin'))
    asm = read_file(infile)
    program = analyze(parse(asm), chipcfg)
    write_file(outfile, encode(program))
    words = len(reformat_lut(program.lut, program.meta.lut_width))
    log.print(f'Written {len(program.insts)} instructions and {words} 32-bit words of LUT.')


def run() -> int:
    """Process boundary shared by both entry points (console script and
    ``python -m bsasm``): install esp-pylib error reporting and translate
    tool errors into a clean message with exit status 2.

    ``main`` stays a plain click command that raises, so programmatic
    callers can catch :class:`~bsasm.errors.AssemblerError` themselves.
    """
    install_exception_reporting()
    try:
        main()
    except FatalError as e:
        log.die(str(e), exit_code=2)
    return 0
