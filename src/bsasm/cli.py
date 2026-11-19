# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Command line interface of the BitScrambler assembler."""

import json
import re

import rich_click as click
from esp_pylib.logger import log

from bsasm.encoder import encode
from bsasm.errors import AssemblerError
from bsasm.model import Chipcfg
from bsasm.parsing import parse
from bsasm.sema import analyze


def read_file(filename: str) -> str:
    try:
        with open(filename) as f:
            return f.read()
    except OSError as e:
        # Raise the tool error instead of SystemExit: the exception hook
        # filters SystemExit, so the IDE error handler would never see it.
        raise AssemblerError(f'Error opening {filename}: {e}') from e


def write_file(filename: str, data: bytes) -> None:
    with open(filename, 'wb') as f:
        f.write(data)


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
            with open(chipcfg_path) as chipcfg_json:
                chipcfg = json.load(chipcfg_json)
        except json.JSONDecodeError as e:
            raise AssemblerError(f'Invalid chip capabilities json {chipcfg_path}: {e}') from e
    else:
        chipcfg = {'chipname': 'chip', 'extra_instruction_groups': [], 'support_all': True}

    if outfile is None:
        # Same default output name as the original assembler: replace the
        # first '.bsasm'-ish stretch of the input name with '.bsbin'.
        outfile = re.sub('.bsasm', '', infile) + '.bsbin'
    asm = read_file(infile)
    program = analyze(parse(asm), chipcfg)
    write_file(outfile, encode(program))
    log.print(f'Written {len(program.insts)} instructions and {len(program.lut)} 32-bit words of LUT.')
