"""PyDense (.dpy): a whitespace-free, brace-blocked, AST-bijective surface syntax for Python.

>>> import pydense
>>> dense = pydense.encode("class A:\\n    def f(self, x):\\n        return self.x + x\\n")
>>> dense
'class A{\\ndef f(x){\\nreturn.x+x}}'
>>> pydense.decode(dense)
'class A:\\n\\n    def f(self, x):\\n        return self.x + x\\n'
"""

from __future__ import annotations

import ast as _ast
import builtins as _builtins
import types as _types

from ._version import __version__
from .emitter import Emitter, Mode, encode
from .errors import Diagnostic, PyDenseRuntimeError, PyDenseSyntaxError, with_deep_recursion
from .lint import check, lint
from .parser import Parser, parse
from .skill import CHEATSHEET


def decode(text: str, *, filename: str = "<dpy>") -> str:
    """.dpy text -> standard Python source (``ast.unparse``), with a trailing newline."""
    tree = parse(text, filename=filename)
    return with_deep_recursion(lambda: _ast.unparse(tree), filename) + "\n"


def compile(text: str, filename: str = "<dpy>", mode: str = "exec") -> _types.CodeType:  # noqa: A001
    """parse + ``builtins.compile`` so tracebacks point at .dpy line numbers."""
    tree = parse(text, filename=filename)
    try:
        return _compile_tree(tree, filename, mode)
    except (
        SyntaxError
    ) as exc:  # CPython's own checks (duplicate argument, nonlocal at module level, ...)
        if isinstance(exc, PyDenseSyntaxError):
            raise
        raise PyDenseSyntaxError(
            exc.msg,
            filename=filename,
            lineno=exc.lineno or 1,
            col=(exc.offset or 1) - 1,
            hint="CPython rejected the program",
        ) from None


def _compile_tree(tree: _ast.Module, filename: str, mode: str) -> _types.CodeType:
    if mode == "eval":
        if len(tree.body) != 1 or not isinstance(tree.body[0], _ast.Expr):
            raise PyDenseSyntaxError("eval mode needs a single expression", filename=filename)
        expr = _ast.Expression(body=tree.body[0].value)
        _ast.fix_missing_locations(expr)
        return _builtins.compile(expr, filename, "eval")
    return _builtins.compile(tree, filename, mode)


from .runtime import RunResult, format_compact_error, run, run_repl  # noqa: E402  (needs compile/parse)

__all__ = [
    "CHEATSHEET",
    "Diagnostic",
    "Emitter",
    "Mode",
    "Parser",
    "PyDenseRuntimeError",
    "PyDenseSyntaxError",
    "RunResult",
    "__version__",
    "check",
    "decode",
    "encode",
    "format_compact_error",
    "lint",
    "parse",
    "run",
    "run_repl",
]
# `compile` stays available as pydense.compile but is deliberately not star-exported: it would
# shadow the builtin under `from pydense import *`.
