# esp-bsasm — the BitScrambler program assembler

`esp-bsasm` translates BitScrambler assembly programs (`.bsasm`) into the
binary format the BitScrambler hardware loads (`.bsbin`), as documented in
the ESP32-C5 Technical Reference Manual, BitScrambler (BITSCRM) chapter, and
in the ESP-IDF programming guide under *API Reference > Peripherals >
BitScrambler*.

This README is written for maintainers. For the user-visible language and
build integration, see the ESP-IDF programming guide; for the hardware bit
layouts, see the TRM chapter.

## Relationship with ESP-IDF

ESP-IDF consumes this package as the `esp-bsasm` pip dependency (listed in
`tools/requirements/requirements.core.txt`) and builds BitScrambler programs
from its own CI. It does not vendor the sources; what lives on the ESP-IDF
side is the test suite (`tools/test_bsasm/`), which validates the installed
package — including unreleased branches via the `CI_PYTHON_TOOL_REPO` /
`CI_PYTHON_TOOL_BRANCH` CI mechanism (see below). Language changes are
developed and validated here; an ESP-IDF MR is only needed when wiring the
results into the ESP-IDF test suite.

## Directory layout

```
BitScrambler.g4           the language grammar: the single source of truth
                          for the syntax of the language
regenerate.py             re-create the ANTLR products (pinned ANTLR version;
                          --check verifies the committed files are in sync)
pyproject.toml            package metadata (no setup.py; src layout)
src/bsasm/
    generated/            ANTLR-generated lexer/parser/visitor (committed,
                          so assembling never needs a JDK)
    parsing.py            ANTLR driver: source text -> parse tree
    builder.py            visitor: parse tree -> statements
    model.py              all the data: statement IR and program IR (frozen
                          dataclasses over shared instruction-level enums)
    sema.py               semantic analysis: statements -> Program (label
                          resolution, ranges, mux compatibility, chip gating)
    encoder.py            Program -> .bsbin bytes (257-bit instructions,
                          header, LUT packing)
    cli.py                command line interface
    errors.py             AssemblerError diagnostics with 1-based locations
```

The pipeline is strictly linear, one module per stage, each independently
testable:

```
source text --parsing--> parse tree --builder--> statements --sema--> Program --encoder--> .bsbin
```

`model.py` owns all the data; `parsing`/`builder` only move data into shape;
`sema` owns every decision that needs a readable diagnostic; `encoder` is a
mechanical bit packer.

## Who checks what

The grammar owns the *shape* of the language; the assembler owns *meaning*:

| Grammar (`BitScrambler.g4`) | Assembler (`sema.py`, `encoder.py`) |
| --- | --- |
| instruction operand counts and shapes | numeric ranges (e.g. width ∈ {0, 8, 16, 32}) |
| ranges (`a..b`), comparator sources (`bl<=o0`), relative addressing (`5+a`) | value spellings (`cfg prefetch true`, hex/bin) |
| bundle structure (comma continuation, newline termination) | label resolution and duplicate detection |
| labels vs mnemonics lexing (`loopa:` is a label) | ctrsel/lutsel/rel_addr conflicts between mux sources |
| | the 8-instruction hardware limit, output duplication checks, jump targets past the program end |

Rationale: only the assembler can produce readable diagnostics (it knows
what a mux source *means*), while ANTLR reports syntax errors with exact
positions and is far easier to extend than hand-rolled character scanning.

## Workflow: assembling a program (daily use)

```
python -m bsasm program.bsasm [output.bsbin] [-c chip.json]
```

`chip.json` describes per-chip capabilities (see the
`bsasm_targets/*.json` files in ESP-IDF). As a library:

```python
import bsasm

program = bsasm.assemble(source_text, chipcfg)
binary = bsasm.encode(program)
```

## Workflow: changing the grammar

1. Edit `BitScrambler.g4`.
2. Run `python regenerate.py` and commit the regenerated files under
   `src/bsasm/generated/`. CI checks they are in sync (`--check`).
3. Add tests (see *Testing* below) and, if the language changed, update the
   ESP-IDF programming guide.

Rules of thumb that keep the grammar clean:

* Keep it free of target-language actions and semantic predicates, so it
  stays a portable spec.
* Every keyword token must be defined before `NAME` (equal-length lexer
  matches go to the first rule) and must be accepted by the `identifier`
  rule, so labels named after keywords (`loopa:`, `jmp set`) keep working.
* Glued constructs must be single lexer tokens: `AUX_CMP` ('bl<=o0') and
  `REL_OPERAND` ('l0+a') pin the no-whitespace rule without target-specific
  tricks.
* One content statement per line (`line` rule); a comma always introduces
  another sub-instruction (no dangling commas).

## Workflow: adding an instruction

1. Grammar: add the mnemonic token (with case-insensitive fragments, before
   `NAME`) and a parser rule wiring its operand shape; add the rule to
   `subInstr` and the token to `identifier`.
2. Regenerate (`python regenerate.py`) and commit.
3. `model.py`: add a `*Sub` statement dataclass.
4. `builder.py`: add a `visitSub*` method — for mnemonics with A/B/H/L
   suffixes, add a mnemonic→(counter, halves) table alongside the existing
   ones.
5. `sema.py`: handle the new sub-instruction in `_InstBuilder.add`,
   producing an `Opcode`; wrap in `_check_chip_supports(...)` if gated, and
   list the group in the chip capability json.
6. `encoder.py`: extend the opcode assembly only for a genuinely new
   opcode pattern (the `_OP_BASES` table covers all seven hardware
   opcodes).
7. Tests as above.

## Workflow: adding a cfg key

1. Grammar: keyword token(s) for the key and its value spellings, plus a
   `cfgStmt` alternative.
2. `model.py`: `CfgKey` member, plus a dedicated enum type if the value is
   an enum (see `LoopEndsOn`).
3. `builder.py`: a `visitCfgStmt` alternative. Match explicitly — a missing
   alternative must fail loudly, not fall through to another key.
4. `sema.py`: a `_collect_cfg` case with the allowed spellings; make sure
   the `ProgramMeta` default keeps old programs byte-identical.
5. `encoder.py`: only if the value reaches the .bsbin header — see
   `loop_ends_on` and the formerly-reserved header byte for the pattern.
6. Tests — the regression suite currently lives in ESP-IDF at
   `tools/test_bsasm/` (see below) and runs against the installed package.

## Testing

The regression suite currently lives in ESP-IDF at `tools/test_bsasm/`
(subprocess harness over JSON-sidecar testcases, the frozen byte-compat
golden corpus, and API-level tests including TRM bit-layout conformance)
and runs against the installed `esp-bsasm` package. It migrates into this
repository once the first release cycle has settled.

## Testing unreleased changes in ESP-IDF CI

ESP-IDF can test a Python tool package from a live git branch instead of the
released version: its CI defines `CI_PYTHON_TOOL_REPO` and
`CI_PYTHON_TOOL_BRANCH` (component inputs of the `ci/actions/common`
template, documented in esp-idf's `.gitlab/ci/common.yml`). Running the
ESP-IDF pipeline with those set to `espressif/esp-bsasm` and this
repository's branch pip-installs this checkout into the ESP-IDF CI
environment before the jobs run — so ESP-IDF's `tools/test_bsasm` suite
validates an unmerged esp-bsasm branch end to end.

Today ESP-IDF CI already exercises the vendored copy at `tools/bsasm` with
no extra configuration; the mechanism becomes relevant once ESP-IDF
switches to consuming the published package (then a esp-bsasm MR triggers
an ESP-IDF pipeline against its own branch before release).

## Repository CI

`.gitlab-ci.yml` runs three jobs on merge requests and on the default
branch: `pre-commit` (ruff-based hooks, see `.pre-commit-config.yaml`),
`regenerate-check` (`regenerate.py --check`, needs a JDK; only when the
grammar changed), and `publish_pypi` on release tags `v*` (build + twine
upload; requires the protected/masked `TWINE_USERNAME`/`TWINE_PASSWORD` CI
variables).

## Pre-commit hooks — code quality

- ruff for linting (pyflakes, pycodestyle, import sorting and pyupgrade
  rules) and ruff for code formatting
- mypy type checker
- codespell for finding common misspellings
- conventional-precommit-linter for checking commit messages

The ruff, mypy and codespell settings live in `pyproject.toml`. Install the
hooks locally with `pre-commit install`; most hooks fix the problems they
find instead of only reporting them.

## Generated files and linting

`src/bsasm/generated/` is machine output (ANTLR 4.13.2, pinned in
`pyproject.toml` and `regenerate.py`; keep the two in sync). It is excluded
from ruff, ruff format, the whitespace/EOF hooks and mypy error reporting
(per-module override in `pyproject.toml`) — do not edit or reformat it by
hand. All other sources are ruff-formatted (single quotes, 120 columns,
py311 target).

## Behaviour compatibility contract

The rewrite is verified byte-identical against the original assembler (the
one that lived in ESP-IDF until the ANTLR rewrite) on the golden corpus.
Beyond that contract:

**Fixed bugs** (all clean errors now): `cfg trailing_bytes` above 8191 (was
a `struct.pack` crash); `l8`/`l16` beyond the LUT width (were silently
encoded as comparator inputs); 16-bit LUT values above 65535 (wrapped
around); jump targets past the program end (overflowed the 3-bit target
field into the counter-select bit); duplicate labels (silently
overwritten).

**Tightened error handling** (legal programs unaffected): misspelled
mnemonics like `ifx`/`loopax`/`addafoo`, dangling trailing commas, numeric
labels, two bundles on one line — all syntax errors now.

**Kept quirks** for parity: labels and cfg spellings are case-insensitive;
a bare `+a` operand resolves to input 32 relative; duplicate `write`/`read`
in one bundle keep the last value; the `Did you forget an L` hint message.

**Diagnostics**: 1-based line/column; exit code 2 on any error.
