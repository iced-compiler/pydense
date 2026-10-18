# PyDense v1.0 — package layout and public API contract

This is the contract every module, test and document in the repository is written against.
The grammar itself is `docs/SPEC.md`. File suffix for the dense form: **`.dpy`**.

## Package layout

```
pydense/
  __init__.py      public API re-exports (below) + __version__
  _version.py      __version__ = "1.0.0"
  errors.py        PyDenseSyntaxError, PyDenseRuntimeError, Diagnostic
  strings.py       string and f-string scanning shared by the lexer and the parser
  rules.py         the receiver rule (SPEC §7) and the legacy macro names (E008) shared by parser and emitter
  lexer.py         Token, tokenize()
  parser.py        Parser: .dpy text -> ast.Module (builds ast nodes directly)
  emitter.py       Emitter(ast._Unparser): ast -> canonical .dpy text, modes, pretty flag
  lint.py          W001–W005 warnings over a parsed module (+ token stream)
  runtime.py       run()/run_repl()/RunResult, REPL-style last-expression evaluation, compact tracebacks
  skill.py         CHEATSHEET (the 418-token LLM cheat sheet) and AGENT_WORKFLOW (MCP directives)
  cli.py           `pydense` console script
  mcp_server.py    `pydense-mcp` console script (FastMCP if installed, zero-dep stdio JSON-RPC fallback)
tests/             pytest suite (see tests/README.md)
benchmarks/        token_compression.py (3 modes, o200k+cl100k, python-minifier baseline), corpus_fidelity.py
docs/              SPEC.md, API_CONTRACT.md, PRIOR_ART.md
legacy/            v0.2 implementation, only for before/after benchmarking
```

## Public API (`import pydense`)

```python
pydense.__version__: str                       # "1.0.0"

class pydense.Mode(str, Enum):
    FULL = "full"          # exact AST bijection: annotations + docstrings kept   (default)
    NODOC = "nodoc"        # docstrings dropped (Module/ClassDef/FunctionDef/AsyncFunctionDef first-stmt str Expr)
    STRIPPED = "stripped"  # NODOC + parameter/return annotations dropped; `x: T = v` -> `x = v`; bare `x: T` kept

def pydense.encode(source: str | ast.AST, *, mode: Mode | str = Mode.FULL, pretty: bool = False,
                   filename: str = "<python>") -> str
    # Python source (or an ast.Module) -> canonical .dpy text (docs/SPEC.md §10). `pretty=True` writes a space
    # between a keyword and a following `.`/quote (`return .x`, `return 'x'`). Raises SyntaxError for bad Python.

def pydense.parse(text: str, *, filename: str = "<dpy>") -> ast.Module
    # .dpy text -> ast.Module with line/col positions filled in. Raises PyDenseSyntaxError (subclass of SyntaxError).
    # Accepts every lenient spelling in SPEC §17.6; rejects legacy sigils with code E008.

def pydense.decode(text: str, *, filename: str = "<dpy>") -> str
    # .dpy text -> standard Python source (ast.unparse of parse(text)), with a trailing newline.

def pydense.compile(text: str, filename: str = "<dpy>", mode: str = "exec") -> types.CodeType
    # parse + builtins.compile. An attribute of the package (`pydense.compile(...)`) but deliberately NOT in
    # `pydense.__all__`, so `from pydense import *` does not shadow the builtin.

def pydense.check(text: str, *, filename: str = "<dpy>") -> list[Diagnostic]
    # parse + lint. Returns diagnostics sorted by position: at most one "error" (the first syntax error, never raised)
    # followed by/or "warning" items (W001–W005). An empty list means clean.

def pydense.lint(tree_or_text: ast.Module | str, *, filename: str = "<dpy>") -> list[Diagnostic]
    # Only the W-series warnings (SPEC §13). Text input is parsed first (raises on syntax error).

@dataclass(frozen=True)
class pydense.Diagnostic:
    code: str          # "E001".."E009", "W001".."W005"
    message: str       # human/LLM readable, one line
    lineno: int        # 1-based
    col: int           # 0-based
    severity: str      # "error" | "warning"
    hint: str = ""     # one-line fix suggestion (may be empty)
    def __str__(self) -> str: ...   # "E001 3:17: unexpected end of input ... (hint: ...)"

class pydense.PyDenseSyntaxError(SyntaxError):
    code: str          # "E001".."E009"
    hint: str
    # .lineno / .offset / .filename / .text as in SyntaxError; str(err) == f"{code} {lineno}:{col}: {msg}" (+ hint)

class pydense.PyDenseRuntimeError(RuntimeError):
    original: BaseException | None
    # raised by run() in place of the program's own exception; str() is format_compact_error(original)

pydense.CHEATSHEET: str          # from pydense.skill
pydense.run(text: str, env: dict | None = None, *, filename: str = "<dpy>") -> dict        # from pydense.runtime
pydense.run_repl(text: str, env: dict, *, filename: str = "<dpy>") -> RunResult             # from pydense.runtime
pydense.RunResult                                                                           # from pydense.runtime
pydense.format_compact_error(exc: BaseException, filename: str | None = None) -> str        # "!Err[fn:L3]: ValueError(msg)"
```

`pydense.__all__` is exactly: `CHEATSHEET`, `Diagnostic`, `Mode`, `PyDenseRuntimeError`, `PyDenseSyntaxError`,
`RunResult`, `__version__`, `check`, `decode`, `encode`, `format_compact_error`, `lint`, `parse`, `run`, `run_repl`,
plus `Emitter` and `Parser`. `Emitter` (`pydense.emitter`) and `Parser` (`pydense.parser`) are exported for advanced
use only: their constructor and method signatures are **unstable** and may change in a minor release; everything
else above is covered by semantic versioning. `compile` is reachable as `pydense.compile` but is not in `__all__`.

Error codes (SPEC §13): E001 unclosed `{` at EOF (lists each unmatched `{` position), E002 unmatched `}`,
E003 missing separator between simple statements, E004 non-chain decorator, E005 ternary/lambda in f-string field
needs parentheses, E006 stray `\`, E007 `def!` outside a class, E008 legacy sigil/macro (`?x{`, `~x:y{`, `^x`, `@f`,
`@c`, `@i(`, `!E:e{`, `#T`, `%p(`, `$0`, `\x:x`, `c??a:b`, `import a=b`, `from m:a`, `&&`, `||`, `}:{`),
E009 mixed `except`/`except*`. Any other syntax error uses code E000.

## Runtime (`pydense.runtime`)

```python
def run(text: str, env: dict | None = None, *, filename: str = "<dpy>") -> dict
    # compile + exec in env (new dict if None); returns env. Python exceptions are re-raised as
    # PyDenseRuntimeError(RuntimeError) whose str() is format_compact_error(original).
def run_repl(text: str, env: dict, *, filename: str = "<dpy>") -> RunResult
    # Jupyter semantics: executes all statements; if the last statement is an expression its value is returned.
    # Captures stdout/stderr. RunResult(stdout: str, stderr: str, value: Any, value_repr: str | None, error: str | None)
def format_compact_error(exc: BaseException, filename: str | None = None) -> str
    # single line: "!Err[<frame>:L<line>]: <ExcType>(<msg>)" using the innermost frame whose filename is `filename`
    # (any .dpy-looking filename when None)
```

## CLI (`pydense`)

```
pydense encode  FILE.py  [-o OUT.dpy] [--mode full|nodoc|stripped] [--pretty]   (FILE may be - for stdin)
pydense decode  FILE.dpy [-o OUT.py]
pydense check   FILE.dpy                       # prints diagnostics, exit 1 on error
pydense run     FILE.dpy                       # execute
pydense -c CODE                                # execute inline .dpy
pydense skill                                  # print the cheat sheet
pydense init-skill [DIR]                       # write SKILL.md, CLAUDE.md, .cursorrules, .vscode/mcp.json into DIR
pydense bench   [--corpus stdlib | --files FILE...]   # delegates to benchmarks/token_compression.py (source checkout only)
pydense mcp                                    # start the MCP server (same as pydense-mcp)
```
Entry points in pyproject: `pydense = "pydense.cli:main"`, `pydense-mcp = "pydense.mcp_server:main"`.

## MCP tools (`pydense.mcp_server`)

| tool | arguments | returns |
|---|---|---|
| `read_file_as_dpy` | `file_path: str`, `mode: "full"\|"nodoc"\|"stripped" = "full"` | the `.dpy` text (or the raw file if it already ends in `.dpy`); on error `!Err[...]`. `full` is the lossless default. `nodoc` and `stripped` are **read-only views**: they drop docstrings (and annotations), so text read with them must never be written back whole with `write_dpy_file` |
| `write_dpy_file` | `file_path: str`, `dpy_code: str`, `output_format: "py"\|"dpy"\|"both" = "py"`, `allow_docstring_loss: bool = False` | writes clean Python (ast.unparse) and/or the dense text; message with byte counts; on syntax error nothing is written and the diagnostics are returned. When the target `.py` exists and has docstrings the new code lacks (the signature of a `nodoc`/`stripped` view being written back), the write is refused with `!Err[...]` unless `allow_docstring_loss=True` |
| `execute_dpy` | `dpy_code: str`, `session_id: str = "default"`, `reset_session: bool = False` | stdout, `[stderr] ...`, `=> repr(last expression)` or `!Err[...]` compact traceback |
| `transpile_dpy` | `code: str`, `direction: "dpy_to_py"\|"py_to_dpy" = "dpy_to_py"`, `mode = "nodoc"` | converted text |
| `check_dpy` | `dpy_code: str` | diagnostics (one per line) or `OK` |
| `get_dpy_cheatsheet` | — | `pydense.CHEATSHEET` |

Both transports expose the same tool names and schemas; the stdio fallback speaks newline-delimited JSON-RPC 2.0
(`initialize`, `initialized` notification, `tools/list`, `tools/call`, `prompts/list`, `prompts/get`, `ping`).
A tool failure is a one-line `!Err[tool]: Type(msg)` text. The SDK (FastMCP) transport raises it, so the client
receives a tool error (`isError: true`) with that text; the stdio fallback returns it as the ordinary text result.
Sessions are per-process dictionaries keyed by `session_id`.
