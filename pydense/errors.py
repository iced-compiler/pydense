"""Diagnostics and the PyDense syntax error type."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Diagnostic:
    """One parser error or lint warning, with a 1-based line and 0-based column."""

    code: str
    message: str
    lineno: int
    col: int
    severity: str  # "error" | "warning"
    hint: str = ""

    def __str__(self) -> str:
        text = f"{self.code} {self.lineno}:{self.col}: {self.message}"
        if self.hint:
            text += f" (hint: {self.hint})"
        return text


class PyDenseSyntaxError(SyntaxError):
    """Raised by :func:`pydense.parse` for malformed .dpy text.

    ``code`` is one of E000-E009 (see docs/SPEC.md section 13); ``hint`` is a one-line fix
    suggestion.
    ``lineno`` is 1-based and ``offset`` is 1-based like :class:`SyntaxError`; ``col`` is 0-based.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "E000",
        lineno: int = 1,
        col: int = 0,
        filename: str = "<dpy>",
        text: str | None = None,
        hint: str = "",
    ) -> None:
        super().__init__(message, (filename, lineno, col + 1, text))
        self.code = code
        self.hint = hint
        self.col = col

    def __str__(self) -> str:
        text = f"{self.code} {self.lineno}:{self.col}: {self.msg}"
        if self.hint:
            text += f" (hint: {self.hint})"
        return text

    def to_diagnostic(self) -> Diagnostic:
        return Diagnostic(self.code, self.msg, self.lineno or 1, self.col, "error", self.hint)


class PyDenseRuntimeError(RuntimeError):
    """Raised by :func:`pydense.runtime.run` when the executed program raises.

    ``str(err)`` is the single-line compact traceback; ``original`` is the underlying exception.
    """

    def __init__(self, message: str, original: BaseException | None = None) -> None:
        super().__init__(message)
        self.original = original


def with_deep_recursion(fn: Callable[[], Any], filename: str) -> Any:
    """Run a recursive parser/emitter with a recursion budget matching CPython's nesting limit."""
    limit = sys.getrecursionlimit()
    if limit < 8000:
        sys.setrecursionlimit(8000)
    try:
        return fn()
    except RecursionError:
        raise PyDenseSyntaxError(
            "too many nested brackets or operators",
            filename=filename,
            hint="CPython itself rejects nesting this deep; split the expression",
        ) from None
    finally:
        sys.setrecursionlimit(limit)
