# PyDense (`.dpy`)

**Python with five deltas, for coding agents.** PyDense is a surface syntax for Python 3.10–3.13 that removes
optional whitespace, replaces indentation with `{}` blocks, writes `self.x` as `.x`, uses `c?a:b` for the
conditional expression and shortest-form floats. Everything else, every keyword, operator, literal, import,
decorator, comprehension, pattern and f-string, is Python.

- **Lossless.** FULL mode is an exact AST bijection: `ast.dump(parse(encode(src))) == ast.dump(ast.parse(src))`
  for every module construct of Python 3.10–3.13. The test suite checks it on a stdlib corpus
  (`PYDENSE_FULL_CORPUS=1 pytest tests/test_corpus.py` sweeps the whole standard library) and with a
  hypothesmith round-trip fuzz test (`tests/test_fuzz.py`); CI runs `benchmarks/corpus_fidelity.py` on every push
  and fails below 100%.
- **Measured.** Every number below is an exact `tiktoken` count against a stated baseline. On real library code
  PyDense saves 12–16% of tokens losslessly; v0.2's "50%" came from stripping docstrings and annotations.
- **Write dense, commit clean.** The MCP server lets a model read `.py` files as `.dpy` and write `.dpy` in tool
  calls while the repository only ever contains standard Python.

Grammar: [`docs/SPEC.md`](docs/SPEC.md) (normative). API: [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).
Prior art: [`docs/PRIOR_ART.md`](docs/PRIOR_ART.md). Changes: [`CHANGELOG.md`](CHANGELOG.md).

## Before / after

Sample 1 of the benchmark suite. Python as `ast.unparse` prints it, 206 o200k tokens without the docstring
(221 with); PyDense NODOC 134 tokens, FULL 148 (`python benchmarks/token_compression.py`).

```python
import math


class RunningStats:
    """Tracks an exponential moving average and variance over a stream of readings."""

    def __init__(self, span: int = 20, min_samples: int = 5):
        self.alpha: float = 2.0 / (span + 1.0)
        self.min_samples: int = min_samples
        self.mean: float = 0.0
        self.var: float = 0.0
        self.count: int = 0

    def update(self, value: float) -> tuple[float, float]:
        self.count += 1
        if self.count == 1:
            self.mean = value
            return self.mean, 0.0
        delta = value - self.mean
        self.mean += self.alpha * delta
        self.var = (1.0 - self.alpha) * (self.var + self.alpha * (delta**2))
        deviation = math.sqrt(self.var) if self.count >= self.min_samples else 0.0
        return self.mean, deviation
```

```
import math
class RunningStats{
def __init__(span:int=20,min_samples:int=5){
.alpha:float=2./(span+1.)
.min_samples:int=min_samples
.mean:float=0.
.var:float=0.
.count:int=0}
def update(value:float)->tuple[float,float]{
.count+=1
if.count==1{
.mean=value
return.mean,0.}
delta=value-.mean
.mean+=.alpha*delta
.var=(1.-.alpha)*(.var+.alpha*delta**2)
deviation=.count>=.min_samples?math.sqrt(.var):0.
return.mean,deviation}}
```

## Measured

Counts are exact `tiktoken` (`o200k_base`; `cl100k_base` in parentheses). The baseline is
`ast.unparse(ast.parse(src))`, i.e. Python with comments and formatting already removed, which is the fair
comparison for an AST-level encoding. FULL is compared against the baseline with docstrings; NODOC and STRIPPED
against the baseline with docstrings removed, because dropping docstrings is not notation.
`benchmarks/token_compression.py` regenerates the 7-sample table; `--corpus stdlib` runs the same columns over
the stdlib files of `benchmarks/corpus_fidelity.py` on your interpreter (the 321 site-packages files are not shipped).

**7 samples** (the 5 reference samples + `textwrap.TextWrapper._wrap_chunks` + two `json.encoder` functions).
Baseline 1865 (1839) tokens with docstrings, 1550 (1530) without (`benchmarks/token_compression.py`).

| mode | o200k | reduction | cl100k | reduction | baseline |
|---|---|---|---|---|---|
| **FULL** (AST bijection) | **1559** | **−16.41%** | **1529** | **−16.86%** | with docstrings |
| **NODOC** (docstrings dropped) | **1249** | **−19.42%** | **1225** | **−19.93%** | without docstrings |
| NODOC measured against the with-doc baseline | 1249 | −33.03% | 1225 | −33.39% | docstrings are 16.9% of the baseline; the notation removes a further 19.4% of what remains |
| STRIPPED (lossy: annotations dropped too) | 1178 | −24.00% | 1158 | −24.31% | without docstrings |
| STRIPPED against the with-doc baseline | 1178 | −36.84% | 1158 | −37.03% | lossy |

**469-file corpus** (148 CPython 3.13 stdlib modules + 321 site-packages modules such as requests, urllib3, pip,
setuptools, click, httpx, werkzeug; 12,508 top-level statements), measured with this implementation
(`pydense.encode`, every file re-parsed and checked for AST equality: 469/469 in FULL and NODOC). python-minifier is
run whitespace-only (lossless, one-way) on the same files.

| corpus | baseline with doc | baseline no doc | python-minifier (vs with-doc) | **FULL** (vs with-doc) | **NODOC** (vs no-doc) | STRIPPED, lossy (vs with-doc / no-doc) |
|---|---|---|---|---|---|---|
| stdlib, 148 files, 5,510 stmts | 952,530 (944,074) | 718,852 (710,985) | 885,071 **−7.08%** (−7.41%) | 826,605 **−13.22%** (−13.59%) | 596,269 **−17.05%** (−17.58%) | 595,582 −37.47% / −17.15% (−38.00%) |
| site-packages, 321 files, 6,998 stmts | 1,253,450 (1,253,430) | 918,110 (919,705) | 1,172,830 **−6.43%** (−6.62%) | 1,113,884 **−11.13%** (−11.31%) | 781,270 **−14.90%** (−15.12%) | 702,496 −43.96% / −23.48% (−43.99%) |
| **all 469 files, 12,508 stmts** | 2,205,980 (2,197,504) | 1,636,962 (1,630,690) | 2,057,901 **−6.71%** (−6.96%) | 1,940,489 **−12.04%** (−12.29%) | 1,377,539 **−15.85%** (−16.19%) | 1,298,078 −41.16% / −20.70% (−41.41%) |

NODOC measured against the with-doc baseline on the corpus is −37.55% o200k; the docstrings themselves are 25.8% of
the baseline tokens. Implicit `self` is worth more on OO-heavy application code than on this library corpus (−18.3% NODOC was
measured on an OO-heavy stdlib subset during the grammar design).

The fixed cost is the cheat sheet (418 o200k tokens; `SKILL.md` adds a short MCP workflow section for a total of about 700); at the corpus NODOC rate it pays for itself after about 2.6k baseline tokens read or written, at the FULL rate after about 3.5k.

## Install

```bash
pip install pydense           # once published: zero runtime dependencies, Python 3.10-3.13
```

From a checkout (needed for `pydense bench`, `benchmarks/` and `legacy/`, which are not part of the wheel):

```bash
git clone https://github.com/iced-compiler/pydense
cd pydense
pip install -e .              # zero runtime dependencies, Python 3.10-3.13
pip install -e ".[mcp]"       # FastMCP transport (a zero-dependency stdio JSON-RPC fallback is built in)
pip install -e ".[bench]"     # tiktoken + python-minifier for the benchmarks
pip install -e ".[dev]"       # pytest, ruff, mypy, hypothesis, hypothesmith + the above
```

## CLI

```bash
pydense encode  module.py  [-o module.dpy] [--mode full|nodoc|stripped] [--pretty]   # - reads stdin
pydense decode  module.dpy [-o module.py]      # clean Python (ast.unparse)
pydense check   module.dpy                     # E/W diagnostics with line:col and a hint; exit 1 on error
pydense run     module.dpy                     # execute (check and run also read - for stdin)
pydense -c 'def f(n){return n<2?n:f(n-1)+f(n-2)}
print([f(i) for i in range(10)])'
pydense skill [--workflow]                     # print the cheat sheet (+ the MCP agent workflow)
pydense init-skill [DIR]                       # SKILL.md, CLAUDE.md, .cursorrules, .vscode/mcp.json, .cursor/mcp.json
pydense bench   [--corpus stdlib | --files FILE...]   # benchmarks/token_compression.py (source checkout only)
pydense mcp                                    # start the MCP server (same as pydense-mcp)
```

`encode` on a `.dpy` file or `decode` on a `.py` file fails with a hint pointing at the other command. Exit codes:
0 success, 1 diagnostics or a failed run, 2 usage error.

```python
import pydense

dpy = pydense.encode(
    source, mode="full"
)  # str | ast.Module -> canonical .dpy text (Mode.FULL/NODOC/STRIPPED)
tree = pydense.parse(
    dpy
)  # .dpy -> ast.Module, positions filled in (PyDenseSyntaxError on bad input)
py = pydense.decode(dpy)  # .dpy -> Python source (ast.unparse)
code = pydense.compile(dpy, "<dpy>")  # code object; tracebacks point at .dpy line numbers
pydense.check(
    dpy
)  # [Diagnostic(code, message, lineno, col, severity, hint)]: first error, then warnings
pydense.lint(dpy)  # warnings only (W001-W005)
env = pydense.run(
    dpy
)  # exec in a fresh namespace; PyDenseRuntimeError with "!Err[fn:L3]: ValueError(msg)"
result = pydense.run_repl(
    dpy, env
)  # Jupyter semantics: RunResult(stdout, stderr, value, value_repr, error)
```

## MCP: write dense, commit clean

The server (`python -m pydense.mcp_server`, or `pydense-mcp`) exposes six tools. The model never sees or writes
Python formatting; the repository never contains `.dpy`.

| tool | what it does |
|---|---|
| `read_file_as_dpy(file_path, mode="full")` | returns a `.py` file as `.dpy` text (a `.dpy` file is returned as is). `full` is lossless and is the default; `nodoc` and `stripped` are read-only views: they drop docstrings (and annotations), so a module read that way must never be written back whole |
| `write_dpy_file(file_path, dpy_code, output_format="py", allow_docstring_loss=False)` | parses the dense text and writes clean Python (`ast.unparse`); on a syntax error nothing is written and the diagnostics come back. Overwriting an existing `.py` whose docstrings the new text does not contain is refused unless `allow_docstring_loss=True` |
| `execute_dpy(dpy_code, session_id="default", reset_session=False)` | stateful REPL; stdout, `[stderr]`, `=> repr(last expression)` or a one-line `!Err[...]` traceback |
| `transpile_dpy(code, direction="dpy_to_py", mode="nodoc")` | either direction, no disk I/O |
| `check_dpy(dpy_code)` | diagnostics one per line, or `OK` |
| `get_dpy_cheatsheet()` | the cheat sheet (418 o200k tokens) |

Every tool returns a one-line `!Err[tool]: Type(msg)` on failure; the SDK (FastMCP) transport raises these as tool
errors (`isError`), the stdio fallback returns the same text as the result.

Models do not emit compact code unprompted: the instruction has to be in the prompt. `pydense init-skill .` sets a
project up in one step: it writes `SKILL.md` (the cheat sheet plus the agent workflow), merges a marked section into
`CLAUDE.md` and `.cursorrules` (existing content is kept, and a rerun replaces only that section), and merges a
`pydense` server entry into `.vscode/mcp.json` and `.cursor/mcp.json` (other servers in those files are kept). An
edited `SKILL.md` is never overwritten. The command is `pydense-mcp` when it is on `PATH`, otherwise the running
interpreter with `-m pydense.mcp_server`; the resolved command and the Claude Code line are printed.

**Claude Code**

```bash
claude mcp add pydense -- pydense-mcp
```

**Cursor** (`.cursor/mcp.json`)

```json
{ "mcpServers": { "pydense": { "command": "pydense-mcp", "args": [] } } }
```

**VS Code** (`.vscode/mcp.json`)

```json
{ "servers": { "pydense": { "type": "stdio", "command": "pydense-mcp", "args": [] } } }
```

If `pydense-mcp` is not on `PATH`, use the interpreter that has pydense installed: `python -m pydense.mcp_server`.
`pydense-mcp --stdio-fallback` serves plain newline-delimited JSON-RPC when the `mcp` package is not installed, and
`pydense-mcp --self-test` runs every tool once.

## Language reference

The full Rosetta stone is `docs/SPEC.md` §14; this is the part a writer needs. Spaces are written only between two
word characters (`return x`, `a in b`, `async def`), so `return.mean`, `if.count==1{`, `return'x'` and `)as f{`
are all canonical. `--pretty` adds a space between a keyword and a following `.` or quote (+0.6% tokens on the
samples, +0.5% on the corpus).

| Python | PyDense (canonical) | o200k tokens |
|---|---|---|
| `x = 1` / `a = b = c` / `x: int = 5` | `x=1` / `a=b=c` / `x:int=5` | 4→3 / 5→3 / 6→4 |
| `if a:` ⏎ `x = 1` ⏎ `elif b:` ⏎ `x = 2` ⏎ `else:` ⏎ `x = 3` | `if a{` ⏎ `x=1}elif b{` ⏎ `x=2}else{` ⏎ `x=3}` | 25→19 |
| `for i, v in enumerate(xs):` ⏎ `if v < 0: continue` ⏎ `total += v` ⏎ `else:` ⏎ `done = True` | `for i,v in enumerate(xs){` ⏎ `if v<0{` ⏎ `continue}` ⏎ `total+=v}else{` ⏎ `done=True}` | 29→22 |
| `while chunk := f.read(8):` ⏎ `buf.append(chunk)` | `while chunk:=f.read(8){` ⏎ `buf.append(chunk)}` | no parentheses needed |
| `try:` … `except (ValueError, TypeError) as e:` … `else:` … `finally:` … | `try{` ⏎ `risky()}except(ValueError,TypeError)as e{` ⏎ `log(e)` ⏎ `raise}else{` ⏎ `ok=True}finally{` ⏎ `close()}` | 35→28 |
| `with open(p) as f, lock:` ⏎ `data = f.read()` | `with open(p)as f,lock{` ⏎ `data=f.read()}` | 15→13 |
| `class A:` ⏎ `def __init__(self, a, b=1):` ⏎ `self.a = a; self.b = b` ⏎ `def total(self):` ⏎ `return self.a + self.b` | `class A{` ⏎ `def __init__(a,b=1){` ⏎ `.a=a` ⏎ `.b=b}` ⏎ `def total(){` ⏎ `return.a+.b}}` | 40→26 |
| `@classmethod` ⏎ `def make(cls, x): return cls(x)` | `@classmethod def make(x){` ⏎ `return cls(x)}` | 14→10 |
| `@property` ⏎ `@abstractmethod` ⏎ `def p(self): return self._p` | `@property@abstractmethod def p(){` ⏎ `return._p}` | |
| `def f(this, x): return this.x` (in a class) | `def!f(this,x){` ⏎ `return this.x}` | 10→10 |
| `def f(a, b=1, /, c=2, *d, e, f=3, **g) -> None: pass` | `def f(a,b=1,/,c=2,*d,e,f=3,**g)->None{}` | 31→23 |
| `async def main():` ⏎ `async with sess as s:` ⏎ `async for x in s.stream():` ⏎ `await handle(x)` | `async def main(){` ⏎ `async with sess as s{` ⏎ `async for x in s.stream(){` ⏎ `await handle(x)}}}` | 24→22 |
| `y = a if c else b` ; `y = a if c else (d if e else f)` | `y=c?a:b` ; `y=c?a:e?d:f` | 7→4 |
| `f(lambda: 1, key=lambda x: x[1])` | `f(lambda:1,key=lambda x:x[1])` | 14→11 |
| `[x * 2 for x in it if x > 0 if x < 9]` ; `{k: v for k, v in d.items() if v is not None}` | `[x*2 for x in it if x>0 if x<9]` ; `{k:v for k,v in d.items()if v is not None}` | 22→18 |
| `match cmd.split():` ⏎ `case [action]: go(action)` ⏎ `case {"k": v, **rest}: use(v)` ⏎ `case str() as s: text(s)` ⏎ `case _: pass` | `match cmd.split(){` ⏎ `case[action]{` ⏎ `go(action)}` ⏎ `case {'k':v,**rest}{` ⏎ `use(v)}` ⏎ `case str()as s{` ⏎ `text(s)}` ⏎ `case _{}}` | |
| `type Alias[T: int, *Ts, **P] = dict[T, P]` ; `class Box[T](Generic[T]):` | `type Alias[T:int,*Ts,**P]=dict[T,P]` ; `class Box[T](Generic[T]){` | |
| `1j, 0x1F, 1_000_000, 1e-5, 0.5, 100.0, -0.5` | `1j,31,1000000,1e-05,.5,100.,-.5` | |
| `f"{self.name}: {a if c else b}"` | `f'{.name}: {(c?a:b)}'` | ternary parenthesised in a field |
| `if x in {1, 2}: pass` | `if x in {1,2}{}` | 12→9; a `{` after a complete header is always the block |

Input is lenient: `a if c else b`, `lambda`, explicit `self`/`cls`, `self.x`, `1.0`, `{pass}`, `;`, `if x:{`,
`else:{`, comments and `\`-continuation all parse to the same AST. Output is canonical, so
`encode(decode(encode(x))) == encode(x)`.

### The receiver rule (`docs/SPEC.md` §7)

1. A `def` is a method iff its nearest enclosing `def`/`lambda`/`class` scope is a `class` (`if`/`try`/`with` blocks are transparent).
2. The receiver is `cls` under a bare `@classmethod`, none under a bare `@staticmethod`, otherwise `self`.
3. Parser: prepend the receiver to the written parameters unless the def is `def!` or the first written parameter is literally `self` or `cls`.
4. Emitter: drop the first parameter iff it is the receiver name with no annotation or default, is not the sole positional-only parameter, and the next parameter is not `self`/`cls`.
5. Otherwise write the parameters verbatim when the parser would not inject (`def __new__(cls,*a)`, `def m(self:T)`, `def m(self,/)`), and `def!` when it would (`def!f(this,x)`, `def!m()`).
6. On 10,116 corpus methods: dropped 94.0%, implicit `cls` 2.9%, verbatim 1.9%, `@staticmethod` 0.7%, `def!` 0.5%.

## How it works

```
Python source ──ast.parse──▶ ast.Module ──Emitter──▶ .dpy text      (pydense.encode)
.dpy text ──Lexer──▶ tokens ──Parser──▶ ast.Module ──ast.unparse──▶ Python   (pydense.parse / decode)
```

- `pydense/lexer.py` and `pydense/strings.py` tokenize `.dpy` text. Whitespace and comments are dropped; a
  newline token is produced only at bracket depth 0, and string literals, PEP 701 f-strings included, are single
  tokens whose replacement fields are parsed later as PyDense expressions.
- `pydense/parser.py` is a hand-written recursive-descent parser that builds `ast` nodes directly, with at most two
  tokens of lookahead (the `match` soft keyword uses the same bounded speculation as CPython). It fills in line and
  column positions, so `pydense.compile` gives tracebacks on `.dpy` lines, applies the receiver rule, and refuses
  the spellings CPython refuses (argument order, bare `*`, deleting a starred name, a lone `}` in an f-string).
- `pydense/emitter.py` subclasses `ast._Unparser`, so operator precedence and string quoting are inherited from
  CPython; it adds the layout, spacing, receiver and ternary rules and the three modes. The output is a fixed point:
  `encode(decode(encode(x))) == encode(x)`.
- `pydense/rules.py` holds the receiver rule and the v0.2 macro names shared by lexer, parser and emitter;
  `pydense/errors.py` defines `PyDenseSyntaxError` (code, hint, line, column) and `Diagnostic`.
- `pydense/lint.py` provides `check` (first syntax error, then warnings, never raises) and `lint` (`W001`-`W005`:
  a split call chain that would read as `self.x()`, a receiver-like first parameter, a continuation keyword after a
  display, stray `;`, a statement starting with an operator).
- `pydense/runtime.py` runs `.dpy` code with one-line compact tracebacks; `run_repl` has Jupyter semantics and
  isolates `stdin`, `SystemExit` and `KeyboardInterrupt` so a tool call can never take the MCP server down.
- `pydense/mcp_server.py` registers the six tools with the `mcp` SDK when it is installed (tool failures surface as
  tool errors carrying the diagnostics) and otherwise serves a zero-dependency stdio JSON-RPC transport.

Deeply nested input is handled with a raised recursion budget and reported as `E000` rather than a `RecursionError`.
Comments are accepted on input but, as with `ast.unparse`, not preserved.

## Modes

| mode | annotations | docstrings | lossless |
|---|---|---|---|
| `full` (default) | kept | kept | yes: `ast.parse(src)` exactly |
| `nodoc` | kept | dropped | by exactly the docstring `Expr` nodes of Module/ClassDef/FunctionDef |
| `stripped` | parameter/return annotations dropped; `x:T=v` → `x=v`; bare `x:T` kept | dropped | **no** |

Modes change which nodes are present, never how a node is spelled.

## Guarantees, and what is not preserved

- FULL: `ast.dump(parse(encode(src))) == ast.dump(ast.parse(src))` for every `ast` node class of Python 3.10–3.13
  (`docs/SPEC.md` §9). NODOC and STRIPPED are equal to the mode-adjusted reference.
- Canonical form is a fixed point; parsing is deterministic recursive descent with at most two tokens of lookahead
  except the `match` soft keyword, which uses the same bounded speculation as CPython.
- Errors `E001`–`E009` carry `line:col` and a one-line hint; `E001` lists the position of every unmatched `{`, the
  dominant generation failure. Lint `W001`–`W005` flags split call chains, receiver-like parameter names and
  non-canonical separators.
- **Not preserved**, exactly as with `ast.unparse`: comments, blank lines and formatting, `# type:` comments,
  non-canonical parentheses, and literal spelling the AST does not keep (`0x1F` → `31`, `1_000` → `1000`, quote and
  escape style, implicit string concatenation, the `{x=}` f-string text). 3.14 t-strings are out of scope.

## Fidelity: v1.0 vs v0.2

v0.2 (`legacy/`) was a sigil dialect (`@c`, `@f`, `?c{}:{}`, `~x:it{}`, `^x`, `&&`, `\a:b`, `$0`, `#np`, `%p`).
On 109 CPython stdlib files (4,630 top-level statements) it reached 73.6% round-trip fidelity and 37% o200k
reduction with annotations stripped. The sigils were measured token-neutral or negative: a Python keyword is one
BPE token whose following space fuses into the next identifier, so `def update(` and `@f update(` both cost 3,
`!isinstance(` costs one more than `not isinstance(`, the macros cost +35 tokens on the samples and the `\` lambda
saved 0 in 8 of 8 contexts (`docs/SPEC.md` §12.3). v1.0 is 100% fidelity on 469/469 files in FULL and NODOC,
−15.85% NODOC on the same kind of corpus, and its cheat sheet is 418 tokens where v0.2's SKILL.md was 1279.
`benchmarks/corpus_fidelity.py --backend legacy` reproduces the v0.2 figures; the default backend is the gate CI
runs on every push (`--fail-under 100`).

## Prior art

- **python-minifier** (dflook): AST-based, one-way, keeps newline+indent and `self`; whitespace-only mode measures
  −6.71% on the 469-file `ast.unparse` corpus (its published −21% is against raw source with comments).
- **SimPy** (Sun et al., ISSTA 2024): AST-identical Python with placeholder terminals; 10.4% on GPT-4's tokenizer
  but requires 78 new vocabulary tokens and continued pre-training.
- **Token Sugar** (ASE 2025): 799 mined idiom tokens, 12.9–15.1% saving after training; untrained GPT-4.1 Pass@1
  falls from 94.5% to 51.2% on sugared code, the reason PyDense keeps Python's own keywords.
- **TOON**: lossless LLM-side encoding of JSON with per-dataset tables that include the cases where it loses and
  structural guardrails against truncation; PyDense adopts the same transport-layer positioning and brace balance
  as the guardrail.

Details and sources: [`docs/PRIOR_ART.md`](docs/PRIOR_ART.md).

## Development

```bash
pip install -e ".[dev]"
ruff check . && mypy pydense && pytest               # ~6,700 tests: batteries, lenient/rejected input, lint, CLI, MCP, fuzz
PYDENSE_FULL_CORPUS=1 pytest tests/test_corpus.py     # whole standard library, whole-file round trip
python benchmarks/corpus_fidelity.py --mode full      # stdlib corpus, 100% required (the CI gate)
python benchmarks/token_compression.py --json out.json  # the 7-sample tables in SPEC section 12.1
```

MIT License. See [`docs/SPEC.md`](docs/SPEC.md) for the grammar, §17 for the conformance gates.
