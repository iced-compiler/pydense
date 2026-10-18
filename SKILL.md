---
name: pydense
description: Read and write PyDense (.dpy), lossless brace-blocked Python, via the MCP tools.
---

# PyDense (.dpy) — how to write it

PyDense is Python with whitespace removed. Keep every keyword, operator, literal, import, decorator, comprehension, pattern and f-string exactly as in Python. Only five things change:

1. **Blocks** are `{...}`, one statement per line (or `;`); after `}` only `elif`/`else`/`except`/`finally`; empty body `{}`.
   `if c{a}elif d{b}else{e}` `for x in y{}` `while c{}` `try{}except E as e{}finally{}` `with a as b{}` `def f(x)->T{}` `class A(B){}` `match x{case p{}}`
2. **No optional spaces**: `x=1` `f(a,b)` `{k:v}` `x:int=5`. One space only between two words (`return x`, `a in b`).
3. **`.x` means `self.x`**, and methods omit the receiver: `def update(value){.count+=1}`. `@classmethod def make(x)` gets `cls`; `@staticmethod` is untouched. Explicit `self`/`cls` is fine (`def __new__(cls,*a)` stays). First parameter not a receiver, or none: `def!f(this,x){}`.
4. **Ternary** `c?a:b` = `a if c else b` (Python form accepted). Parenthesize it in a slice bound, dict key or f-string field: `f'{(c?a:b)}'`.
5. **Floats** shortest: `1.` `.5` `0.` (`1.0` accepted).

Traps: decorators and `def` on one line (`@a@b def f(){`); a decorator that is not a `name.attr(args)` chain is `@(expr)`. Never split a call chain across lines without parentheses. Balance every `{`.

## Agent workflow (MCP server `pydense-mcp`)

Models do not emit compact code unprompted: the instruction must be explicit, e.g. "write PyDense (.dpy) in tool calls".
- `check_dpy(dpy_code)` before writing; fix every diagnostic (line:col + hint), then retry.
- `write_dpy_file(file_path, dpy_code, output_format="py")`: you emit dense text, disk gets clean Python to commit. It refuses to drop every docstring of an existing .py unless `allow_docstring_loss=true`.
- `read_file_as_dpy(file_path, mode="full")` instead of a plain read for large .py modules. `nodoc`/`stripped` are cheaper read-only views: never write one back whole (its docstrings are gone).
- `execute_dpy(dpy_code, session_id)`: stateful REPL check; the last expression is returned like Jupyter.
- `transpile_dpy(code, direction)` converts either way; `get_dpy_cheatsheet()` reprints this sheet.
- Without MCP: `pydense check f.dpy`, `pydense decode f.dpy -o f.py`, `pydense encode f.py --mode nodoc`.
