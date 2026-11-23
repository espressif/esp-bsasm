# SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Drive the language server over stdio exactly like an editor would.

tests/test_lsp.py exercises the pure helpers; this module exercises the
pygls handlers themselves through a real ``python -m bsasm.lsp`` process,
so protocol-level mistakes (wrong params types, misframed replies) fail
here instead of only in an editor.
"""

import json
import queue
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import pytest

REPO = Path(__file__).resolve().parent.parent
TESTCASE = Path(__file__).resolve().parent / 'testcases' / 'eof_on_downstream.bsasm'
URI = TESTCASE.as_uri()
START_TIMEOUT = 15.0


class Server:
    """A spawned bsasm language server with framed JSON-RPC helpers."""

    def __init__(self) -> None:
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'bsasm.lsp'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO,
        )
        stdin = self.process.stdin
        stdout = self.process.stdout
        stderr = self.process.stderr
        assert stdin is not None and stdout is not None and stderr is not None
        self.stdin: IO[bytes] = stdin
        self.stdout: IO[bytes] = stdout
        self.stderr: IO[bytes] = stderr
        self.messages: queue.Queue[dict] = queue.Queue()
        self.stderr_lines: list[str] = []
        self._threads = [
            threading.Thread(target=self._drain_stderr, daemon=True),
            threading.Thread(target=self._reader, daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def _drain_stderr(self) -> None:
        for line in iter(self.stderr.readline, b''):
            self.stderr_lines.append(line.decode())

    def _reader(self) -> None:
        while True:
            line = self.stdout.readline()
            if not line:
                break
            if line.lower().startswith(b'content-length:'):
                length = int(line.split(b':', 1)[1])
                while self.stdout.readline() not in (b'\r\n', b'\n'):
                    pass  # skip remaining headers (Content-Type etc.)
                message: dict = json.loads(self.stdout.read(length))
                self.messages.put(message)

    def send(self, message: dict) -> None:
        body = json.dumps(message).encode()
        self.stdin.write(f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        self.stdin.flush()

    def request(self, req_id: int, method: str, params: dict) -> dict:
        self.send({'jsonrpc': '2.0', 'id': req_id, 'method': method, 'params': params})
        while True:
            message: dict = self.messages.get(timeout=START_TIMEOUT)
            if message.get('id') == req_id:
                assert 'error' not in message, f'{method} errored: {message["error"]}'
                result: dict = message['result']
                return result
            self.messages.put(message)  # keep notifications for wait_diagnostics

    def notify(self, method: str, params: dict) -> None:
        self.send({'jsonrpc': '2.0', 'method': method, 'params': params})

    def wait_diagnostics(self) -> dict:
        while True:
            message: dict = self.messages.get(timeout=START_TIMEOUT)
            if message.get('method') == 'textDocument/publishDiagnostics':
                params: dict = message['params']
                return params

    def close(self) -> None:
        # Closing stdin makes the server exit; the reader threads then hit EOF
        # on their own, so joining them before closing the remaining pipes
        # avoids racing a readline() on a closed file.
        self.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        for thread in self._threads:
            thread.join(timeout=5)
        for stream in (self.stdout, self.stderr):
            try:
                stream.close()
            except OSError:
                pass


@pytest.fixture
def server() -> Iterator[Server]:
    server = Server()
    yield server
    server.close()


def assert_server_clean(server: Server) -> None:
    logged = ''.join(server.stderr_lines)
    assert 'Error in server' not in logged
    assert 'Traceback' not in logged


def test_stdio_server_round_trip(server: Server) -> None:
    good = TESTCASE.read_text()
    result = server.request(1, 'initialize', {'processId': None, 'rootUri': None, 'capabilities': {}})
    capabilities = result['capabilities']
    assert capabilities['semanticTokensProvider']['full']
    server.notify('initialized', {})

    server.notify(
        'textDocument/didOpen', {'textDocument': {'uri': URI, 'languageId': 'bsasm', 'version': 1, 'text': good}}
    )
    diagnostics = server.wait_diagnostics()
    assert diagnostics['uri'] == URI
    assert diagnostics['diagnostics'] == []

    server.notify(
        'textDocument/didChange',
        {'textDocument': {'uri': URI, 'version': 2}, 'contentChanges': [{'text': good + 'bogus_op\n'}]},
    )
    diagnostics = server.wait_diagnostics()
    assert diagnostics['diagnostics'], 'a broken line must produce diagnostics'

    # Semantic errors surface on syntactically clean documents: an undefined
    # jump target comes straight from the analyzer.
    server.notify(
        'textDocument/didChange',
        {'textDocument': {'uri': URI, 'version': 3}, 'contentChanges': [{'text': 'jmp nowhere\n'}]},
    )
    diagnostics = server.wait_diagnostics()
    assert diagnostics['diagnostics'], 'undefined jump target must produce diagnostics'
    assert 'Label not found' in diagnostics['diagnostics'][0]['message']

    server.notify(
        'textDocument/didChange', {'textDocument': {'uri': URI, 'version': 4}, 'contentChanges': [{'text': good}]}
    )
    diagnostics = server.wait_diagnostics()
    assert diagnostics['diagnostics'] == []

    # Regression: DidSaveTextDocumentParams.text_document is a
    # TextDocumentIdentifier (uri only) - the handler must read the
    # workspace copy, not params.text_document.text.
    server.notify('textDocument/didSave', {'textDocument': {'uri': URI}})
    diagnostics = server.wait_diagnostics()
    assert diagnostics['diagnostics'] == []

    tokens = server.request(2, 'textDocument/semanticTokens/full', {'textDocument': {'uri': URI}})
    assert tokens['data']

    hover = server.request(
        5, 'textDocument/hover', {'textDocument': {'uri': URI}, 'position': {'line': 1, 'character': 5}}
    )
    assert hover is not None
    assert 'eof_on' in hover['contents']['value']

    completion = server.request(
        3, 'textDocument/completion', {'textDocument': {'uri': URI}, 'position': {'line': 0, 'character': 0}}
    )
    items = completion['items'] if isinstance(completion, dict) else completion
    assert len(items) >= 7  # the mnemonic set

    symbols = server.request(4, 'textDocument/documentSymbol', {'textDocument': {'uri': URI}})
    assert isinstance(symbols, list)
    assert_server_clean(server)
