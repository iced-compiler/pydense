# Changelog

All notable changes to PyDense are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-18

The grammar, the package layout and the file suffix all changed. Nothing written for v0.2 parses under v1.0, and
the v1.0 tools do not read `.pyd` files. The reasons are measurements, recorded in `docs/SPEC.md` §12 and
`docs/PRIOR_ART.md`.

### Changed - the grammar is replaced

v0.2 was a sigil dialect: `@c`/`@f`/`@i` for `class`/`def`/`__init__`, `?c{}:{}` for `if`/`else`, `~x:it{}` for
`for`, `^x` for `return`, `!{}` for `try`, `&&`/`||`/`!` for `and`/`or`/`not`, `\a:b` for `lambda`, `$0` positional
parameter references, and `#np`/`%p`-style macros for libraries and builtins.

Exact `tiktoken` counts (o200k_base and cl100k_base) on the reference samples and on a 469-file corpus showed that
these were token-neutral or negative, not positive:

- A Python keyword is one BPE token and the following space fuses into the next identifier (`def update(` is
  3 tokens). A sigil in the same position costs the same or more (`@f update(` is also 3; `!isinstance(` splits
  `is` + `instance` and costs one more than `not isinstance(`).
- The `#`/`%` macros cost +35 tokens on the samples; `@f`/`@c` +10; `^` for `return` +5; `;` after every `}` +13.
  The `\` lambda saved exactly 0 tokens in 8 of 8 realistic contexts; `}:{` for `else` saved 3 tokens in 1281
  (0.2%); `import a=b` saved 1 token but is invented syntax that no model has seen.
- The literature says the same: SimPy needs vocabulary surgery and continued pre-training to pay off, and Token
  Sugar reports GPT-4.1 Pass@1 falling from 94.5% to 51.2% on untrained sugared code.

v1.0 keeps every Python keyword, operator, literal form, import, decorator, comprehension, pattern and f-string.
Exactly five things differ from Python, each with a measured delta on the 7-sample set (docstrings dropped on both
sides, o200k): `{}` blocks and canonical layout (-78 tokens on top of whitespace removal, which is -146), `.x` and
the implicit receiver (-26), the `c?a:b` ternary (-5), `{}` for a `pass`-only body (-2 per occurrence), and
shortest-form floats `1.` / `.5` (-42). The full ablation ladder is `docs/SPEC.md` §12.2.

Dropped constructs are not silently misparsed: a v0.2 sigil or macro at statement start is rejected with error
`E008` and a hint naming the Python keyword to use.

### Changed - the file suffix is `.dpy`, not `.pyd`

`.pyd` is CPython's own suffix for Windows extension modules (`importlib.machinery.EXTENSION_SUFFIXES`). A
`.pyd` file next to a package on Windows is picked up by the import system as a binary module. The dense form is
now `.dpy` everywhere: CLI, MCP tools (`read_file_as_dpy`, `write_dpy_file`, `execute_dpy`, `transpile_dpy`,
`check_dpy`, `get_dpy_cheatsheet`), `init-skill` output and documentation.

### Changed - package layout

The three top-level modules (`pydense.py`, `mcp_server.py`, `pydense_cli.py`) and `grammar.lark` are replaced by
the `pydense/` package: `lexer`, `parser` (hand-written recursive descent that builds `ast` nodes directly, no
intermediate Python text and no `lark` dependency), `emitter` (an `ast._Unparser` subclass, so precedence and
quoting are inherited from CPython), `lint`, `runtime`, `skill`, `cli`, `mcp_server`, `errors`. The public API is
`pydense.encode` / `decode` / `parse` / `compile` / `check` / `lint` / `run`, `pydense.Mode`, `pydense.Diagnostic`,
`pydense.PyDenseSyntaxError` and `pydense.CHEATSHEET` (`docs/API_CONTRACT.md`). Console scripts are
`pydense = pydense.cli:main` and `pydense-mcp = pydense.mcp_server:main`. The v0.2 files live on in `legacy/`,
unsupported and uninstalled, only so `benchmarks/corpus_fidelity.py --backend legacy` can reproduce the before/after.

### Added - fidelity as a guarantee

- FULL mode is an exact AST bijection: `ast.dump(parse(encode(src))) == ast.dump(ast.parse(src))` for every
  Python 3.10-3.13 module construct (`docs/SPEC.md` §9). Verified 469/469 files (12,508 top-level statements) in
  FULL and NODOC modes at design time; the CI gate reruns the stdlib corpus on every push and fails below 100%.
  v0.2 measured 73.6% statement fidelity on 109 stdlib files.
- Three reported modes, always side by side: FULL (default), NODOC (docstrings dropped) and STRIPPED (lossy:
  annotations dropped too). The canonical form is a fixed point (`encode(decode(encode(x))) == encode(x)`).
- Lenient input: `a if c else b`, `lambda`, explicit `self`/`cls`, `self.x`, `1.0`, `{pass}`, `;`, `if x:{`,
  comments and `\`-continuation all parse; the emitter always writes the canonical spelling.
- Diagnostics `E001`-`E009` with `line:col` and a one-line hint (every unmatched `{` is listed on EOF), and lint
  warnings `W001`-`W005` (`pydense check`, MCP `check_dpy`).
- `pydense.Mode`, `--mode full|nodoc|stripped` on the CLI and MCP tools, `--pretty` keyword spacing, and a
  zero-dependency stdio JSON-RPC MCP transport when the `mcp` package is not installed.
- `benchmarks/token_compression.py` reports o200k and cl100k for `ast.unparse` (with and without docstrings),
  python-minifier whitespace-only, and all three PyDense modes, each percentage against its stated baseline.

### Fixed

An adversarial review (five independent reviewers, every finding re-verified by two skeptics) found 23 confirmed
issues; all are fixed: f-string edge cases (`\N{NAME}` escapes, a backslash before a brace, backslashes in format
specs, quote selection when the literal parts use every quote style, braces inside a format spec), yields and
one-element tuples in `for`/`match` headers, a display as an exception type, an operator or `=` continuing across a
line break, deep nesting (now a clean E000 instead of a `RecursionError`), the match-statement speculation swallowing
real errors, invalid parameter and argument orders that CPython rejects, `SystemExit`/`KeyboardInterrupt` and
`input()` inside `execute_dpy`, ASCII-safe JSON on the stdio transport, and every stale number in the documents.

### Removed

- All v0.2 sigils, macros (`#T`, `#np`, `%p`, ...), `$n` positional references and the auto-import prelude.
- `--strip-types` (replaced by `--mode stripped`), `pydense compile`/`decompile` subcommands (now `decode`/`encode`),
  `pydense test` (use `pytest`).
- The `lark` grammar and the `grammar.lark` file.

### Measured (o200k_base; cl100k_base figures are in the README tables and track o200k within half a point on the samples)

7 samples: FULL -16.41% vs `ast.unparse` with docstrings; NODOC -19.42% vs the no-docstring baseline; STRIPPED
-24.00% vs the no-docstring baseline (-36.84% vs with-docstring, lossy). 469-file corpus (148 stdlib + 321 site-packages modules, this
implementation): FULL -12.04%, NODOC -15.85% vs the no-docstring baseline, STRIPPED -41.16% vs with-doc (the
docstrings alone are 25.8% of the baseline tokens); python-minifier whitespace-only on the same files -6.71%. The 50% figure v0.2 headlined was measured against unformatted source
with annotations stripped and is not reproduced by any lossless mode.

## [0.2.0] - 2026-10

Sigil dialect (`.pyd`), `lark`-based parser, FastMCP/stdio MCP server, `SKILL.md` installer. Kept in `legacy/`.
