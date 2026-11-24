# esp-bsasm — the BitScrambler assembler

`esp-bsasm` assembles programs written for the Espressif BitScrambler instruction set. It translates `.bsasm` source files into the `.bsbin` binary format loaded by BitScrambler hardware.

The assembler is a standalone Python package. It is not tied to a particular software framework or host application; ESP-IDF is one of its consumers.

## Installation

From PyPI, for command-line and library use:

```console
python -m pip install esp-bsasm
```

Optional dependency groups:

| Extra | Contents | Install |
| --- | --- | --- |
| `test` | pytest, pytest-cov, and the language-server extras (so LSP tests run) | `pip install "esp-bsasm[test]"` |
| `lsp` | pygls and lsprotocol for the language server | `pip install "esp-bsasm[lsp]"` |
| `dev` | commitizen (Espressif rules) for version bumps and changelogs | `pip install "esp-bsasm[dev]"` |

### Installing from a source checkout

Clone the repository and install in editable mode with the extras you need:

```console
git clone <this repository>
cd esp-bsasm
python -m pip install -e ".[test,lsp]"
```

A plain `pip install -e .` (no extras) is enough for the command line and the Python API. Editable mode points the installation at your working tree, so code and grammar changes take effect without reinstalling.

To install from source without editable mode (for example to try an unmerged branch as-is):

```console
python -m pip install "esp-bsasm[lsp] @ file:///path/to/esp-bsasm"
```

Verify the installation:

```console
bsasm --help
python -c "import bsasm; print(bsasm.__version__)"
```

## Command-line usage

```console
bsasm PROGRAM.bsasm [OUTPUT.bsbin] [-c CHIP.json]
```

If the output path is omitted, the assembler replaces the `.bsasm` suffix with `.bsbin`.

The optional chip capability file allows the assembler to reject instructions that are not supported by a particular BitScrambler implementation.

You can also invoke the command through Python:

```console
python -m bsasm PROGRAM.bsasm [OUTPUT.bsbin]
```

The command exits with status 2 when the source cannot be assembled and reports diagnostics with one-based line and column locations.

## Python API

```python
import bsasm

program = bsasm.assemble(source_text, chipcfg)
binary = bsasm.encode(program)
```

`source_text` is a BitScrambler assembly program and `chipcfg` describes the available instruction groups for the target hardware. The returned `binary` is the contents of a `.bsbin` file.

Invalid sources raise `bsasm.AssemblerErrors`; its `errors` attribute holds every individual `AssemblerSyntaxError` with its source location — the same full set the CLI and the editor report.

## Editor support (VS Code)

A VS Code extension in [`editors/vscode/`](editors/vscode/) provides live diagnostics, semantic highlighting, a document outline of labels, go-to-definition and find-references on jump targets, and completion for mnemonics, source bits and cfg keys. Diagnostics, highlighting and navigation all come from this package's parser and analyzer - the same code `bsasm` uses - so they cannot drift from the assembler. Both the CLI and the editor report every error they can recover: the CLI prints each diagnostic on its own line, the editor shows them all at once. The editor analyzes with the CLI's default `support_all` configuration (it does not take a `-c` chip-capability file).

Coloring and diagnostics appear only after the language server starts. If `esp-bsasm[lsp]` is missing from the interpreter in `bsasm.python`, the file stays plain text; the server log is under *Output* → *BitScrambler Assembly Language Server*.

The server is `python -m bsasm.lsp`, also installed as the `bsasm-lsp` command.

To set it up from a source checkout:

1. Install the package with the language-server extra:

   ```console
   python -m pip install -e ".[lsp]"
   ```

2. Build and install the extension (requires Node.js):

   ```console
   cd editors/vscode
   npm install
   npm run package
   code --install-extension esp-bsasm-<version>.vsix
   ```

3. Point the extension at the interpreter that has the package installed. It launches `python -m bsasm.lsp` with the `bsasm.python` setting (default `python`). In VS Code settings:

   ```json
   "bsasm.python": "/path/to/python-with-esp-bsasm"
   ```

4. Open a `.bsasm` file. Expect live diagnostics for syntax errors, colored mnemonics, source bits, comments and numbers, the label outline in the outline view, completion while typing, and F12 navigation from a jump target to its label.

## Documentation

For the language reference, BitScrambler programming model, and binary format, see the [ESP32-C5 Technical Reference Manual — BitScrambler](https://documentation.espressif.com/esp32-c5_technical_reference_manual_en.pdf) and the [ESP-IDF BitScrambler programming guide](https://docs.espressif.com/projects/esp-idf/en/latest/esp32c5/api-reference/peripherals/bitscrambler.html).

## Development

Set up a development environment once:

```console
python -m pip install -e ".[test,dev]"
pre-commit install
```

The grammar is defined in [`BitScrambler.g4`](BitScrambler.g4). Generated ANTLR sources are committed under `src/bsasm/generated/`, so using the package does not require Java or ANTLR to be installed.

After changing the grammar, regenerate the parser with:

```console
python regenerate.py
```

To verify that the generated files are up to date:

```console
python regenerate.py --check
```

Run the test suite with:

```console
python -m pytest
```

The tests include the BitScrambler corpus and command-line coverage. They also check decoded fields in generated `.bsbin` files against the expected sidecar data. Linting and formatting run through the installed pre-commit hooks on every commit.

## Advanced development: changing the grammar

The grammar is the single source of truth for the syntax of the BitScrambler language. Keep it free of target-language actions and semantic predicates so that it remains a portable ANTLR grammar.

When adding a keyword token, define it before `NAME` because equal-length lexer matches are resolved in favor of the first rule, and add the keyword to the `identifier` rule when labels with that spelling must remain valid, such as `loopa:` or `jmp set`.

Keep glued constructs as single lexer tokens when whitespace is not allowed; for example, `AUX_CMP` represents `bl<=o0` and `REL_OPERAND` represents `l0+a`. A content statement occupies one line, and a comma always introduces another sub-instruction rather than acting as a dangling separator.

After changing `BitScrambler.g4`, run `python regenerate.py`, commit the generated files under `src/bsasm/generated/`, and add or update tests before submitting the change.

## Advanced development: adding an instruction

1. Add the mnemonic token, parser rule, operand shape, `subInstr` alternative, and `identifier` entry in `BitScrambler.g4`.
2. Regenerate the parser with `python regenerate.py` and commit the generated files.
3. Add the corresponding statement dataclass to `src/bsasm/model.py`.
4. Add a `visitSub*` method to `src/bsasm/builder.py`; for A/B/H/L variants, update the mnemonic-to-counter-and-halves mapping.
5. Handle the new statement in `src/bsasm/sema.py`, including chip capability checks where applicable.
6. Update `src/bsasm/encoder.py` only when the instruction introduces a genuinely new hardware opcode pattern; the existing opcode base table already covers the standard opcode families.
7. Add or update tests under `tests/`, including a `.bsasm` and sidecar `.json` pair when the instruction affects the binary corpus.
8. Update `src/bsasm/lsp.py`: add the mnemonic to `_MNEMONIC_TOKENS` (highlighting and completion derive from that list) and `_HOVER_DOCS`.

## Advanced development: adding a configuration key

1. Add the key and its value spellings to the grammar and add a `cfgStmt` alternative.
2. Add the key to the appropriate model enum, together with a dedicated value enum when necessary.
3. Add an explicit `visitCfgStmt` alternative in `src/bsasm/builder.py`; an unhandled alternative should fail loudly rather than fall through to another key.
4. Add the corresponding handling to `_collect_cfg` in `src/bsasm/sema.py` and preserve byte-identical defaults for existing programs.
5. Update `src/bsasm/encoder.py` only when the configuration value is represented in the `.bsbin` header.
6. Add regression tests under `tests/`.
7. Update `src/bsasm/lsp.py`: add the key/value tokens to `_CFG_KEY_TOKENS` / `_CFG_VALUE_TOKENS` and `_HOVER_DOCS`.

## Package structure

The assembler processes a program through these stages:

```text
source text -> parser -> semantic analysis -> binary encoder -> .bsbin
```

The public API is exposed by `bsasm`. The command-line entry point is `bsasm.cli`, and the generated parser implementation is an internal detail.

## Compatibility

The binary encoder targets the BitScrambler binary format used by Espressif hardware. The test corpus covers supported instruction forms, configuration values, LUT encodings, and binary header fields. Changes to the grammar or encoder should preserve the existing binary format unless a corresponding hardware-format change is intended.
