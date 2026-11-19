# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Error types and source locations for the BitScrambler assembler."""

from dataclasses import dataclass

from esp_pylib.errors import FatalError


@dataclass(frozen=True, slots=True)
class Location:
    """A position in the source file.

    Lines and columns are counted from one, as users of other assemblers
    expect. ``text`` is the token or sub-instruction the location points at,
    ready to be quoted in diagnostics.
    """

    line: int
    column: int
    text: str = ''

    def describe(self) -> str:
        return f'line {self.line} column {self.column}'


class AssemblerError(FatalError):
    """Base class for every diagnostic the assembler reports."""


class AssemblerSyntaxError(AssemblerError):
    """Raised for lexical, syntactic and semantic problems in the source.

    ``first`` and ``second`` point at the offending source location(s); some
    checks (like two incompatible mux inputs) naturally involve two places
    and report both.
    """

    def __init__(self, first: Location, message: str, second: Location | None = None) -> None:
        if second is None:
            msg = f'{first.describe()}: "{first.text}": {message}'
        else:
            msg = f'{first.describe()}: "{first.text}" and {second.describe()}: "{second.text}": {message}'
        super().__init__(msg)
        self.first = first
        self.second = second
        self.message = message
