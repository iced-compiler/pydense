"""Lint (W001-W005) and `check` (first syntax error + warnings) for .dpy text — SPEC section 13."""

from __future__ import annotations

import ast

from .errors import Diagnostic, PyDenseSyntaxError, with_deep_recursion
from .parser import Parser, parse_with_warnings


def lint(tree_or_text: ast.Module | str, *, filename: str = "<dpy>") -> list[Diagnostic]:
    """Return the W-series warnings for .dpy text.  Raises PyDenseSyntaxError on a syntax error.

    An ``ast.Module`` carries no token information, so only text input can produce warnings;
    a module argument returns an empty list.
    """
    if isinstance(tree_or_text, ast.AST):
        return []
    _, warnings = parse_with_warnings(tree_or_text, filename=filename)
    return warnings


def check(text: str, *, filename: str = "<dpy>") -> list[Diagnostic]:
    """Parse and lint; never raises.

    At most one error (the first), then warnings, sorted by position.
    """
    try:
        parser = Parser(text, filename, collect_warnings=True)
    except PyDenseSyntaxError as exc:  # lexical error
        return [exc.to_diagnostic()]
    try:
        with_deep_recursion(parser.parse_module, filename)
    except PyDenseSyntaxError as exc:
        warnings = sorted(parser.warnings, key=lambda d: (d.lineno, d.col))
        return [exc.to_diagnostic(), *warnings]
    return sorted(parser.warnings, key=lambda d: (d.lineno, d.col))
