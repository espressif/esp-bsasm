# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Command line interface of the BitScrambler assembler."""

from pathlib import Path

import rich_click as click
from esp_pylib.errors import FatalError
from esp_pylib.excepthook import install_exception_reporting
from esp_pylib.logger import log

from bsasm import __version__
from bsasm.encoder import encode, reformat_lut
from bsasm.errors import AssemblerError, AssemblerErrors
from bsasm.isa import OPTIONAL_INSTRUCTION_GROUPS
from bsasm.parsing import parse
from bsasm.sema import analyze, normalize_extra_inst


def read_file(filename: str) -> str:
    try:
        with open(filename, encoding='utf-8') as f:
            return f.read()
    except OSError as e:
        # SystemExit is filtered by the exception hook: raising the tool
        # error keeps the IDE error handler in the loop.
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
@click.version_option(version=__version__, prog_name='bsasm')
@click.argument('infile', type=click.Path(exists=True, dir_okay=False))
@click.argument('outfile', required=False)
@click.option(
    '--enable-extra-inst',
    'enabled_extra_inst',
    multiple=True,
    metavar='NAME',
    help=(
        'Enable extra instructions for this target. Repeat this option, or '
        'separate several names with commas. Each name is one family '
        f'(one of: {", ".join(sorted(OPTIONAL_INSTRUCTION_GROUPS))}). '
        'Names are case-insensitive.'
    ),
)
def main(infile: str, outfile: str | None, enabled_extra_inst: tuple[str, ...]) -> None:
    # One option value may list several families ('addcti,other'); repeating
    # the option is the same thing. Both forms become one set of names.
    names = [part.strip() for value in enabled_extra_inst for part in value.split(',') if part.strip()]
    enabled = normalize_extra_inst(names)

    if outfile is None:
        # Default output name: the input path with a '.bsbin' suffix. A
        # literal str.replace-style '.bsasm' strip (the original assembler's
        # re.sub, unescaped and unanchored) ate directory names that contain
        # 'bsasm' - the suffix swap is deterministic instead.
        outfile = str(Path(infile).with_suffix('.bsbin'))
    asm = read_file(infile)
    parsed = parse(asm)
    if parsed.errors:
        raise AssemblerErrors(parsed.errors)
    program, errors = analyze(parsed.statements, enabled)
    if errors:
        raise AssemblerErrors(errors)
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
    except AssemblerErrors as e:
        for error in e.errors:
            log.print(f'ERROR: {error}')
        return 2
    except FatalError as e:
        log.die(str(e), exit_code=2)
    return 0
