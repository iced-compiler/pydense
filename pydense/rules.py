"""Grammar constants shared by the lexer, parser and emitter."""

from __future__ import annotations

import ast

RECEIVER_NAMES = ("self", "cls")
# Receiver-like first-parameter names: lint W002 fires when `self` would be inserted before one.
RECEIVER_ALIASES = frozenset(
    {"this", "mcs", "metacls", "meta", "klass", "kls", "that", "me", "obj"}
)

# v0.2 macros: `#` followed by one of these is rejected with E008 instead of read as a comment.
LEGACY_MACRO_NAMES = (
    "T",
    "F",
    "N",
    "np",
    "pd",
    "sp",
    "os",
    "sys",
    "js",
    "re",
    "m",
    "dt",
    "pl",
    "as",
    "dc",
)
LEGACY_MACRO_ALTERNATION = "|".join(LEGACY_MACRO_NAMES)
LEGACY_MACRO_HINT = "write True/False/None or the module name; '#' starts a comment"
E008_HINT = (
    "PyDense uses Python keywords: write if/for/while/return/def/class/__init__/except/lambda"
)


def receiver_for(decorators: list[ast.expr]) -> str | None:
    """SPEC section 7: `cls` under a bare @classmethod, none under @staticmethod, else `self`."""
    for d in decorators:
        if isinstance(d, ast.Name) and d.id == "staticmethod":
            return None
    for d in decorators:
        if isinstance(d, ast.Name) and d.id == "classmethod":
            return "cls"
    return "self"
