# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Entry point for ``python -m bsasm``."""

from esp_pylib.errors import FatalError
from esp_pylib.excepthook import install_exception_reporting
from esp_pylib.logger import log

from bsasm.cli import main

if __name__ == '__main__':
    install_exception_reporting()
    try:
        main()
    except FatalError as e:
        log.die(str(e), exit_code=2)
