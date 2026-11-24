# ESP BitScrambler Assembly — VS Code extension

Syntax-aware editing for `.bsasm` files (ESP-IDF BitScrambler assembly): live diagnostics straight from the assembler's own parser, semantic highlighting derived from the grammar, document outline (labels), go-to-definition and find-references on jump targets, and completion for mnemonics, source bits and cfg keys. Keywords are case-insensitive (`CFG`, `Cfg`, `cfg` all work), and the original spelling is preserved in the editor.

The extension is a thin client: all language intelligence lives in the `esp-bsasm` Python package, launched over stdio as `python -m bsasm.lsp`.

## Install

### 1. The Python package

From PyPI:

```
pip install "esp-bsasm[lsp]"
```

Or from a local checkout, e.g. to test an unreleased change (editable: edits to the package take effect the next time a `.bsasm` file opens):

```
pip install -e "/path/to/esp-bsasm[lsp]"
```

### 2. The extension

Install a built `.vsix` from the Extensions view: `...` → *Install from VSIX...*, or from the command line:

```
code --install-extension esp-bsasm-<version>.vsix
```

To build the `.vsix` yourself:

```
cd editors/vscode
npm install
npm run package
```

### 3. Point it at the right interpreter

The extension runs `python -m bsasm.lsp` using the interpreter from the `bsasm.python` setting (default: `python` on your `PATH`). If the package lives in a virtualenv — for instance the ESP-IDF Python environment — set the interpreter explicitly:

```jsonc
// .vscode/settings.json
{
  "bsasm.python": "/home/you/.espressif/python_env/idf7.0_py3.13_env/bin/python"
}
```

This also matters when VS Code is launched from a desktop launcher that does not inherit your shell's `PATH`.

## Verify

Open a `.bsasm` file: a syntax error below an instruction shows a red squiggle with the assembler's own message. Highlighting and diagnostics require the language server; if it fails to start, the buffer stays plain text. The server log is under *Output* → *BitScrambler Assembly Language Server*.
