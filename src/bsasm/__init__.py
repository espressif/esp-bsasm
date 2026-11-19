# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Public API of the BitScrambler assembler.

Typical use, mirroring what the CLI does::

    import bsasm

    program = bsasm.assemble(source_text, chipcfg)
    binary = bsasm.encode(program)
"""

__version__ = '0.1.0'

from bsasm.encoder import encode
from bsasm.errors import AssemblerError
from bsasm.errors import AssemblerSyntaxError
from bsasm.errors import Location
from bsasm.model import Chipcfg
from bsasm.model import Instruction
from bsasm.model import Program
from bsasm.model import ProgramMeta
from bsasm.parsing import parse
from bsasm.sema import DEFAULT_CHIPCFG
from bsasm.sema import analyze

__all__ = [
    'DEFAULT_CHIPCFG',
    'AssemblerError',
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

    Raises :class:`AssemblerSyntaxError` (a subclass of esp-pylib's
    FatalError) for any problem in the source.
    """
    return analyze(parse(source), chipcfg)
