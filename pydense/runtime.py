"""Execution helpers: ``run``, Jupyter-style ``run_repl`` and single-line compact tracebacks.

The parser and compiler are imported lazily inside the functions so that ``pydense/__init__.py`` can
re-export :func:`run` and :func:`format_compact_error` from here without a circular import.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import io
import os
import sys
from dataclasses import dataclass
from typing import Any

try:
    from .errors import PyDenseRuntimeError
except ImportError:  # pragma: no cover - only while the core is being written

    class PyDenseRuntimeError(RuntimeError):  # type: ignore[no-redef]
        """Raised by :func:`run` when the executed program raises."""

        def __init__(self, message: str, original: BaseException | None = None) -> None:
            super().__init__(message)
            self.original = original


__all__ = ["PyDenseRuntimeError", "RunResult", "format_compact_error", "run", "run_repl"]


@dataclass
class RunResult:
    """Outcome of :func:`run_repl`.

    ``value`` is the value of a trailing expression statement (``None`` otherwise); ``value_repr``
    is its ``repr`` unless the value is ``None`` (Jupyter does not display ``None``). ``error`` is a
    compact single-line traceback, or ``None`` when the code ran to completion.
    """

    stdout: str
    stderr: str
    value: Any
    value_repr: str | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None


def _new_env(env: dict | None) -> dict:
    if env is None:
        return {"__name__": "__main__"}
    return env


def _is_dpy_filename(name: str) -> bool:
    """Heuristic used when :func:`format_compact_error` is not told the filename."""
    if name.endswith(".dpy"):
        return True
    return (
        name.startswith("<")
        and name.endswith(">")
        and name
        not in {
            "<module>",
            "<string>",
            "<stdin>",
            "<frozen importlib._bootstrap>",
        }
        and not name.startswith("<frozen")
    )


def _one_line(text: str) -> str:
    return " ".join(text.splitlines()) if "\n" in text or "\r" in text else text


def format_compact_error(exc: BaseException, filename: str | None = None) -> str:
    """Return ``"!Err[<frame>:L<line>]: <ExcType>(<msg>)"`` for ``exc``.

    The frame is the innermost traceback entry whose code filename is the ``.dpy`` filename
    (``filename`` if given, otherwise any ``*.dpy`` / ``<...>`` pseudo-file); when none matches, the
    last frame is used.
    A :class:`SyntaxError` carries no useful frame, so its own filename and line are reported.
    """
    exc_type = type(exc).__name__
    msg = _one_line(str(exc))
    if isinstance(exc, SyntaxError) and exc.lineno:
        where = exc.filename or filename or "<dpy>"
        return f"!Err[{where}:L{exc.lineno}]: {exc_type}({msg})"

    chosen: tuple[str, int] | None = None
    last: tuple[str, int] | None = None
    own_dir = os.path.dirname(os.path.abspath(__file__))
    tb = exc.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        if not os.path.abspath(code.co_filename).startswith(own_dir):
            last = (code.co_name, tb.tb_lineno)  # pydense's own frames are never the error site
        matches = code.co_filename == filename if filename else _is_dpy_filename(code.co_filename)
        if matches:
            chosen = (code.co_name, tb.tb_lineno)
        tb = tb.tb_next
    frame = chosen or last
    if frame is None:
        return f"!Err: {exc_type}({msg})"
    return f"!Err[{frame[0]}:L{frame[1]}]: {exc_type}({msg})"


def run(text: str, env: dict | None = None, *, filename: str = "<dpy>") -> dict:
    """Compile ``text`` (PyDense) and ``exec`` it in ``env`` (a new ``__main__`` dict if ``None``).

    Returns ``env``. Syntax errors propagate as :class:`pydense.PyDenseSyntaxError`; an exception
    raised by the program is re-raised as :class:`PyDenseRuntimeError` whose ``str`` is
    :func:`format_compact_error`.
    ``SystemExit`` and ``KeyboardInterrupt`` propagate unchanged.
    """
    from . import compile as dpy_compile  # lazy: avoids a circular import with pydense/__init__.py

    env = _new_env(env)
    code = dpy_compile(text, filename, "exec")
    try:
        exec(code, env)
    except Exception as exc:
        raise PyDenseRuntimeError(format_compact_error(exc, filename), exc) from exc
    return env


def run_repl(text: str, env: dict, *, filename: str = "<dpy>") -> RunResult:
    """Execute ``text`` with Jupyter semantics and capture its output.

    Every statement is executed in ``env``; when the last statement is an expression, its value is
    evaluated and returned as ``value`` (``value_repr`` is ``repr(value)`` unless the value is
    ``None``). ``stdout`` and ``stderr`` are captured via :mod:`contextlib`. Errors (syntax or
    runtime) never raise: they fill ``error``.
    """
    from . import parse  # lazy: avoids a circular import with pydense/__init__.py

    out, err = io.StringIO(), io.StringIO()
    value: Any = None
    value_repr: str | None = None
    error: str | None = None
    try:
        tree = parse(text, filename=filename)
    except SyntaxError as exc:
        return RunResult("", "", None, None, format_compact_error(exc, filename))

    last_expr: ast.Expr | None = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last_expr = tree.body[-1]
        tree = ast.Module(body=tree.body[:-1], type_ignores=[])

    saved_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO()  # input() must never read the protocol stream
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if tree.body:
                exec(builtins.compile(tree, filename, "exec"), env)
            if last_expr is not None:
                expression = ast.Expression(body=last_expr.value)
                ast.fix_missing_locations(expression)
                value = eval(builtins.compile(expression, filename, "eval"), env)
                if value is not None:
                    value_repr = repr(value)
    except BaseException as exc:  # noqa: BLE001 - SystemExit/KeyboardInterrupt must not kill the host
        error = format_compact_error(exc, filename)
        value = None
        value_repr = None
    finally:
        sys.stdin = saved_stdin
    return RunResult(out.getvalue(), err.getvalue(), value, value_repr, error)
