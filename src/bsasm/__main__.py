# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Entry point for ``python -m bsasm``."""

import sys

from bsasm.cli import run

if __name__ == '__main__':
    sys.exit(run())
