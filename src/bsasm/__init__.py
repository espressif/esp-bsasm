# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Public API of the BitScrambler assembler.

Typical use, mirroring what the CLI does::

    import bsasm

    program = bsasm.assemble(source_text, chipcfg)
    binary = bsasm.encode(program)

Any source errors are reported together as :class:`AssemblerErrors`, whose
``errors`` attribute holds each individual :class:`AssemblerSyntaxError`.
"""

__version__ = '0.1.0'

from bsasm.encoder import encode
from bsasm.errors import AssemblerError, AssemblerErrors, AssemblerSyntaxError, Location
from bsasm.model import Chipcfg, Instruction, Program, ProgramMeta
from bsasm.parsing import parse
from bsasm.sema import DEFAULT_CHIPCFG, analyze

__all__ = [
    'DEFAULT_CHIPCFG',
    'AssemblerError',
    'AssemblerErrors',
    'AssemblerSyntaxError',
    'Instruction',
    'Location',
    'Program',
    'ProgramMeta',
    'analyze',
    'encode',
    'parse',
]


def assemble(source: str, chipcfg: Chipcfg | None = None) -> Program:
    """Parse and analyze bsasm ``source`` into a :class:`Program`.

    Raises :class:`AssemblerErrors` for any problem in the source; its
    ``errors`` attribute holds every individual diagnostic. This is the same
    analysis the CLI and the language server use, so all three report the
    same set of problems.
    """
    parsed = parse(source)
    if parsed.errors:
        raise AssemblerErrors(parsed.errors)
    program, errors = analyze(parsed.statements, chipcfg)
    if errors:
        raise AssemblerErrors(errors)
    return program
