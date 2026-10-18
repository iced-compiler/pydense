# Test suite layout

- `test_lexer.py`, `test_parser.py`, `test_emitter.py` — unit tests for the core;
  `test_parser_spellings.py` — spellings only hand-written `.dpy` reaches (implicit concatenation,
  header trailing commas, f-string corners, invalid spellings that must raise, nesting depth).
- `test_roundtrip_batteries.py` — data-driven AST round-trip (`ast.dump(parse(encode(src))) == ast.dump(ast.parse(src))`)
  over every snippet in `batteries/*.py`, in all three modes with the mode-adjusted reference.
- `test_lenient_input.py` / `test_rejected_input.py` — SPEC §17.6 / §17.7.
- `test_lint.py` — W001–W005; `test_errors.py` — E001–E009 messages and positions.
- `test_canonical.py` — Rosetta stone (SPEC §14) exact text + idempotence `encode(decode(encode(x))) == encode(x)`.
- `test_receiver_rule.py` — SPEC §7 table.
- `test_corpus.py` — stdlib subset round trip (fast); set `PYDENSE_FULL_CORPUS=1` for the whole stdlib.
- `test_runtime.py`, `test_cli.py`, `test_mcp.py` — runtime, console script, MCP tools and stdio transport.
- `test_tokens.py` — token regression (skipped without tiktoken).
- `test_fuzz.py` — hypothesmith round-trip fuzz (skipped without hypothesmith) and spec-legal layout perturbations.
- `test_fuzz.py` — spec-legal layout perturbations over stdlib modules (dependency-free);
  `test_fuzz_hypothesis.py` — random Python round trips (skipped without hypothesmith).
- `batteries/` — data-driven snippet modules, each exporting `SNIPPETS` (items: `src` | `(name, src)` |
  `(src, (3, 12))` | `(name, src, (3, 12))`); `lenient.py` holds `(name, dpy, python)` pairs and
  `rejected.py` holds `(name, dpy, error_code)` pairs. `construct_matrix.py` is the per-node-type
  matrix; the others port the design review's candidate batteries (Python side only, deduplicated by AST).
- `samples/` — the 7 reference programs behind the SPEC §12 token figures (`test_tokens.py`,
  `test_canonical.py` workloads).
- `_util.py` — the mode-adjusted reference normaliser (SPEC §11), battery loader, token helpers.
