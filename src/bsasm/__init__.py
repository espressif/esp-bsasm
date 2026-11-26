# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Public API of the BitScrambler assembler.

Typical use, mirroring what the CLI does::

    import bsasm

    program = bsasm.assemble(source_text)
    binary = bsasm.encode(program)

Extra instructions are off by default. Pass the names the target supports
as ``enabled_extra_inst`` (the CLI:
``bsasm compile --enable-extra-inst addcti,other ...``). One name enables a
family of mnemonics; ``addcti`` enables ``ADDCTIA``, ``ADDCTIB`` and their
``H``/``L`` forms.

Any source errors are reported together as :class:`AssemblerErrors`, whose
``errors`` attribute holds each individual :class:`AssemblerSyntaxError`.
"""

__version__ = '0.2.0'

from collections.abc import Iterable

from bsasm.encoder import encode
from bsasm.errors import AssemblerError, AssemblerErrors, AssemblerSyntaxError, Location
from bsasm.formatting import FormatOptions, format_source
from bsasm.model import Instruction, Program, ProgramMeta
from bsasm.parsing import parse
from bsasm.sema import analyze, normalize_extra_inst

__all__ = [
    'AssemblerError',
    'AssemblerErrors',
    'AssemblerSyntaxError',
    'FormatOptions',
    'Instruction',
    'Location',
    'Program',
    'ProgramMeta',
    'analyze',
    'assemble',
    'encode',
    'format_source',
    'parse',
]


def assemble(source: str, enabled_extra_inst: Iterable[str] = ()) -> Program:
    """Parse and analyze bsasm ``source`` into a :class:`Program`.

    ``enabled_extra_inst`` lists the extra instructions the target
    supports. Each name enables one family (``OPTIONAL_INSTRUCTION_GROUPS``
    in :mod:`bsasm.isa`; ``addcti`` enables the ``ADDCTI*`` mnemonics). Names
    are matched case-insensitively, and the default enables nothing. An
    unknown name raises :class:`AssemblerError`. Using an instruction whose
    family is not listed raises :class:`AssemblerErrors`.

    Raises :class:`AssemblerErrors` for any problem in the source; its
    ``errors`` attribute holds every individual diagnostic. This is the same
    analysis the CLI uses.
    """
    enabled = normalize_extra_inst(enabled_extra_inst)
    parsed = parse(source)
    if parsed.errors:
        raise AssemblerErrors(parsed.errors)
    program, errors = analyze(parsed.statements, enabled)
    if errors:
        raise AssemblerErrors(errors)
    return program
