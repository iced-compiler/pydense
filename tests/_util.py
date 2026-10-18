"""Shared helpers for the PyDense test suite.

* ``_Normalizer`` / ``reference_dump`` build the mode-adjusted reference AST (SPEC §11) that
  ``parse(encode(src, mode))`` must reproduce exactly.  The class is a copy of
  ``benchmarks/corpus_fidelity._Normalizer`` with three SPEC §11 corrections:
    - a docstring-only *module* becomes an empty body (``[]``), not ``[Pass]``
      (only def/class bodies fall back to ``[Pass]``);
    - in STRIPPED mode a bare ``x: T`` is kept verbatim (deleting it would delete a statement);
    - ``Constant.kind`` (the ``u''`` prefix) is kept: SPEC §9.2 says it is represented.
* ``load_batteries`` loads every ``tests/batteries/*.py`` module's ``SNIPPETS``.
* ``tok_fields`` reads a lexer token without depending on the Token attribute names, which the
  API contract leaves to the implementation.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
BATTERIES_DIR = TESTS_DIR / "batteries"
SAMPLES_DIR = TESTS_DIR / "samples"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODES = ("full", "nodoc", "stripped")
PY = sys.version_info[:2]


# --------------------------------------------------------------------------- normaliser


class _Normalizer(ast.NodeTransformer):
    """Removes exactly the information a mode is allowed to drop (SPEC §11)."""

    def __init__(self, strip_types: bool, strip_docstrings: bool) -> None:
        self.strip_types = strip_types
        self.strip_docstrings = strip_docstrings

    @staticmethod
    def _has_docstring(body: list[ast.stmt]) -> bool:
        return bool(
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        )

    def _strip_body_docstring(self, body: list[ast.stmt], *, module: bool) -> list[ast.stmt]:
        if self.strip_docstrings and self._has_docstring(body):
            body = body[1:]
            if not body and not module:
                body = [ast.Pass()]
        return body

    def visit_Module(self, node: ast.Module) -> ast.AST:
        node.type_ignores = []
        node.body = self._strip_body_docstring(node.body, module=True)
        self.generic_visit(node)
        return node

    def _visit_def(self, node: Any) -> ast.AST:
        node.body = self._strip_body_docstring(node.body, module=False)
        if self.strip_types:
            node.returns = None
        node.type_comment = None
        self.generic_visit(node)
        return node

    visit_FunctionDef = _visit_def
    visit_AsyncFunctionDef = _visit_def

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        node.body = self._strip_body_docstring(node.body, module=False)
        self.generic_visit(node)
        return node

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        # lambda parameters never carry annotations; nothing to strip
        self.generic_visit(node)
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        if self.strip_types:
            node.annotation = None
        node.type_comment = None
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        if self.strip_types and node.value is not None:
            return ast.Assign(
                targets=[node.target], value=self.visit(node.value), type_comment=None
            )
        self.generic_visit(node)
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        node.type_comment = None
        self.generic_visit(node)
        return node

    def visit_For(self, node: ast.For) -> ast.AST:
        node.type_comment = None
        self.generic_visit(node)
        return node

    visit_AsyncFor = visit_For

    def visit_With(self, node: ast.With) -> ast.AST:
        node.type_comment = None
        self.generic_visit(node)
        return node

    visit_AsyncWith = visit_With


def mode_flags(mode: str) -> tuple[bool, bool]:
    """(strip_types, strip_docstrings) for a mode name."""
    mode = str(getattr(mode, "value", mode)).lower()
    if mode == "full":
        return False, False
    if mode == "nodoc":
        return False, True
    if mode == "stripped":
        return True, True
    raise ValueError(f"unknown mode {mode!r}")


def normalized_dump(tree: ast.Module, mode: str) -> str:
    strip_types, strip_docstrings = mode_flags(mode)
    tree = _Normalizer(strip_types, strip_docstrings).visit(tree)
    ast.fix_missing_locations(tree)
    return ast.dump(tree, include_attributes=False)


def plain_dump(tree: ast.AST) -> str:
    return ast.dump(tree, include_attributes=False)


def reference_dump(src: str, mode: str = "full") -> str:
    """ast.dump of the mode-adjusted reference for Python source ``src``."""
    return normalized_dump(ast.parse(src), mode)


def has_docstring_anywhere(tree: ast.AST) -> bool:
    """True if any module/class/def body starts with a string Expr (a docstring position)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if _Normalizer._has_docstring(node.body):
                return True
    return False


def first_diff(a: str, b: str, width: int = 160) -> str:
    """Human readable pointer at the first differing position of two dumps."""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    lo = max(0, i - width // 2)
    return f"...{a[lo : i + width // 2]}...\n...{b[lo : i + width // 2]}..."


def assert_same_ast(got: ast.AST, want_dump: str, context: str = "") -> None:
    got_dump = plain_dump(got)
    if got_dump != want_dump:
        try:
            back = ast.unparse(got)
        except Exception as exc:  # noqa: BLE001
            back = f"<unparse failed: {exc}>"
        pytest.fail(
            f"AST mismatch{(' ' + context) if context else ''}\n"
            f"decoded: {back!r}\n{first_diff(want_dump, got_dump)}"
        )


# --------------------------------------------------------------------------- batteries


@dataclass(frozen=True)
class Snippet:
    id: str
    src: str
    min_version: tuple[int, int] = (3, 10)

    @property
    def supported(self) -> bool:
        return PY >= self.min_version


def _coerce(item: Any) -> tuple[str | None, str, tuple[int, int]]:
    """Battery item -> (name, src, min_version).

    Accepted forms: ``src`` | ``(src, ver)`` | ``(name, src)`` | ``(name, src, ver)``.
    """
    if isinstance(item, str):
        return None, item, (3, 10)
    if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str):
        if isinstance(item[1], str):
            return item[0], item[1], (3, 10)
        return None, item[0], tuple(item[1])  # type: ignore[return-value]
    if isinstance(item, tuple) and len(item) == 3 and isinstance(item[1], str):
        return item[0], item[1], tuple(item[2])  # type: ignore[return-value]
    raise TypeError(f"bad battery item {item!r}")


def _load_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"pydense_battery_{path.stem}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def battery_files() -> list[Path]:
    return sorted(p for p in BATTERIES_DIR.glob("*.py") if not p.name.startswith("_"))


def load_battery(path: Path) -> list[Snippet]:
    mod = _load_module(path)
    out: list[Snippet] = []
    for i, item in enumerate(mod.SNIPPETS):
        name, src, ver = _coerce(item)
        label = name if name is not None else f"{i:03d}"
        out.append(Snippet(f"{path.stem}[{label}]", src, ver))
    return out


def load_batteries() -> list[Snippet]:
    """Every Python snippet of every battery (lenient/rejected batteries are not Python)."""
    out: list[Snippet] = []
    for path in battery_files():
        if path.stem in ("lenient", "rejected"):
            continue
        out.extend(load_battery(path))
    return out


def load_pairs(name: str) -> list[tuple[str, Any]]:
    """(dpy_text, expected) tuples of the ``lenient`` / ``rejected`` battery."""
    mod = _load_module(BATTERIES_DIR / f"{name}.py")
    return list(mod.SNIPPETS)


def skip_unsupported(snippet: Snippet) -> None:
    if not snippet.supported:
        pytest.skip(f"needs Python {snippet.min_version[0]}.{snippet.min_version[1]}+")


def snippet_params(snippets: Iterable[Snippet]) -> list[Any]:
    return [pytest.param(s, id=s.id) for s in snippets]


def needs(major: int, minor: int) -> Any:
    return pytest.mark.skipif(PY < (major, minor), reason=f"needs Python {major}.{minor}+")


# --------------------------------------------------------------------------- lexer tokens

_TYPE_ATTRS = ("type", "kind", "tok_type", "category")
_VALUE_ATTRS = ("value", "string", "text", "src")
_LINE_ATTRS = ("lineno", "line", "row")
_COL_ATTRS = ("col", "col_offset", "column")


def _first_attr(obj: Any, names: tuple[str, ...]) -> Any:
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    if isinstance(obj, tuple):
        return None
    raise AttributeError(f"token {obj!r} has none of {names}")


def tok_type(tok: Any) -> str:
    t = _first_attr(tok, _TYPE_ATTRS)
    if t is None and isinstance(tok, tuple):
        t = tok[0]
    return str(getattr(t, "name", t)).upper()


def tok_value(tok: Any) -> str:
    v = _first_attr(tok, _VALUE_ATTRS)
    if v is None and isinstance(tok, tuple):
        v = tok[1]
    return v


def tok_line(tok: Any) -> int:
    v = _first_attr(tok, _LINE_ATTRS)
    if v is None and isinstance(tok, tuple):
        v = tok[2]
    return int(v)


def tok_col(tok: Any) -> int:
    v = _first_attr(tok, _COL_ATTRS)
    if v is None and isinstance(tok, tuple):
        v = tok[3]
    return int(v)


def tok_fields(tok: Any) -> tuple[str, str, int, int]:
    return tok_type(tok), tok_value(tok), tok_line(tok), tok_col(tok)


def tokens_of(text: str) -> list[Any]:
    from pydense.lexer import tokenize

    return list(tokenize(text))


def significant(tokens: Iterable[Any]) -> list[tuple[str, str]]:
    """(type, value) pairs without NEWLINE / EOF / COMMENT bookkeeping tokens."""
    out = []
    for t in tokens:
        ty = tok_type(t)
        if ty in ("NEWLINE", "NL", "EOF", "ENDMARKER", "COMMENT", "INDENT", "DEDENT"):
            continue
        out.append((ty, tok_value(t)))
    return out


def has_newline_between(tokens: list[Any], left_value: str, right_value: str) -> bool:
    """True iff a significant NEWLINE separates the first token ``left_value`` from the next
    token ``right_value`` — either as a NEWLINE token or as an ``nl_before`` flag."""
    vals = [tok_value(t) for t in tokens]
    i = vals.index(left_value)
    j = vals.index(right_value, i + 1)
    between = tokens[i + 1 : j]
    if any(tok_type(t) == "NEWLINE" for t in between):
        return True
    return bool(getattr(tokens[j], "nl_before", False))
