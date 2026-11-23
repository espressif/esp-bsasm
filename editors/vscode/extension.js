// Thin LSP client: all language intelligence lives in the bsasm Python
// package (src/bsasm/lsp.py), launched over stdio.
const { execFile } = require('child_process');
const vscode = require('vscode');
const { LanguageClient, TransportKind } = require('vscode-languageclient/node');

let client;
let extensionContext;

function getPython() {
  return vscode.workspace.getConfiguration('bsasm').get('python', 'python');
}

const SERVER_ARGS = ['-m', 'bsasm.lsp'];

function ensureServerImport(python) {
  return new Promise((resolve, reject) => {
    execFile(python, ['-c', 'import bsasm.lsp'], { timeout: 20000 }, (err, _stdout, stderr) => {
      if (!err) {
        resolve();
        return;
      }
      const detail = (stderr || err.message).trim().split('\n')[0];
      reject(
        new Error(
          `could not import bsasm.lsp using ${python}. ` +
            `Install it with: ${python} -m pip install "esp-bsasm[lsp]"` +
            (detail ? ` (${detail})` : ''),
        ),
      );
    });
  });
}

function createClient(python) {
  const serverOptions = {
    command: python,
    args: SERVER_ARGS,
    transport: TransportKind.stdio,
  };
  const clientOptions = {
    // No scheme filter: unsaved (untitled) buffers get language support too.
    documentSelector: [{ language: 'bsasm' }],
    // A missing module exits before initialize; do not retry.
    initializationFailedHandler: () => false,
  };
  return new LanguageClient(
    'bsasm-language-server',
    'BitScrambler Assembly Language Server',
    serverOptions,
    clientOptions,
  );
}

async function stopClient() {
  if (!client) {
    return;
  }
  try {
    await client.stop();
  } catch {
    // A process that exits before initialize leaves the client in
    // 'starting', where stop() throws.
  }
  const index = extensionContext.subscriptions.indexOf(client);
  if (index !== -1) {
    extensionContext.subscriptions.splice(index, 1);
  }
  client = undefined;
}

async function startClient() {
  const python = getPython();
  await stopClient();
  await ensureServerImport(python);
  client = createClient(python);
  extensionContext.subscriptions.push(client);
  await client.start();
}

function showStartError(reason) {
  vscode.window.showErrorMessage(`bsasm language server failed to start: ${reason}`);
}

function activate(context) {
  extensionContext = context;
  // Not awaited: activation must not fail because the interpreter is
  // misconfigured. A start failure surfaces as an error message instead.
  startClient().catch(showStartError);
  // The interpreter is resolved when the server starts; restart on change
  // so editing bsasm.python takes effect without a window reload.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration('bsasm.python')) {
        startClient().catch(showStartError);
      }
    }),
  );
}

function deactivate() {
  return stopClient();
}

module.exports = { activate, deactivate };
