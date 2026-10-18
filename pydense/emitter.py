"""Emitter: Python ``ast`` -> canonical PyDense (.dpy) text (docs/SPEC.md sections 5, 7, 10, 11).

Subclasses :class:`ast._Unparser` so that operator precedence, parenthesisation and string
quoting are
inherited from CPython; only spacing, layout, the receiver rule, ``.x``, the ternary and the modes
are PyDense-specific.  The emitter is a pure function of the AST, so
``emit(parse(emit(x))) == emit(x)``.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Any, cast

from .errors import with_deep_recursion
from .rules import RECEIVER_ALIASES, RECEIVER_NAMES, receiver_for

try:  # private but stable since 3.9
    from ast import _ALL_QUOTES, _MULTI_QUOTES, _Precedence, _Unparser  # type: ignore[attr-defined]
except ImportError as exc:  # pragma: no cover
    raise ImportError("pydense needs the ast._Unparser machinery of CPython 3.9+") from exc


class Mode(str, Enum):
    FULL = "full"
    NODOC = "nodoc"
    STRIPPED = "stripped"

    @classmethod
    def coerce(cls, value: Mode | str) -> Mode:
        if isinstance(value, Mode):
            return value
        try:
            return cls(str(value).lower())
        except ValueError:
            raise ValueError(f"unknown mode {value!r}; use full, nodoc or stripped") from None


_WORD = re.compile(r"\w")
_MERGE_HAZARDS = frozenset(
    {
        "**",
        "//",
        "<<",
        ">>",
        "<=",
        ">=",
        "==",
        "!=",
        "->",
        "+=",
        "-=",
        "*=",
        "/=",
        "%=",
        "&=",
        "|=",
        "^=",
        "@=",
        ":=",
        "<>",
    }
)
# After a keyword these characters get a space for readability (`in {1,2}`, `return *a`, `case -1`).
_KW_SPACE_BEFORE = frozenset("{-+~*")


def _is_word(ch: str) -> bool:
    return bool(ch) and bool(_WORD.match(ch))


class Emitter(_Unparser):
    """Python AST -> .dpy text."""

    def __init__(self, mode: Mode = Mode.FULL, *, pretty: bool = False) -> None:
        super().__init__()
        self.mode = mode
        self.pretty = pretty
        self._scopes: list[str] = ["module"]
        self._last_kw = False  # last thing written was a keyword (for --pretty)
        self._num_dot = False  # last thing written was a number ending in '.'
        self._in_try_star = False
        self._bare_walrus: set[int] = set()  # NamedExpr nodes written without parentheses
        self._source: list[str]

    # ------------------------------------------------------------------ writing
    def write(self, *text: str) -> None:
        src = self._source
        for t in text:
            if not t:
                continue
            if src:
                last = src[-1][-1]
                first = t[0]
                if _is_word(last) and _is_word(first):
                    src.append(" ")
                elif self._num_dot and _is_word(first):
                    src.append(" ")  # `1. if`
                elif _is_word(last) and first == "." and len(t) > 1 and t[1].isdigit():
                    src.append(" ")  # `in .5`
                elif (last + first) in _MERGE_HAZARDS:
                    src.append(" ")
                elif self._last_kw and first in _KW_SPACE_BEFORE:
                    src.append(" ")
                elif self.pretty and self._last_kw and first in ".'\"":
                    src.append(" ")
                elif self.pretty and last in "'\"" and _is_word(first):
                    src.append(" ")
            src.append(t)
            self._last_kw = False
            self._num_dot = False

    def kw(self, word: str) -> None:
        self.write(word)
        self._last_kw = True

    def fill(self, text: str = "") -> None:
        """Start a statement: a newline unless at the very beginning."""
        if self._source:
            self._source.append("\n")
            self._last_kw = False
            self._num_dot = False
        if text:
            self.write(text)

    @contextmanager
    def delimit(self, start: str, end: str) -> Iterator[None]:
        self.write(start)
        yield
        self.write(end)

    def items(self, nodes: Any, f: Any = None) -> None:
        self.interleave(lambda: self.write(","), f or self.traverse, nodes)

    def items_view(self, traverser: Any, items: Any) -> None:
        if len(items) == 1:
            traverser(items[0])
            self.write(",")
        else:
            self.interleave(lambda: self.write(","), traverser, items)

    # ------------------------------------------------------------------ blocks / docstrings
    @staticmethod
    def _is_pass_only(stmts: list[ast.stmt]) -> bool:
        return len(stmts) == 1 and isinstance(stmts[0], ast.Pass)

    @staticmethod
    def _kept_docstring(node: Any) -> ast.Constant | None:
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            return body[0].value
        return None

    def _write_docstring(self, const: ast.Constant) -> None:
        """FULL mode writes docstrings triple-quoted, exactly as ``ast.unparse`` does."""
        self.fill()
        if const.kind == "u":
            self.write("u")
        self._write_str_avoiding_backslashes(const.value, quote_types=_MULTI_QUOTES)

    def emit_block(self, stmts: list[ast.stmt], owner: Any = None) -> None:
        """Write `{...}`; a body of exactly [Pass] (after docstring removal) is `{}`."""
        body = list(stmts)
        doc = self._kept_docstring(owner) if owner is not None else None
        if doc is not None:
            body = body[1:]
        self._source.append("{")  # a block brace is glued to its header (`)else{`, `){`)
        self._last_kw = False
        self._num_dot = False
        if doc is not None and self.mode is Mode.FULL:
            self._write_docstring(doc)
            self.traverse(body)
        else:
            if doc is not None and not body:
                body = [ast.Pass()]
            if not self._is_pass_only(body):
                self.traverse(body)
        self._source.append("}")
        self._last_kw = False
        self._num_dot = False

    def visit_Module(self, node: ast.Module) -> None:
        body = list(node.body)
        doc = self._kept_docstring(node)
        if doc is not None:
            body = body[1:]
            if self.mode is Mode.FULL:
                self._write_docstring(doc)
        self.traverse(body)

    def visit_Expr(self, node: ast.Expr) -> None:
        self.fill()
        self.set_precedence(_Precedence.TUPLE, node.value)
        self.traverse(node.value)

    def visit_Pass(self, node: ast.Pass) -> None:
        self.fill()
        self.kw("pass")

    def visit_Break(self, node: ast.Break) -> None:
        self.fill()
        self.kw("break")

    def visit_Continue(self, node: ast.Continue) -> None:
        self.fill()
        self.kw("continue")

    # ------------------------------------------------------------------ simple statements
    def visit_Import(self, node: ast.Import) -> None:
        self.fill()
        self.kw("import")
        self.items(node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.fill()
        self.kw("from")
        if node.level:
            self._source.append(" " + "." * node.level)
            self._last_kw = False
            if not node.module:
                self._source.append(" ")
        if node.module:
            self.write(node.module)
        self.kw("import")
        self.items(node.names)

    def visit_alias(self, node: ast.alias) -> None:
        self.write(node.name)
        if node.asname:
            self.kw("as")
            self.write(node.asname)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.fill()
        for target in node.targets:
            self.set_precedence(_Precedence.TUPLE, target)
            self.traverse(target)
            self.write("=")
        self.set_precedence(_Precedence.TUPLE, node.value)
        self.traverse(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.fill()
        self.traverse(node.target)
        self.write(self.binop[node.op.__class__.__name__] + "=")
        self.set_precedence(_Precedence.TUPLE, node.value)
        self.traverse(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.fill()
        if self.mode is Mode.STRIPPED and node.value is not None:
            self.set_precedence(_Precedence.TUPLE, node.target)
            self.traverse(node.target)
            self.write("=")
            self.set_precedence(_Precedence.TUPLE, node.value)
            self.traverse(node.value)
            return
        with self.delimit_if("(", ")", not node.simple and isinstance(node.target, ast.Name)):
            self.traverse(node.target)
        self.write(":")
        self.traverse(node.annotation)
        if node.value:
            self.write("=")
            self.set_precedence(_Precedence.TUPLE, node.value)
            self.traverse(node.value)

    def visit_Return(self, node: ast.Return) -> None:
        self.fill()
        self.kw("return")
        if node.value:
            prec = (
                _Precedence.ATOM
                if isinstance(node.value, (ast.Yield, ast.YieldFrom))
                else _Precedence.TUPLE
            )
            self.set_precedence(prec, node.value)
            self.traverse(node.value)

    def visit_Delete(self, node: ast.Delete) -> None:
        self.fill()
        self.kw("del")
        self.items(node.targets)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.fill()
        self.kw("assert")
        self.traverse(node.test)
        if node.msg:
            self.write(",")
            self.traverse(node.msg)

    def visit_Global(self, node: ast.Global) -> None:
        self.fill()
        self.kw("global")
        self.interleave(lambda: self.write(","), self.write, node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.fill()
        self.kw("nonlocal")
        self.interleave(lambda: self.write(","), self.write, node.names)

    def visit_Raise(self, node: ast.Raise) -> None:
        self.fill()
        self.kw("raise")
        if not node.exc:
            return
        self.traverse(node.exc)
        if node.cause:
            self.kw("from")
            self.traverse(node.cause)

    def visit_Await(self, node: ast.Await) -> None:
        with self.require_parens(_Precedence.AWAIT, node):
            self.kw("await")
            if node.value:
                self.set_precedence(_Precedence.ATOM, node.value)
                self.traverse(node.value)

    def visit_Yield(self, node: ast.Yield) -> None:
        with self.require_parens(_Precedence.YIELD, node):
            self.kw("yield")
            if node.value:
                # `yield a,b` is written bare (SPEC 9.1); a nested yield stays parenthesised.
                nested = isinstance(node.value, (ast.Yield, ast.YieldFrom))
                self.set_precedence(_Precedence.ATOM if nested else _Precedence.TUPLE, node.value)
                self.traverse(node.value)

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        with self.require_parens(_Precedence.YIELD, node):
            self.kw("yield")
            self.kw("from")
            self.set_precedence(_Precedence.ATOM, node.value)
            self.traverse(node.value)

    def visit_TypeAlias(self, node: Any) -> None:
        self.fill()
        self.kw("type")
        self.traverse(node.name)
        self._type_params_helper(node.type_params)
        self.write("=")
        self.traverse(node.value)

    def visit_TypeVar(self, node: Any) -> None:
        self.write(node.name)
        if node.bound:
            self.write(":")
            self.traverse(node.bound)
        if getattr(node, "default_value", None):
            self.write("=")
            self.traverse(node.default_value)

    def visit_TypeVarTuple(self, node: Any) -> None:
        self.write("*" + node.name)
        if getattr(node, "default_value", None):
            self.write("=")
            self.traverse(node.default_value)

    def visit_ParamSpec(self, node: Any) -> None:
        self.write("**" + node.name)
        if getattr(node, "default_value", None):
            self.write("=")
            self.traverse(node.default_value)

    def _type_params_helper(self, type_params: Any) -> None:
        if type_params:
            with self.delimit("[", "]"):
                self.items(type_params)

    # ------------------------------------------------------------------ compound statements
    def _else_block(self, stmts: list[ast.stmt]) -> None:
        self.kw("else")
        self.emit_block(stmts)

    def do_visit_try(self, node: Any) -> None:
        self.fill()
        self.kw("try")
        self.emit_block(node.body)
        for ex in node.handlers:
            self.traverse(ex)
        if node.orelse:
            self._else_block(node.orelse)
        if node.finalbody:
            self.kw("finally")
            self.emit_block(node.finalbody)

    def visit_Try(self, node: ast.Try) -> None:
        prev = self._in_try_star
        self._in_try_star = False
        try:
            self.do_visit_try(node)
        finally:
            self._in_try_star = prev

    def visit_TryStar(self, node: Any) -> None:
        prev = self._in_try_star
        self._in_try_star = True
        try:
            self.do_visit_try(node)
        finally:
            self._in_try_star = prev

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.kw("except*" if self._in_try_star else "except")
        if node.type:
            is_display = isinstance(node.type, (ast.Dict, ast.Set, ast.DictComp, ast.SetComp))
            with self.delimit_if("(", ")", is_display):
                self.traverse(node.type)
        if node.name:
            self.kw("as")
            self.write(node.name)
        self.emit_block(node.body)

    @staticmethod
    def _is_primary_chain(node: ast.expr) -> bool:
        while True:
            if isinstance(node, ast.Name):
                return True
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name) and node.value.id == "self":
                    return True
                node = node.value
            elif isinstance(node, ast.Call):
                node = node.func
            elif isinstance(node, ast.Subscript):
                node = node.value
            else:
                return False

    def _write_decorators(self, node: Any) -> None:
        for deco in node.decorator_list:
            self.write("@")
            with self.delimit_if("(", ")", not self._is_primary_chain(deco)):
                self.set_precedence(_Precedence.TEST, deco)
                self._allow_bare_walrus(deco)
                self.traverse(deco)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.fill()
        self._write_decorators(node)
        self.kw("class")
        self.write(node.name)
        self._type_params_helper(getattr(node, "type_params", None))
        with self.delimit_if("(", ")", condition=bool(node.bases or node.keywords)):
            self.items(list(node.bases) + list(node.keywords))
        self._scopes.append("class")
        try:
            self.emit_block(node.body, owner=node)
        finally:
            self._scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_helper(node, False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function_helper(node, True)

    def _method_form(self, node: Any) -> tuple[str, bool]:
        """Return (form, drop_first) with form in {'plain', 'dropped', 'bang'} (SPEC section 7)."""
        if self._scopes[-1] != "class":
            return "plain", False
        receiver = receiver_for(node.decorator_list)
        if receiver is None:
            return "plain", False
        args = node.args
        allpos = list(args.posonlyargs) + list(args.args)
        if allpos and allpos[0].arg in RECEIVER_NAMES:
            first = allpos[0]
            n_defaults = len(args.defaults)
            first_has_default = n_defaults > len(allpos) - 1  # defaults align to the end of allpos
            sole_posonly = len(args.posonlyargs) == 1
            rest_injects = not (
                len(allpos) > 1
                and (allpos[1].arg in RECEIVER_NAMES or allpos[1].arg in RECEIVER_ALIASES)
            )
            if (
                first.arg == receiver
                and (first.annotation is None or self.mode is Mode.STRIPPED)
                and not first_has_default
                and not sole_posonly
                and rest_injects
            ):
                return "dropped", True
            return "plain", False  # parser rule (b): first written param is literally self/cls
        return "bang", False

    def _function_helper(self, node: Any, is_async: bool) -> None:
        self.fill()
        self._write_decorators(node)
        if is_async:
            self.kw("async")
        form, drop_first = self._method_form(node)
        self.kw("def")
        if form == "bang":
            self.write("!")
        self.write(node.name)
        self._type_params_helper(getattr(node, "type_params", None))
        with self.delimit("(", ")"):
            self._emit_arguments(node.args, drop_first=drop_first)
        if node.returns and self.mode is not Mode.STRIPPED:
            self.write("->")
            self.traverse(node.returns)
        self._scopes.append("def")
        try:
            self.emit_block(node.body, owner=node)
        finally:
            self._scopes.pop()

    def _emit_arguments(self, args: ast.arguments, drop_first: bool = False) -> None:
        posonly = list(args.posonlyargs)
        regular = list(args.args)
        allpos = posonly + regular
        defaults: list[ast.expr | None] = [None] * (len(allpos) - len(args.defaults)) + list(
            args.defaults
        )
        if drop_first:
            if posonly:
                posonly = posonly[1:]
            else:
                regular = regular[1:]
            allpos = allpos[1:]
            defaults = defaults[1:]
        first = True

        def sep() -> None:
            nonlocal first
            if first:
                first = False
            else:
                self.write(",")

        for index, (a, d) in enumerate(zip(allpos, defaults, strict=True), 1):
            sep()
            self._write_arg(a)
            if d is not None:
                self.write("=")
                self.traverse(d)
            if posonly and index == len(posonly):
                self.write(",/")
        if args.vararg or args.kwonlyargs:
            sep()
            self.write("*")
            if args.vararg:
                self._write_arg(args.vararg)
        for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True):
            sep()
            self._write_arg(a)
            if d is not None:
                self.write("=")
                self.traverse(d)
        if args.kwarg:
            sep()
            self.write("**")
            self._write_arg(args.kwarg)

    def _write_arg(self, node: ast.arg) -> None:
        self.write(node.arg)
        if node.annotation and self.mode is not Mode.STRIPPED:
            self.write(":")
            self.traverse(node.annotation)

    def visit_arguments(self, node: ast.arguments) -> None:  # lambda only
        self._emit_arguments(node)

    def visit_arg(self, node: ast.arg) -> None:
        self._write_arg(node)

    def visit_keyword(self, node: ast.keyword) -> None:
        if node.arg is None:
            self.write("**")
        else:
            self.write(node.arg)
            self.write("=")
        self.traverse(node.value)

    def _for_helper(self, node: Any, is_async: bool) -> None:
        self.fill()
        if is_async:
            self.kw("async")
        self.kw("for")
        self.set_precedence(_Precedence.TUPLE, node.target)
        self.traverse(node.target)
        self.kw("in")
        self.set_precedence(self._header_tuple_precedence(node.iter), node.iter)
        self.traverse(node.iter)
        self.emit_block(node.body)
        if node.orelse:
            self._else_block(node.orelse)

    @staticmethod
    def _header_tuple_precedence(node: ast.expr) -> Any:
        """Bare tuples in a header, except a one-element tuple (its comma would run into `{`).

        A yield is parenthesised too: the parser does not accept a bare yield as an iterable or
        subject.
        """
        if isinstance(node, ast.Tuple) and len(node.elts) == 1:
            return _Precedence.TEST
        if isinstance(node, (ast.Yield, ast.YieldFrom)):
            return _Precedence.ATOM
        return _Precedence.TUPLE

    def visit_For(self, node: ast.For) -> None:
        self._for_helper(node, False)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._for_helper(node, True)

    def visit_If(self, node: ast.If) -> None:
        self.fill()
        self.kw("if")
        self._allow_bare_walrus(node.test)
        self.traverse(node.test)
        self.emit_block(node.body)
        while node.orelse and len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            node = node.orelse[0]
            self.kw("elif")
            self._allow_bare_walrus(node.test)
            self.traverse(node.test)
            self.emit_block(node.body)
        if node.orelse:
            self._else_block(node.orelse)

    def visit_While(self, node: ast.While) -> None:
        self.fill()
        self.kw("while")
        self._allow_bare_walrus(node.test)
        self.traverse(node.test)
        self.emit_block(node.body)
        if node.orelse:
            self._else_block(node.orelse)

    def _with_helper(self, node: Any, is_async: bool) -> None:
        self.fill()
        if is_async:
            self.kw("async")
        self.kw("with")
        self.items(node.items)
        self.emit_block(node.body)

    def visit_With(self, node: ast.With) -> None:
        self._with_helper(node, False)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._with_helper(node, True)

    def visit_withitem(self, node: ast.withitem) -> None:
        self.set_precedence(_Precedence.TEST.next(), node.context_expr)
        self.traverse(node.context_expr)
        if node.optional_vars:
            self.kw("as")
            self.traverse(node.optional_vars)

    def visit_Match(self, node: Any) -> None:
        self.fill()
        self.kw("match")
        self.set_precedence(self._header_tuple_precedence(node.subject), node.subject)
        self.traverse(node.subject)
        self._source.append("{")
        self._last_kw = False
        self.traverse(node.cases)
        self._source.append("}")
        self._last_kw = False

    def visit_match_case(self, node: Any) -> None:
        self.fill()
        self.kw("case")
        self.traverse(node.pattern)
        if node.guard:
            self.kw("if")
            self.traverse(node.guard)
        self.emit_block(node.body)

    # ------------------------------------------------------------------ expressions
    @staticmethod
    def _float_text(value: float) -> str:
        text = repr(value)
        if "e" in text or "n" in text:  # exponent form, inf, nan
            mant, _, exp = text.partition("e")
            if exp and mant.endswith(".0"):
                mant = mant[:-1]
            if exp:
                return f"{mant}e{exp}"
            return text
        if text.endswith(".0"):
            text = text[:-1]
        if text.startswith("0.") and len(text) > 2:
            text = text[1:]
        elif text.startswith("-0.") and len(text) > 3:
            text = "-" + text[2:]
        return text

    def _write_constant(self, value: Any) -> None:
        if (
            isinstance(value, float)
            and value == value
            and value not in (float("inf"), float("-inf"))
        ):
            self.write(self._float_text(value))
            self._num_dot = self._source[-1].endswith(".")
        elif isinstance(value, str):
            # Like repr(), but a string holding both quote kinds is triple-quoted instead of
            # escaped (fewer tokens, no backslash noise); whitespace is still escaped.
            text, quote_types = self._str_literal_helper(
                value, quote_types=_ALL_QUOTES, escape_special_whitespace=True
            )
            quote = quote_types[0]
            self.write(f"{quote}{text}{quote}")
        else:
            super()._write_constant(value)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            self.write("." + node.attr)
            return
        self.set_precedence(_Precedence.ATOM, node.value)
        if (
            isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, (int, float, complex))
            and not isinstance(node.value.value, bool)
        ):
            with self.delimit("(", ")"):
                self.traverse(node.value)
        else:
            self.traverse(node.value)
        self.write("." + node.attr)

    def visit_Call(self, node: ast.Call) -> None:
        self.set_precedence(_Precedence.ATOM, node.func)
        self.traverse(node.func)
        with self.delimit("(", ")"):
            if (
                len(node.args) == 1
                and not node.keywords
                and isinstance(node.args[0], ast.GeneratorExp)
            ):
                self._genexp_inner(node.args[0])
            else:
                self._allow_bare_walrus(*node.args)
                self.items(list(node.args) + list(node.keywords))

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self.set_precedence(_Precedence.ATOM, node.value)
        self.traverse(node.value)
        with self.delimit("[", "]"):
            sl = node.slice
            if (
                isinstance(sl, ast.Tuple)
                and len(sl.elts) == 1
                and isinstance(sl.elts[0], ast.Starred)
            ):
                self.traverse(sl.elts[0])  # `a[*idx]` is already a one-tuple in the AST
            elif isinstance(sl, ast.Tuple) and sl.elts:
                self.items_view(self.traverse, sl.elts)
            else:
                self.traverse(sl)

    def visit_Slice(self, node: ast.Slice) -> None:
        for part in (node.lower, node.upper, node.step):
            if part is not None:
                self.set_precedence(_Precedence.TEST.next(), part)
        if node.lower:
            self.traverse(node.lower)
        self.write(":")
        if node.upper:
            self.traverse(node.upper)
        if node.step:
            self.write(":")
            self.traverse(node.step)

    def _allow_bare_walrus(self, *nodes: ast.expr) -> None:
        """Python allows a bare `x:=v` here (if/while header, call argument, list/set item)."""
        for n in nodes:
            if isinstance(n, ast.NamedExpr):
                self._bare_walrus.add(id(n))

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        with self.delimit_if("(", ")", id(node) not in self._bare_walrus):
            self.set_precedence(_Precedence.ATOM, node.target, node.value)
            self.traverse(node.target)
            self.write(":=")
            self.traverse(node.value)

    def visit_List(self, node: ast.List) -> None:
        with self.delimit("[", "]"):
            self._allow_bare_walrus(*node.elts)
            self.items(node.elts)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        bare = len(node.elts) > 0 and self.get_precedence(node) <= _Precedence.TUPLE
        with self.delimit_if("(", ")", not bare):
            if bare:  # `c?a:b,d` reads badly: parenthesise ternaries/lambdas inside a bare tuple
                for elt in node.elts:
                    if isinstance(elt, (ast.IfExp, ast.Lambda)):
                        self.set_precedence(_Precedence.TEST.next(), elt)
            self.items_view(self.traverse, node.elts)

    def visit_Set(self, node: ast.Set) -> None:
        if node.elts:
            with self.delimit("{", "}"):
                self._allow_bare_walrus(*node.elts)
                self.items(node.elts)
        else:
            self.write("{*()}")

    def visit_Dict(self, node: ast.Dict) -> None:
        def write_item(item: tuple[ast.expr | None, ast.expr]) -> None:
            k, v = item
            if k is None:
                self.write("**")
                self.set_precedence(_Precedence.EXPR, v)
                self.traverse(v)
            else:
                self.set_precedence(_Precedence.TEST.next(), k)
                self.traverse(k)
                self.write(":")
                self.traverse(v)

        with self.delimit("{", "}"):
            self.interleave(
                lambda: self.write(","), write_item, zip(node.keys, node.values, strict=True)
            )

    def visit_ListComp(self, node: ast.ListComp) -> None:
        with self.delimit("[", "]"):
            self.traverse(node.elt)
            self.traverse(node.generators)

    def _genexp_inner(self, node: ast.GeneratorExp) -> None:
        self.traverse(node.elt)
        self.traverse(node.generators)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        with self.delimit("(", ")"):
            self._genexp_inner(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        with self.delimit("{", "}"):
            self.traverse(node.elt)
            self.traverse(node.generators)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        with self.delimit("{", "}"):
            self.set_precedence(_Precedence.TEST.next(), node.key)
            self.traverse(node.key)
            self.write(":")
            self.traverse(node.value)
            self.traverse(node.generators)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        if node.is_async:
            self.kw("async")
        self.kw("for")
        self.set_precedence(_Precedence.TUPLE, node.target)
        self.traverse(node.target)
        self.kw("in")
        self.set_precedence(_Precedence.TEST.next(), node.iter, *node.ifs)
        self.traverse(node.iter)
        for if_clause in node.ifs:
            self.kw("if")
            self.traverse(if_clause)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        with self.require_parens(_Precedence.TEST, node):
            self.set_precedence(_Precedence.TEST.next(), node.body, node.test)
            self.traverse(node.test)
            self.write("?")
            self.traverse(node.body)
            self.write(":")
            orelse_prec = (
                _Precedence.TEST.next() if isinstance(node.orelse, ast.Lambda) else _Precedence.TEST
            )
            self.set_precedence(orelse_prec, node.orelse)
            self.traverse(node.orelse)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        with self.require_parens(_Precedence.TEST, node):
            self.kw("lambda")
            self._emit_arguments(node.args)
            self.write(":")
            self.set_precedence(_Precedence.TEST, node.body)
            self.traverse(node.body)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        operator = self.unop[node.op.__class__.__name__]
        operator_precedence = self.unop_precedence[operator]
        with self.require_parens(operator_precedence, node):
            if operator == "not":
                self.kw("not")
            else:
                self.write(operator)
            self.set_precedence(operator_precedence, node.operand)
            self.traverse(node.operand)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        operator = self.binop[node.op.__class__.__name__]
        operator_precedence = self.binop_precedence[operator]
        with self.require_parens(operator_precedence, node):
            if operator in self.binop_rassoc:
                left_precedence, right_precedence = operator_precedence.next(), operator_precedence
                if isinstance(node.right, ast.UnaryOp) and not isinstance(node.right.op, ast.Not):
                    right_precedence = _Precedence.FACTOR  # `a**-b`: the right operand is a factor
            else:
                left_precedence, right_precedence = operator_precedence, operator_precedence.next()
            self.set_precedence(left_precedence, node.left)
            self.traverse(node.left)
            self.write(operator)
            self.set_precedence(right_precedence, node.right)
            self.traverse(node.right)

    def visit_Compare(self, node: ast.Compare) -> None:
        with self.require_parens(_Precedence.CMP, node):
            self.set_precedence(_Precedence.CMP.next(), node.left, *node.comparators)
            self.traverse(node.left)
            for o, e in zip(node.ops, node.comparators, strict=True):
                sym = self.cmpops[o.__class__.__name__]
                if sym[0].isalpha():
                    for w in sym.split():
                        self.kw(w)
                else:
                    self.write(sym)
                self.traverse(e)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        operator = self.boolops[node.op.__class__.__name__]
        operator_precedence = self.boolop_precedence[operator]

        with self.require_parens(operator_precedence, node):
            # `a or b and c` needs no parentheses; a nested same operator does (`a or (b or c)`).
            self.set_precedence(operator_precedence.next(), *node.values)
            self.interleave(lambda: self.kw(operator), self.traverse, node.values)

    def visit_Starred(self, node: ast.Starred) -> None:
        self.write("*")
        self.set_precedence(_Precedence.EXPR, node.value)
        self.traverse(node.value)

    # ------------------------------------------------ f-strings (version independent)
    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self.write("f")
        body, quote_types = self._fstring_body(node)
        quote = quote_types[0]
        if body.endswith(quote[0]) and not body.endswith("\\" + quote[0]):
            body = body[:-1] + "\\" + body[-1]  # `..."` + `"""` would close early
        self._source.append(f"{quote}{body}{quote}")
        self._last_kw = False
        self._num_dot = False

    @staticmethod
    def _escape_fstring_literal(text: str) -> str:
        """Escape as ``ast._Unparser`` does for f-string literals (backslash, non-printables)."""
        out = []
        for ch in text:
            if ch == "\\" or ch in "\n\t" or not ch.isprintable():
                out.append(ch.encode("unicode_escape").decode("ascii"))
            else:
                out.append(ch)
        return "".join(out).replace("{", "{{").replace("}", "}}")

    def _fstring_body(self, node: ast.JoinedStr) -> tuple[str, list[str]]:
        parts: list[str] = []
        literal_text: list[str] = []
        field_texts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                text = self._escape_fstring_literal(str(value.value))
                parts.append(text)
                literal_text.append(text)
            else:
                text = self._formatted_value_text(cast(ast.FormattedValue, value))
                parts.append(text)
                field_texts.append(text)
        joined = "".join(literal_text)
        # A quote may be used when it never occurs in the literal text; prefer one that is also not
        # reused inside a replacement field (`f"{d['k']}"` rather than PEP 701 nesting).
        candidates = [q for q in _ALL_QUOTES if q not in joined]
        preferred = [q for q in candidates if not any(q[0] in ft for ft in field_texts)]
        if preferred:
            quote_types = preferred
        elif candidates:
            quote_types = candidates
        else:  # every quote style occurs in the literal text: escape the single quote everywhere
            quote_types = ["'"]
            parts = [
                p.replace("'", "\\'") if isinstance(v, ast.Constant) else p
                for p, v in zip(parts, node.values, strict=True)
            ]
        return "".join(parts), quote_types

    def _formatted_value_text(self, node: ast.FormattedValue) -> str:
        sub = Emitter(self.mode, pretty=self.pretty)
        sub._scopes = list(self._scopes)
        sub.set_precedence(_Precedence.TEST.next(), node.value)
        expr = sub.visit(node.value)
        if expr.startswith("{"):
            expr = " " + expr
        out = "{" + expr
        if node.conversion != -1:
            out += f"!{chr(node.conversion)}"
        if node.format_spec:
            out += ":" + self._spec_text(cast(ast.JoinedStr, node.format_spec))
        return out + "}"

    def _spec_text(self, spec: ast.JoinedStr) -> str:
        parts = []
        for value in spec.values:
            if isinstance(value, ast.Constant):
                # a format spec has no brace escapes: every '{' is a nested field
                parts.append(self._escape_fstring_literal(str(value.value)).replace("{{", "{"))
            else:
                parts.append(self._formatted_value_text(cast(ast.FormattedValue, value)))
        return "".join(parts)

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:  # bare, outside a JoinedStr
        self.write("f")
        self._source.append("'" + self._formatted_value_text(node) + "'")

    # ------------------------------------------------------------------ patterns
    def visit_MatchValue(self, node: Any) -> None:
        self.traverse(node.value)

    def visit_MatchSingleton(self, node: Any) -> None:
        self._write_constant(node.value)

    def visit_MatchSequence(self, node: Any) -> None:
        with self.delimit("[", "]"):
            self.items(node.patterns)

    def visit_MatchStar(self, node: Any) -> None:
        self.write("*" + (node.name or "_"))

    def visit_MatchMapping(self, node: Any) -> None:
        def pair(p: tuple[ast.expr, Any]) -> None:
            k, pt = p
            self.traverse(k)
            self.write(":")
            self.traverse(pt)

        with self.delimit("{", "}"):
            self.interleave(
                lambda: self.write(","), pair, list(zip(node.keys, node.patterns, strict=True))
            )
            if node.rest is not None:
                if node.keys:
                    self.write(",")
                self.write(f"**{node.rest}")

    def visit_MatchClass(self, node: Any) -> None:
        self.set_precedence(_Precedence.ATOM, node.cls)
        self.traverse(node.cls)
        with self.delimit("(", ")"):
            self.items(node.patterns)
            if node.kwd_attrs:
                if node.patterns:
                    self.write(",")

                def attr(p: tuple[str, Any]) -> None:
                    a, pt = p
                    self.write(f"{a}=")
                    self.traverse(pt)

                self.interleave(
                    lambda: self.write(","),
                    attr,
                    list(zip(node.kwd_attrs, node.kwd_patterns, strict=True)),
                )

    def visit_MatchAs(self, node: Any) -> None:
        if node.name is None:
            self.write("_")
        elif node.pattern is None:
            self.write(node.name)
        else:
            with self.require_parens(_Precedence.TEST, node):
                self.set_precedence(_Precedence.BOR, node.pattern)
                self.traverse(node.pattern)
                self.kw("as")
                self.write(node.name)

    def visit_MatchOr(self, node: Any) -> None:
        with self.require_parens(_Precedence.BOR, node):
            self.set_precedence(_Precedence.BOR.next(), *node.patterns)
            self.interleave(lambda: self.write("|"), self.traverse, node.patterns)


def encode(
    source: str | ast.AST,
    *,
    mode: Mode | str = Mode.FULL,
    pretty: bool = False,
    filename: str = "<python>",
) -> str:
    """Python source (or an ast.Module) -> canonical .dpy text."""
    tree = ast.parse(source, filename=filename) if isinstance(source, str) else source
    emitter = Emitter(Mode.coerce(mode), pretty=pretty)
    return with_deep_recursion(lambda: emitter.visit(tree), filename)


__all__ = ["Emitter", "Mode", "encode"]
