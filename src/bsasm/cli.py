# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Unified command-line interface for bsasm."""

import difflib
import os
import sys
import tempfile
from pathlib import Path

import rich_click as click
from esp_pylib.errors import FatalError
from esp_pylib.excepthook import install_exception_reporting
from esp_pylib.logger import log
from rich.console import Console
from rich.syntax import Syntax

from bsasm import __version__
from bsasm.encoder import encode, reformat_lut
from bsasm.errors import AssemblerError, AssemblerErrors
from bsasm.formatting import FormatOptions, format_source
from bsasm.isa import OPTIONAL_INSTRUCTION_GROUPS
from bsasm.parsing import parse
from bsasm.sema import analyze, normalize_extra_inst


def read_text_file(filename: str) -> str:
    try:
        return Path(filename).read_text(encoding='utf-8')
    except OSError as e:
        # SystemExit is filtered by the exception hook: raising the tool
        # error keeps the IDE error handler in the loop.
        raise AssemblerError(f'Error opening {filename}: {e}') from e
    except UnicodeDecodeError as e:
        raise AssemblerError(f'Error decoding {filename}: {e}') from e


def write_binary_file(filename: str, data: bytes) -> None:
    try:
        Path(filename).write_bytes(data)
    except OSError as e:
        raise AssemblerError(f'Error writing {filename}: {e}') from e


def write_text_file(filename: str, data: str) -> None:
    """Replace *filename* atomically, keeping its permissions."""
    path = Path(filename)
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(data)
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o7777)
        os.replace(temporary, path)
    except OSError as e:
        raise AssemblerError(f'Error writing {filename}: {e}') from e
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


@click.group(
    context_settings={'help_option_names': ['-h', '--help']},
    help='BitScrambler assembler, formatter and language server.',
)
@click.version_option(version=__version__, prog_name='bsasm')
def main() -> None:
    """Unified bsasm command-line entry point."""


@main.command('compile', help='Assemble a BitScrambler source file.')
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
def compile_command(infile: str, outfile: str | None, enabled_extra_inst: tuple[str, ...]) -> None:
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
    asm = read_text_file(infile)
    parsed = parse(asm)
    if parsed.errors:
        raise AssemblerErrors(parsed.errors)
    program, errors = analyze(parsed.statements, enabled)
    if errors:
        raise AssemblerErrors(errors)
    write_binary_file(outfile, encode(program))
    words = len(reformat_lut(program.lut, program.meta.lut_width))
    log.print(f'Written {len(program.insts)} instructions and {words} 32-bit words of LUT.')


@main.command('format', help='Format BitScrambler assembly source files.')
@click.argument('infiles', nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, allow_dash=True))
@click.option('--check', is_flag=True, help='Do not write files; exit 1 if any file would change.')
@click.option(
    '--diff',
    'show_diff',
    is_flag=True,
    help='Show a unified diff instead of writing files; combines with --check.',
)
@click.option('--indent-width', type=click.IntRange(min=1), default=4, show_default=True, help='Spaces per level.')
@click.option(
    '--comment-column',
    type=click.IntRange(min=1),
    default=None,
    help='Column for trailing comments (default: eight times the indent width).',
)
@click.option('--tabs/--spaces', default=False, help='Indent with tabs instead of spaces.')
def format_command(
    infiles: tuple[str, ...],
    check: bool,
    show_diff: bool,
    indent_width: int,
    comment_column: int | None,
    tabs: bool,
) -> None:
    if '-' in infiles and len(infiles) != 1:
        raise click.UsageError('standard input cannot be combined with other input files')

    options = FormatOptions(indent_width=indent_width, comment_column=comment_column, use_tabs=tabs)
    changed: list[str] = []
    failed: list[str] = []
    failures: list[AssemblerError] = []
    # Every file is processed even when others fail (read error, syntax
    # error, write error): a batch run reports all problems at once instead
    # of stopping at the first, and good files are still reformatted.
    for filename in infiles:
        display = '<stdin>' if filename == '-' else filename
        try:
            original = sys.stdin.read() if filename == '-' else read_text_file(filename)
            formatted = format_source(original, options)
        except AssemblerError as e:
            failed.append(display)
            errors = e.errors if isinstance(e, AssemblerErrors) else [e]
            failures.extend(AssemblerError(f'{display}: {error}') for error in errors)
            continue
        if formatted == original:
            continue

        changed.append(display)
        if check:
            click.echo(f'Would reformat {display}', err=True)
        if show_diff:
            patch = ''.join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    formatted.splitlines(keepends=True),
                    fromfile=f'{display} (before)',
                    tofile=f'{display} (after)',
                )
            )
            # Rich handles TTY/NO_COLOR detection; soft_wrap keeps long diff
            # lines intact when output is piped or redirected.
            Console().print(
                Syntax(patch.rstrip('\n'), 'diff', background_color='default'),
                end='',
                soft_wrap=True,
            )
        if not (check or show_diff):
            if filename == '-':
                click.echo(formatted, nl=False)
            else:
                try:
                    write_text_file(filename, formatted)
                except AssemblerError as e:
                    failed.append(display)
                    failures.append(AssemblerError(f'{display}: {e}'))

    if not (show_diff or '-' in infiles):
        unchanged = len(infiles) - len(changed) - len(failed)
        if changed:
            verb = 'would be reformatted' if check else 'reformatted'
            click.echo(f'{len(changed)} file(s) {verb}', err=True)
        if unchanged and not changed:
            click.echo(f'{"All " if not failures else ""}{unchanged} file(s) already formatted', err=True)

    if failures:
        raise AssemblerErrors(failures)
    if check and changed:
        raise click.exceptions.Exit(1)


@main.command('lsp', help='Run the language server over standard input/output.')
@click.option(
    '--stdio',
    '_stdio',
    is_flag=True,
    hidden=True,
    help='Accepted for LSP clients that append it; stdio is the only transport.',
)
def lsp_command(_stdio: bool) -> None:
    # vscode-languageclient appends --stdio to stdio-transport servers. The
    # server always uses stdio, so the flag is accepted and ignored.
    # LSP dependencies are an optional extra; defer this import until the
    # command is selected so compile/format work without pygls installed.
    from bsasm.lsp import run_stdio_server

    run_stdio_server()


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
