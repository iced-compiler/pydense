"""Recursive-descent parser: PyDense (.dpy) text -> ``ast.Module`` (docs/SPEC.md sections 3-7).

The parser builds ``ast`` nodes directly (no intermediate Python text).  Lookahead is at most two
tokens except for the ``match`` soft keyword, which uses bounded speculation on its header (6.7).
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from typing import Any, NoReturn, cast

from .errors import Diagnostic, PyDenseSyntaxError, with_deep_recursion
from .lexer import HARD_KEYWORDS, LineMap, Token, tokenize
from .rules import (
    E008_HINT,
    LEGACY_MACRO_ALTERNATION,
    LEGACY_MACRO_HINT,
    RECEIVER_ALIASES,
    RECEIVER_NAMES,
    receiver_for,
)
from .strings import _NAME_RE, _merge_constants, parse_fstring_body

PY = sys.version_info

_AUGOPS = {
    "+=": ast.Add,
    "-=": ast.Sub,
    "*=": ast.Mult,
    "/=": ast.Div,
    "//=": ast.FloorDiv,
    "%=": ast.Mod,
    "**=": ast.Pow,
    ">>=": ast.RShift,
    "<<=": ast.LShift,
    "&=": ast.BitAnd,
    "|=": ast.BitOr,
    "^=": ast.BitXor,
    "@=": ast.MatMult,
}
_BINOPS = {
    "+": ast.Add,
    "-": ast.Sub,
    "*": ast.Mult,
    "/": ast.Div,
    "//": ast.FloorDiv,
    "%": ast.Mod,
    "@": ast.MatMult,
    "<<": ast.LShift,
    ">>": ast.RShift,
    "&": ast.BitAnd,
    "|": ast.BitOr,
    "^": ast.BitXor,
    "**": ast.Pow,
}
_CMPOPS = {"==": ast.Eq, "!=": ast.NotEq, "<": ast.Lt, "<=": ast.LtE, ">": ast.Gt, ">=": ast.GtE}
_SINGLETONS = {"None": None, "True": True, "False": False}
_EXPR_KEYWORDS = frozenset({"None", "True", "False", "not", "await", "lambda", "yield"})
_SIMPLE_KW = frozenset(
    {
        "return",
        "pass",
        "break",
        "continue",
        "raise",
        "global",
        "nonlocal",
        "del",
        "assert",
        "import",
        "from",
    }
)
_BLOCK_CONTINUATION = frozenset({"else", "elif", "except", "finally"})
_LEGACY_DECORATORS = frozenset({"f", "c", "i", "af", "sf", "w", "wa", "aw"})

_LEGACY_MACRO_RE = re.compile(rf"#(?:{LEGACY_MACRO_ALTERNATION})(?![\w])")
_E008_HINT = E008_HINT


class _Rewind(Exception):
    pass


def _set_ctx(node: ast.expr, ctx: ast.expr_context, p: Parser) -> ast.expr:
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
        node.ctx = ctx
    elif isinstance(node, (ast.Tuple, ast.List)):
        node.ctx = ctx
        for e in node.elts:
            _set_ctx(e, ctx, p)
    elif isinstance(node, ast.Starred):
        node.ctx = ctx
        _set_ctx(node.value, ctx, p)
    else:
        kind = "delete" if isinstance(ctx, ast.Del) else "assign to"
        p.error(f"cannot {kind} {type(node).__name__}", at=node)
    return node


class Parser:
    def __init__(self, src: str, filename: str = "<dpy>", *, collect_warnings: bool = True) -> None:
        self.src = src
        self.filename = filename
        self.lm = LineMap(src)
        self.toks: list[Token] = tokenize(src, filename)
        self.i = 0
        self.scopes: list[str] = ["module"]  # module | class | def
        self.depth = 0  # bracket depth incl. displays; newlines are insignificant when > 0
        self.open_blocks: list[Token] = []  # '{' tokens of blocks currently being parsed
        self.last_atom_parenthesized = False
        self.warnings: list[Diagnostic] = []
        self._collect = collect_warnings
        self._stmt_last_tok: Token | None = (
            None  # last token of the previous statement in this block
        )
        self._stmt_first = True  # first statement of the current block/module
        self._last_close_display = False  # the most recent '}' closed a dict/set display

    # ------------------------------------------------------------------ token helpers
    def _skip_nl(self, i: int) -> int:
        toks = self.toks
        while toks[i].kind == "NEWLINE":
            i += 1
        return i

    def peek(self, k: int = 0) -> Token:
        i = self.i
        for step in range(k + 1):
            i = self._skip_nl(i)
            if step < k:
                i += 1
        return self.toks[i]

    def newline_before(self) -> bool:
        """True when a NEWLINE separates the last consumed token from the next one."""
        return self.toks[self.i].kind == "NEWLINE"

    def nl_terminates(self) -> bool:
        """A depth-0 newline before the next token ends the simple statement / expression."""
        return self.depth == 0 and self.newline_before()

    def advance(self) -> Token:
        self.i = self._skip_nl(self.i)
        t = self.toks[self.i]
        self.i += 1
        return t

    def prev(self) -> Token:
        i = self.i - 1
        while i >= 0 and self.toks[i].kind == "NEWLINE":
            i -= 1
        return self.toks[max(i, 0)]

    def at(self, value: str, k: int = 0) -> bool:
        t = self.peek(k)
        return t.kind in ("OP", "NAME") and t.value == value

    def cont(self, value: str) -> bool:
        """Like at(), but False when a depth-0 newline precedes the token (statement boundary)."""
        return not self.nl_terminates() and self.at(value)

    def at_name(self, k: int = 0) -> bool:
        t = self.peek(k)
        return t.kind == "NAME" and t.value not in HARD_KEYWORDS

    def accept(self, value: str) -> bool:
        if self.at(value):
            self.advance()
            return True
        return False

    def accept_cont(self, value: str) -> bool:
        if self.cont(value):
            self.advance()
            return True
        return False

    def expect(self, value: str, hint: str = "") -> Token:
        t = self.peek()
        if not (t.kind in ("OP", "NAME") and t.value == value):
            self.error(f"expected {value!r} but found {self._describe(t)}", hint=hint)
        return self.advance()

    def expect_name(self) -> str:
        t = self.peek()
        if t.kind != "NAME" or t.value in HARD_KEYWORDS:
            self.error(f"expected a name but found {self._describe(t)}")
        self.advance()
        return t.value

    @staticmethod
    def _describe(t: Token) -> str:
        if t.kind == "EOF":
            return "end of input"
        if t.kind == "NEWLINE":
            return "newline"
        return f"{t.kind} {t.value!r}" if t.kind in ("NAME", "NUMBER", "STRING") else repr(t.value)

    def error(self, msg: str, *, code: str = "E000", hint: str = "", at: Any = None) -> NoReturn:
        if isinstance(at, Token):
            line, col = at.line, at.col
        elif isinstance(at, ast.AST) and getattr(at, "lineno", None):
            line, col = at.lineno, getattr(at, "col_offset", 0)  # type: ignore[attr-defined]
        else:
            t = self.peek()
            line, col = t.line, t.col
        raise PyDenseSyntaxError(
            msg,
            code=code,
            lineno=line,
            col=col,
            filename=self.filename,
            text=self.lm.line_text(line),
            hint=hint,
        )

    def warn(self, code: str, msg: str, tok: Token, hint: str = "") -> None:
        if self._collect:
            self.warnings.append(Diagnostic(code, msg, tok.line, tok.col, "warning", hint))

    @contextmanager
    def bracket(self) -> Iterator[None]:
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1

    @contextmanager
    def speculate(self) -> Iterator[None]:
        saved = (self.i, self.depth, len(self.warnings))
        try:
            yield
        except PyDenseSyntaxError:
            self.i, self.depth, nw = saved
            del self.warnings[nw:]
            raise _Rewind() from None

    @staticmethod
    def _loc(node: Any, tok: Token) -> Any:
        node.lineno = tok.line
        node.col_offset = tok.col
        return node

    # ------------------------------------------------------------------ module / blocks
    def parse_module(self) -> ast.Module:
        body = self._parse_stmt_list(closer=None)
        if self.peek().kind != "EOF":
            t = self.peek()
            if t.value == "}":
                self.error(
                    "unmatched '}'", code="E002", hint="remove it or open a block before it", at=t
                )
            self.error(f"unexpected {self._describe(t)}")
        mod = ast.Module(body=body, type_ignores=[])
        _fix_locations(mod, 1, 0)
        return mod

    def _parse_stmt_list(self, closer: str | None) -> list[ast.stmt]:
        body: list[ast.stmt] = []
        saved_last, saved_first = self._stmt_last_tok, self._stmt_first
        self._stmt_last_tok, self._stmt_first = None, True
        try:
            while True:
                t = self.peek()
                if t.kind == "EOF" or (closer is not None and t.kind == "OP" and t.value == closer):
                    break
                if closer is None and t.kind == "OP" and t.value == "}":
                    break
                if t.kind == "OP" and t.value == ";":
                    prev = self.prev()
                    if prev.value == "}" or self.peek(1).value == "}" or self.peek(1).kind == "EOF":
                        self.warn(
                            "W004",
                            "';' is not needed here",
                            t,
                            "PyDense separates statements with newlines",
                        )
                    self.advance()
                    continue
                first_tok = t
                first_idx = self._skip_nl(self.i)
                self._check_legacy_statement_start(first_tok)
                stmt = self.parse_statement()
                last_tok = self.prev()
                self._lint_statement(first_tok, first_idx, last_tok)
                body.append(stmt)
                self._stmt_last_tok = last_tok
                self._stmt_first = False
        finally:
            self._stmt_last_tok, self._stmt_first = saved_last, saved_first
        return body

    def parse_block(self) -> list[ast.stmt]:
        if self.at(":") and self.peek(1).value == "{":
            self.advance()  # colon habit: `if x:{`
        t = self.peek()
        if not (t.kind == "OP" and t.value == "{"):
            if t.kind == "EOF":
                self._eof_error()
            self.error(
                f"expected '{{' to open a block but found {self._describe(t)}",
                hint="blocks are written {...}",
            )
        open_tok = self.advance()
        self.open_blocks.append(open_tok)
        body = self._parse_stmt_list(closer="}")
        if self.peek().kind == "EOF":
            self._eof_error()
        self.expect("}")
        self.open_blocks.pop()
        self._last_close_display = False
        return body or [ast.Pass()]

    def _eof_error(self) -> None:
        opens = self.open_blocks
        if not opens:
            self.error("unexpected end of input", hint="the statement is incomplete")
        where = " and ".join(f"{t.line}:{t.col}" for t in opens)
        n = len(opens)
        self.error(
            f"unexpected end of input: {n} unclosed '{{' (opened at {where})",
            code="E001",
            hint="add the missing '}'" + ("s" if n > 1 else ""),
        )

    def end_simple_stmt(self) -> None:
        t = self.peek()
        if t.kind == "OP" and t.value == ";":
            self.advance()
            nxt = self.peek()
            if nxt.kind == "EOF" or (nxt.kind == "OP" and nxt.value in ("}", ";")):
                self.warn(
                    "W004",
                    "';' is not needed here",
                    t,
                    "PyDense separates statements with newlines",
                )
            return
        if (t.kind == "OP" and t.value == "}") or t.kind == "EOF" or self.newline_before():
            return
        if (
            t.kind == "NAME"
            and t.value in _BLOCK_CONTINUATION
            and self._last_close_display
            and self.prev().value == "}"
        ):
            self.warn(
                "W003",
                f"'{t.value}' follows a '}}' that closed a dict/set display, not a block",
                t,
                "the header before it is missing or the block braces are misplaced",
            )
        if t.kind == "OP" and t.value == "{":
            self.error(
                "unexpected '{' after a simple statement",
                hint="only if/for/while/def/class/try/with/match headers open a block",
            )
        self.error(
            f"expected newline, ';' or '}}' before {self._describe(t)}",
            code="E003",
            hint="put each statement on its own line or separate them with ';'",
        )

    # ------------------------------------------------------------------ lint hooks
    def _check_legacy_statement_start(self, t: Token) -> None:
        v = t.value
        if t.kind == "OP":
            if v in ("?", "^", "!", "~?", "^>"):
                self.error(
                    f"{v!r} cannot start a statement",
                    code="E008",
                    hint=_E008_HINT,
                    at=t,
                )
            if v == ":" and self.prev().value == "}":
                self.error("'}:{' is not an else block", code="E008", hint="write }else{", at=t)
            if v in ("+", "-", "~") and not self._stmt_first:
                self.warn(
                    "W005",
                    f"statement starts with {v!r} after a newline",
                    t,
                    "Python reads this as a new statement; bracket the expression if it continues "
                    "the previous line",
                )

    def _lint_statement(self, first: Token, first_idx: int, last: Token) -> None:
        prev_last = self._stmt_last_tok
        if (
            first.kind == "OP"
            and first.value == "."
            and prev_last is not None
            and prev_last.value in (")", "]")
            and self.toks[first_idx + 1].kind == "NAME"
            and self.toks[first_idx + 2].value in ("(", "[")
        ):
            self.warn(
                "W001",
                "statement starts with '.NAME(' right after a ')'-terminated statement",
                first,
                "this is two statements ('.x' means 'self.x'); bracket a call chain that continues "
                "a line",
            )

    # ------------------------------------------------------------------ statements
    def parse_statement(self) -> ast.stmt:
        t = self.peek()
        if t.kind == "OP" and t.value == "@":
            return self.parse_decorated()
        if t.kind == "NAME":
            v = t.value
            if v == "def":
                return self.parse_funcdef([], False, t)
            if v == "class":
                return self.parse_classdef([], t)
            if v == "async":
                nxt = self.peek(1).value
                if nxt == "def":
                    self.advance()
                    return self.parse_funcdef([], True, t)
                if nxt == "for":
                    self.advance()
                    return self.parse_for(True, t)
                if nxt == "with":
                    self.advance()
                    return self.parse_with(True, t)
                self.error("'async' must be followed by def, for or with")
            if v == "if":
                return self.parse_if()
            if v == "while":
                return self.parse_while()
            if v == "for":
                return self.parse_for(False, t)
            if v == "try":
                return self.parse_try()
            if v == "with":
                return self.parse_with(False, t)
            if v in _BLOCK_CONTINUATION:
                if self._last_close_display and self.prev().value == "}":
                    self.warn(
                        "W003",
                        f"'{v}' follows a '}}' that closed a dict/set display, not a block",
                        t,
                        "the header before it is missing or the block braces are misplaced",
                    )
                self.error(
                    f"{v!r} without a matching block",
                    hint=f"'{v}' must directly follow the '}}' of its if/for/while/try block",
                )
            if v == "match":
                matched = self._try_match(t)
                if matched is not None:
                    return matched
            if (
                v == "type"
                and self.peek(1).kind == "NAME"
                and self.peek(1).value not in HARD_KEYWORDS
            ):
                return self.parse_type_alias(t)
            if v in _SIMPLE_KW:
                node = self.parse_simple_keyword_stmt(v, t)
                self.end_simple_stmt()
                return node
        node = self.parse_expr_or_assign()
        self.end_simple_stmt()
        return node

    def starts_expr(self, t: Token) -> bool:
        if t.kind in ("NUMBER", "STRING"):
            return True
        if t.kind == "NAME":
            return t.value not in HARD_KEYWORDS or t.value in _EXPR_KEYWORDS
        if t.kind == "OP":
            return t.value in ("(", "[", "{", "-", "+", "~", "*", ".", "...")
        return False

    def optional_expr_follows(self) -> bool:
        if self.newline_before():
            self._maybe_legacy_macro_error(self.peek())
            return False
        t = self.peek()
        if t.kind == "EOF":
            self._maybe_legacy_macro_error(t)
        if t.kind == "OP" and t.value in (";", "}"):
            return False
        return self.starts_expr(t)

    def parse_simple_keyword_stmt(self, v: str, t0: Token) -> ast.stmt:
        self.advance()
        node: ast.stmt
        if v == "pass":
            node = ast.Pass()
        elif v == "break":
            node = ast.Break()
        elif v == "continue":
            node = ast.Continue()
        elif v == "return":
            value = (
                self.parse_star_exprs(allow_yield=True) if self.optional_expr_follows() else None
            )
            node = ast.Return(value=value)
        elif v == "raise":
            exc = cause = None
            if self.optional_expr_follows():
                exc = self.parse_test()
                if self.accept_cont("from"):
                    cause = self.parse_test()
            node = ast.Raise(exc=exc, cause=cause)
        elif v in ("global", "nonlocal"):
            names = [self.expect_name()]
            while self.accept_cont(","):
                names.append(self.expect_name())
            node = (ast.Global if v == "global" else ast.Nonlocal)(names=names)
        elif v == "del":
            targets = [self.parse_bitor_or_star()]
            while self.accept_cont(","):
                if not self.starts_expr(self.peek()) or self.nl_terminates():
                    break
                targets.append(self.parse_bitor_or_star())
            for x in targets:
                if isinstance(x, ast.Starred):
                    self.error("cannot delete a starred expression", at=x)
            node = ast.Delete(targets=[_set_ctx(x, ast.Del(), self) for x in targets])
        elif v == "assert":
            test = self.parse_test()
            msg = self.parse_test() if self.accept_cont(",") else None
            node = ast.Assert(test=test, msg=msg)
        elif v == "import":
            aliases = [self.parse_alias(dotted=True)]
            while self.accept_cont(","):
                self._operand_follows()
                aliases.append(self.parse_alias(dotted=True))
            if self.cont("="):
                self.error("'import a=b' is not PyDense", code="E008", hint="write 'import a as b'")
            node = ast.Import(names=aliases)
        elif v == "from":
            level = 0
            while True:
                if self.at("."):
                    self.advance()
                    level += 1
                elif self.at("..."):
                    self.advance()
                    level += 3
                else:
                    break
            module = None
            if not self.at("import"):
                module = self.parse_dotted_name()
            if self.at(":"):
                self.error("'from m:a' is not PyDense", code="E008", hint="write 'from m import a'")
            self.expect("import")
            if self.accept("*"):
                node = ast.ImportFrom(
                    module=module, names=[ast.alias(name="*", asname=None)], level=level
                )
            else:
                paren = self.accept("(")
                with self.bracket() if paren else nullcontext():
                    aliases = [self.parse_alias(dotted=False)]
                    while self.accept_cont(","):
                        if paren and self.at(")"):
                            break
                        if not paren:
                            self._operand_follows()
                        aliases.append(self.parse_alias(dotted=False))
                if paren:
                    self.expect(")")
                node = ast.ImportFrom(module=module, names=aliases, level=level)
        else:  # pragma: no cover
            self.error(f"unknown statement {v!r}")
        return self._loc(node, t0)

    def parse_dotted_name(self) -> str:
        parts = [self.expect_name()]
        while self.cont(".") and self.peek(1).kind == "NAME":
            self.advance()
            self._operand_follows()
            parts.append(self.expect_name())
        return ".".join(parts)

    def parse_alias(self, dotted: bool) -> ast.alias:
        t = self.peek()
        name = self.parse_dotted_name() if dotted else self.expect_name()
        asname = None
        if self.accept_cont("as"):
            asname = self.expect_name()
        return self._loc(ast.alias(name=name, asname=asname), t)

    def parse_type_alias(self, t0: Token) -> ast.stmt:
        if PY < (3, 12):
            self.error("'type' aliases need Python 3.12+")
        self.expect("type")
        name_tok = self.peek()
        name = self._loc(ast.Name(id=self.expect_name(), ctx=ast.Store()), name_tok)
        tps = self.parse_type_params()
        self.expect("=")
        value = self.parse_test()
        self.end_simple_stmt()
        return self._loc(ast.TypeAlias(name=name, type_params=tps, value=value), t0)  # type: ignore[attr-defined]

    def parse_type_params(self) -> list[Any]:
        if not self.at("["):
            return []
        if PY < (3, 12):
            self.error("type parameters need Python 3.12+")
        self.advance()
        out: list[Any] = []

        def default_value() -> Any:
            if not self.accept("="):
                return None
            if PY < (3, 13):
                self.error("type parameter defaults need Python 3.13+")
            return self.parse_star_or_test()

        def mk(cls: Any, **kw: Any) -> Any:
            if PY < (3, 13):
                kw.pop("default_value", None)
            return cls(**kw)

        with self.bracket():
            while not self.at("]"):
                t = self.peek()
                if self.accept("*"):
                    name = self.expect_name()
                    node = mk(ast.TypeVarTuple, name=name, default_value=default_value())  # type: ignore[attr-defined]
                elif self.accept("**"):
                    name = self.expect_name()
                    node = mk(ast.ParamSpec, name=name, default_value=default_value())  # type: ignore[attr-defined]
                else:
                    name = self.expect_name()
                    bound = self.parse_test() if self.accept(":") else None
                    node = mk(ast.TypeVar, name=name, bound=bound, default_value=default_value())  # type: ignore[attr-defined]
                out.append(self._loc(node, t))
                if not self.accept(","):
                    break
        self.expect("]")
        return out

    def parse_star_or_test(self) -> ast.expr:
        t = self.peek()
        if self.accept("*"):
            return self._loc(ast.Starred(value=self.parse_bitor(), ctx=ast.Load()), t)
        return self.parse_test()

    def parse_expr_or_assign(self) -> ast.stmt:
        t0 = self.peek()
        first = self.parse_star_exprs(allow_yield=True)
        t = self.peek()
        if not self.nl_terminates() and t.kind == "OP" and t.value in _AUGOPS:
            self.advance()
            self._operand_follows()
            value = self.parse_star_exprs(allow_yield=True)
            node: ast.stmt = ast.AugAssign(
                target=cast(Any, _set_ctx(first, ast.Store(), self)),
                op=_AUGOPS[t.value](),
                value=value,
            )
            return self._loc(node, t0)
        if self.cont(":"):
            if t0.kind == "OP" and t0.value == "~":
                self.error(
                    "'~x:y{' is not a for loop", code="E008", hint="write 'for x in y{'", at=t0
                )
            self.advance()
            simple = 1 if isinstance(first, ast.Name) and not self.last_atom_parenthesized else 0
            annotation = self.parse_test()
            ann_value = self.parse_star_exprs(allow_yield=True) if self.accept_cont("=") else None
            node = ast.AnnAssign(
                target=cast(Any, _set_ctx(first, ast.Store(), self)),
                annotation=annotation,
                value=ann_value,
                simple=simple,
            )
            return self._loc(node, t0)
        if self.cont("="):
            targets = [first]
            rhs: ast.expr = first
            while self.accept_cont("="):
                self._operand_follows()
                rhs = self.parse_star_exprs(allow_yield=True)
                targets.append(rhs)
            targets.pop()
            node = ast.Assign(targets=[_set_ctx(x, ast.Store(), self) for x in targets], value=rhs)
            return self._loc(node, t0)
        if t0.kind == "OP" and t0.value == "~" and self.at("{"):
            self.error("'~x:y{' is not a for loop", code="E008", hint="write 'for x in y{'", at=t0)
        return self._loc(ast.Expr(value=first), t0)

    # ------------------------------------------------------------------ decorators / defs
    def parse_decorated(self) -> ast.stmt:
        decorators: list[ast.expr] = []
        t0 = self.peek()
        while self.at("@"):
            at_tok = self.advance()
            deco = self.parse_decorator(at_tok)
            decorators.append(deco)
            while self.at(";"):
                self.advance()
            nxt = self.peek()
            legacy_name = (
                deco.func.id
                if isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Name)
                and deco.func.id in _LEGACY_DECORATORS
                else None
            )
            if nxt.kind == "OP" and nxt.value == "{" and legacy_name is not None:
                self.error(
                    f"'@{legacy_name}(' is not PyDense",
                    code="E008",
                    hint="write 'def __init__(a,b){' for a constructor",
                    at=at_tok,
                )
            if nxt.kind == "NAME" and nxt.value not in ("def", "class", "async"):
                if isinstance(deco, ast.Name) and deco.id in _LEGACY_DECORATORS:
                    self.error(
                        f"'@{deco.id}' is not PyDense",
                        code="E008",
                        hint=_E008_HINT,
                        at=at_tok,
                    )
                self.error(
                    f"decorator must be followed by another '@', 'def', 'class' or 'async def', "
                    f"not {self._describe(nxt)}",
                    code="E004",
                    hint="a decorator is a name/attribute/call/subscript chain; "
                    "write @(expr) for anything else",
                )
        if self.at("def"):
            return self.parse_funcdef(decorators, False, t0)
        if self.at("async") and self.peek(1).value == "def":
            self.advance()
            return self.parse_funcdef(decorators, True, t0)
        if self.at("class"):
            return self.parse_classdef(decorators, t0)
        self.error("decorator must be followed by def or class", code="E004")

    def parse_decorator(self, at_tok: Token) -> ast.expr:
        t = self.peek()
        if t.kind == "OP" and t.value == "(":
            node = self.parse_atom()
        elif t.kind == "NAME" and t.value not in HARD_KEYWORDS:
            node = self._loc(ast.Name(id=self.advance().value, ctx=ast.Load()), t)
        elif t.kind == "OP" and t.value == "." and self.peek(1).kind == "NAME":
            node = self.parse_atom()
        else:
            self.error(
                f"bad decorator start {self._describe(t)}",
                code="E004",
                hint="a decorator is a name/attribute/call/subscript chain; "
                "write @(expr) for anything else",
            )
        node = self.parse_trailers(node)
        nxt = self.peek()
        if (
            nxt.kind == "OP"
            and nxt.value not in ("@",)
            and nxt.value in _BINOPS | _CMPOPS.keys() | {"?", "if"}
        ):
            self.error(
                "decorator must be a name/attribute/call/subscript chain; write @(a or b) / @(a@b)",
                code="E004",
                hint="parenthesize the decorator expression",
                at=nxt,
            )
        if nxt.kind == "NAME" and nxt.value in ("or", "and", "if", "not", "is", "in"):
            self.error(
                "decorator must be a name/attribute/call/subscript chain; write @(a or b)",
                code="E004",
                hint="parenthesize the decorator expression",
                at=nxt,
            )
        return node

    def parse_funcdef(self, decorators: list[ast.expr], is_async: bool, t0: Token) -> ast.stmt:
        def_tok = self.expect("def")
        bang = self.accept("!")
        name_tok = self.peek()
        name = self.expect_name()
        tps = self.parse_type_params()
        is_method = self.scopes[-1] == "class"
        if bang and not is_method:
            self.error(
                "'def!' is only meaningful for methods (directly inside a class body)",
                code="E007",
                hint="write 'def' here",
                at=def_tok,
            )
        receiver = None if bang or not is_method else receiver_for(decorators)
        self.expect("(", hint="a def needs a parameter list: def name(params){")
        with self.bracket():
            args, first_written = self.parse_parameters(")", receiver)
        self.expect(")")
        if (
            is_method
            and receiver is not None
            and first_written is not None
            and first_written in RECEIVER_ALIASES
        ):
            self.warn(
                "W002",
                f"'{receiver}' was inserted in front of parameter {first_written!r}",
                name_tok,
                f"write 'def!{name}(...)' if {first_written!r} is the receiver, "
                f"or name it {receiver}",
            )
        returns = None
        if self.accept("->"):
            returns = self.parse_test()
        self.scopes.append("def")
        body = self.parse_block()
        self.scopes.pop()
        cls = ast.AsyncFunctionDef if is_async else ast.FunctionDef
        kw: dict[str, Any] = dict(
            name=name,
            args=args,
            body=body,
            decorator_list=decorators,
            returns=returns,
            type_comment=None,
        )
        if PY >= (3, 12):
            kw["type_params"] = tps
        return self._loc(cls(**kw), t0)

    def parse_parameters(
        self, closer: str, receiver: str | None
    ) -> tuple[ast.arguments, str | None]:
        """Parse a parameter list up to `closer`.

        Returns (arguments, first_written_positional_name).
        """
        posonly: list[ast.arg] = []
        regular: list[ast.arg] = []
        defaults: list[ast.expr] = []
        kwonly: list[ast.arg] = []
        kw_defaults: list[ast.expr | None] = []
        vararg = kwarg = None
        seen_star = False
        allow_ann = closer == ")"
        first_written: str | None = None
        while not self.at(closer):
            t = self.peek()
            if kwarg is not None:
                self.error("no parameter may follow **kwargs", at=t)
            if self.accept("/"):
                if seen_star or posonly:
                    self.error("'/' must come before '*' and may appear only once", at=t)
                if not regular:
                    self.error("at least one parameter must precede '/'", at=t)
                posonly, regular = regular, []
            elif self.accept("**"):
                kwarg = self.parse_param(allow_ann)
            elif self.accept("*"):
                if seen_star or kwonly or vararg is not None:
                    self.error("only one '*' parameter is allowed", at=t)
                seen_star = True
                if not (self.at(",") or self.at(closer)):
                    vararg = self.parse_param(allow_ann, star=True)
            else:
                p = self.parse_param(allow_ann)
                default = None
                if self.accept("="):
                    default = self.parse_test()
                if seen_star:
                    kwonly.append(p)
                    kw_defaults.append(default)
                else:
                    if first_written is None:
                        first_written = p.arg
                    regular.append(p)
                    if default is not None:
                        defaults.append(default)
                    elif defaults:
                        self.error(
                            "parameter without a default follows a parameter with a default", at=t
                        )
            if not self.accept(","):
                break
        if seen_star and vararg is None and not kwonly:
            self.error("named parameters must follow a bare '*'")
        if receiver is not None:
            allpos = posonly + regular
            if allpos and allpos[0].arg in RECEIVER_NAMES:
                pass  # written explicitly - never doubled
            else:
                recv = ast.arg(arg=receiver, annotation=None, type_comment=None)
                if posonly:
                    posonly.insert(0, recv)
                else:
                    regular.insert(0, recv)
        args = ast.arguments(
            posonlyargs=posonly,
            args=regular,
            vararg=vararg,
            kwonlyargs=kwonly,
            kw_defaults=kw_defaults,
            kwarg=kwarg,
            defaults=defaults,
        )
        return args, first_written

    def parse_param(self, allow_ann: bool, star: bool = False) -> ast.arg:
        t = self.peek()
        name = self.expect_name()
        ann = None
        if allow_ann and self.accept(":"):
            if star and self.at("*"):  # PEP 646: *args: *Ts
                st = self.advance()
                ann = self._loc(ast.Starred(value=self.parse_bitor(), ctx=ast.Load()), st)
            else:
                ann = self.parse_test()
        return self._loc(ast.arg(arg=name, annotation=ann, type_comment=None), t)

    def parse_classdef(self, decorators: list[ast.expr], t0: Token) -> ast.ClassDef:
        self.expect("class")
        name = self.expect_name()
        tps = self.parse_type_params()
        bases: list[ast.expr] = []
        keywords: list[ast.keyword] = []
        if self.accept("("):
            with self.bracket():
                bases, keywords = self.parse_call_args()
            self.expect(")")
        self.scopes.append("class")
        body = self.parse_block()
        self.scopes.pop()
        kw: dict[str, Any] = dict(
            name=name, bases=bases, keywords=keywords, body=body, decorator_list=decorators
        )
        if PY >= (3, 12):
            kw["type_params"] = tps
        return self._loc(ast.ClassDef(**kw), t0)

    # ------------------------------------------------------------------ compound statements
    def parse_else_block(self) -> list[ast.stmt]:
        if self.at("else"):
            self.advance()
            return self.parse_block()
        return []

    def parse_if(self) -> ast.If:
        t0 = self.expect("if")
        return self._parse_if_rest(t0)

    def _parse_if_rest(self, t0: Token) -> ast.If:
        test = self.parse_namedexpr()
        body = self.parse_block()
        if self.at("elif"):
            t1 = self.advance()
            orelse: list[ast.stmt] = [self._parse_if_rest(t1)]
        else:
            orelse = self.parse_else_block()
        return self._loc(ast.If(test=test, body=body, orelse=orelse), t0)

    def parse_while(self) -> ast.While:
        t0 = self.expect("while")
        test = self.parse_namedexpr()
        body = self.parse_block()
        return self._loc(ast.While(test=test, body=body, orelse=self.parse_else_block()), t0)

    def parse_for(self, is_async: bool, t0: Token) -> ast.stmt:
        self.expect("for")
        target = self.parse_target_list(stop={"in"})
        self.expect("in", hint="for TARGET in ITERABLE{")
        it = self.parse_star_exprs(allow_yield=False, header=True)
        body = self.parse_block()
        orelse = self.parse_else_block()
        cls = ast.AsyncFor if is_async else ast.For
        return self._loc(
            cls(target=target, iter=it, body=body, orelse=orelse, type_comment=None), t0
        )

    def parse_target_list(self, stop: set[str]) -> ast.expr:
        t = self.peek()
        first = self.parse_bitor_or_star()
        if not self.at(","):
            return _set_ctx(first, ast.Store(), self)
        elts = [first]
        while self.accept(","):
            nxt = self.peek()
            if (nxt.kind in ("OP", "NAME") and nxt.value in stop) or nxt.value in (
                "=",
                "{",
                ")",
                "]",
            ):
                break
            elts.append(self.parse_bitor_or_star())
        return _set_ctx(self._loc(ast.Tuple(elts=elts, ctx=ast.Store()), t), ast.Store(), self)

    def parse_bitor_or_star(self) -> ast.expr:
        t = self.peek()
        if self.accept("*"):
            return self._loc(ast.Starred(value=self.parse_bitor(), ctx=ast.Load()), t)
        return self.parse_bitor()

    def parse_try(self) -> ast.stmt:
        t0 = self.expect("try")
        body = self.parse_block()
        handlers: list[ast.ExceptHandler] = []
        star: bool | None = None
        while self.at("except"):
            ht = self.advance()
            is_star = self.accept("*")
            if is_star and PY < (3, 11):
                self.error("'except*' needs Python 3.11+", at=ht)
            if star is None:
                star = is_star
            elif star != is_star:
                self.error(
                    "all handlers of a try must be except or except*",
                    code="E009",
                    hint="use the same handler form throughout",
                    at=ht,
                )
            typ = name = None
            if not self.at("{") and not (self.at(":") and self.peek(1).value == "{"):
                typ = self.parse_test()
                if self.accept("as"):
                    name = self.expect_name()
            elif is_star:
                self.error("'except*' needs an exception type", at=ht)
            hbody = self.parse_block()
            handlers.append(self._loc(ast.ExceptHandler(type=typ, name=name, body=hbody), ht))
        orelse = self.parse_else_block()
        finalbody: list[ast.stmt] = []
        if self.accept("finally"):
            finalbody = self.parse_block()
        if not handlers and not finalbody:
            if self.at("!"):
                self.error(
                    "'!E:e{' is not an except clause", code="E008", hint="write 'except E as e{'"
                )
            if self.at(":") and self.peek(1).value == "{":
                self.error("'}:{' is not an else block", code="E008", hint="write }else{")
            self.error("try needs at least one except or a finally block")
        if orelse and not handlers:
            self.error("try/else needs at least one except handler")
        cls: Any = ast.TryStar if star else ast.Try  # type: ignore[attr-defined]
        return self._loc(cls(body=body, handlers=handlers, orelse=orelse, finalbody=finalbody), t0)

    def parse_with(self, is_async: bool, t0: Token) -> ast.stmt:
        self.expect("with")
        items: list[ast.withitem] | None = None
        if self.at("("):
            try:
                with self.speculate():
                    self.advance()
                    with self.bracket():
                        items = [self.parse_withitem()]
                        while self.accept(","):
                            if self.at(")"):
                                break
                            items.append(self.parse_withitem())
                    self.expect(")")
                    if not (self.at("{") or (self.at(":") and self.peek(1).value == "{")):
                        self.error("not a parenthesized with-item list")
            except _Rewind:
                items = None
        if items is None:
            items = [self.parse_withitem()]
            while self.accept(","):
                items.append(self.parse_withitem())
        body = self.parse_block()
        cls = ast.AsyncWith if is_async else ast.With
        return self._loc(cls(items=items, body=body, type_comment=None), t0)

    def parse_withitem(self) -> ast.withitem:
        ctx = self.parse_test()
        var = None
        if self.accept("as"):
            var = _set_ctx(self.parse_target_atom(), ast.Store(), self)
        return ast.withitem(context_expr=ctx, optional_vars=var)

    def parse_target_atom(self) -> ast.expr:
        return self.parse_bitor_or_star()

    # ------------------------------------------------------------------ match
    def _try_match(self, t0: Token) -> ast.Match | None:
        nxt = self.peek(1)
        if nxt.kind == "EOF" or (
            nxt.kind == "OP"
            and nxt.value in ("=", ":", ";", "}", ")", "]", ",", "?", ".")
            or nxt.value in _AUGOPS
        ):
            if not (nxt.kind == "OP" and nxt.value == "." and self.peek(2).kind == "NAME"):
                return None
            # `match.x` could be an attribute of a variable named match, or a value pattern subject.
        if nxt.kind == "OP" and nxt.value in _BINOPS and nxt.value not in ("-", "+", "~", "*"):
            return None
        if nxt.kind == "OP" and nxt.value in _CMPOPS:
            return None
        if nxt.kind == "NAME" and nxt.value in ("and", "or", "if", "is", "in", "else"):
            return None
        try:
            with self.speculate():
                subject, open_tok = self._parse_match_header()
        except _Rewind:
            return None
        # Committed: errors inside the match body are real errors, not speculation failures.
        return self._parse_match_cases(t0, subject, open_tok)

    def _parse_match_header(self) -> tuple[ast.expr, Token]:
        self.expect("match")
        subject = self.parse_star_exprs(allow_yield=False, header=True)
        if self.at(":") and self.peek(1).value == "{":
            self.advance()
        if not self.at("{"):
            self.error("expected '{' after match subject")
        open_tok = self.advance()
        if not self.at("case"):
            self.error("expected 'case' inside match block")
        return subject, open_tok

    def parse_match(self, t0: Token) -> ast.Match:
        subject, open_tok = self._parse_match_header()
        return self._parse_match_cases(t0, subject, open_tok)

    def _parse_match_cases(self, t0: Token, subject: ast.expr, open_tok: Token) -> ast.Match:
        self.open_blocks.append(open_tok)
        cases: list[ast.match_case] = []
        while not self.at("}"):
            if self.peek().kind == "EOF":
                self._eof_error()
            if self.accept(";"):
                continue
            ct = self.expect("case")
            pattern = self.parse_patterns_top()
            guard = None
            if self.accept("if"):
                guard = self.parse_namedexpr()
            body = self.parse_block()
            cases.append(self._loc(ast.match_case(pattern=pattern, guard=guard, body=body), ct))
        self.expect("}")
        self.open_blocks.pop()
        return self._loc(ast.Match(subject=subject, cases=cases), t0)

    # ------------------------------------------------------------------ patterns
    def parse_patterns_top(self) -> ast.pattern:
        t = self.peek()
        first = self.parse_pattern()
        if not self.at(","):
            return first
        pats = [first]
        while self.accept(","):
            if self.at("{") or self.at("if") or self.at(":"):
                break
            pats.append(self.parse_pattern())
        return self._loc(ast.MatchSequence(patterns=pats), t)

    def parse_pattern(self) -> ast.pattern:
        t = self.peek()
        pat = self.parse_or_pattern()
        if self.accept("as"):
            name = self.expect_name()
            pat = self._loc(ast.MatchAs(pattern=pat, name=name), t)
        return pat

    def parse_or_pattern(self) -> ast.pattern:
        t = self.peek()
        pats = [self.parse_closed_pattern()]
        while self.accept("|"):
            pats.append(self.parse_closed_pattern())
        return pats[0] if len(pats) == 1 else self._loc(ast.MatchOr(patterns=pats), t)

    def parse_closed_pattern(self) -> ast.pattern:
        t = self.peek()
        if t.kind == "OP":
            if t.value == "(":
                self.advance()
                with self.bracket():
                    if self.at(")"):
                        self.advance()
                        return self._loc(ast.MatchSequence(patterns=[]), t)
                    first = self.parse_pattern()
                    if self.at(","):
                        pats = [first]
                        while self.accept(","):
                            if self.at(")"):
                                break
                            pats.append(self.parse_pattern())
                        self.expect(")")
                        return self._loc(ast.MatchSequence(patterns=pats), t)
                self.expect(")")
                return first
            if t.value == "[":
                self.advance()
                pats = []
                with self.bracket():
                    while not self.at("]"):
                        pats.append(self.parse_pattern())
                        if not self.accept(","):
                            break
                self.expect("]")
                return self._loc(ast.MatchSequence(patterns=pats), t)
            if t.value == "{":
                self.advance()
                keys: list[ast.expr] = []
                pats = []
                rest = None
                with self.bracket():
                    while not self.at("}"):
                        if self.accept("**"):
                            rest = self.expect_name()
                        else:
                            keys.append(self.parse_pattern_key())
                            self.expect(":")
                            pats.append(self.parse_pattern())
                        if not self.accept(","):
                            break
                self.expect("}")
                return self._loc(ast.MatchMapping(keys=keys, patterns=pats, rest=rest), t)
            if t.value == "*":
                self.advance()
                name = self.expect_name()
                return self._loc(ast.MatchStar(name=None if name == "_" else name), t)
            if t.value == "-":
                return self._loc(ast.MatchValue(value=self.parse_pattern_number()), t)
            if t.value == "." and self.peek(1).kind == "NAME":
                self.advance()
                node: ast.expr = self._loc(
                    ast.Attribute(
                        value=ast.Name(id="self", ctx=ast.Load()),
                        attr=self.expect_name(),
                        ctx=ast.Load(),
                    ),
                    t,
                )
                while self.at(".") and self.peek(1).kind == "NAME":
                    self.advance()
                    node = ast.Attribute(value=node, attr=self.expect_name(), ctx=ast.Load())
                if self.at("("):
                    return self.parse_class_pattern(node, t)
                return self._loc(ast.MatchValue(value=node), t)
        if t.kind == "STRING":
            return self._loc(ast.MatchValue(value=self.parse_strings()), t)
        if t.kind == "NUMBER":
            return self._loc(ast.MatchValue(value=self.parse_pattern_number()), t)
        if t.kind == "NAME":
            if t.value in _SINGLETONS:
                self.advance()
                return self._loc(ast.MatchSingleton(value=_SINGLETONS[t.value]), t)
            name = self.expect_name()
            if self.at(".") and self.peek(1).kind == "NAME":
                node = self._loc(ast.Name(id=name, ctx=ast.Load()), t)
                while self.at(".") and self.peek(1).kind == "NAME":
                    self.advance()
                    node = ast.Attribute(value=node, attr=self.expect_name(), ctx=ast.Load())
                if self.at("("):
                    return self.parse_class_pattern(node, t)
                return self._loc(ast.MatchValue(value=node), t)
            if self.at("("):
                return self.parse_class_pattern(self._loc(ast.Name(id=name, ctx=ast.Load()), t), t)
            return self._loc(ast.MatchAs(pattern=None, name=None if name == "_" else name), t)
        self.error(f"unexpected {self._describe(t)} in pattern")

    def parse_pattern_key(self) -> ast.expr:
        t = self.peek()
        if t.kind == "STRING":
            return self.parse_strings()
        if t.kind == "NUMBER" or self.at("-"):
            return self.parse_pattern_number()
        if t.kind == "NAME":
            if t.value in _SINGLETONS:
                self.advance()
                return self._loc(ast.Constant(value=_SINGLETONS[t.value]), t)
            node: ast.expr = self._loc(ast.Name(id=self.expect_name(), ctx=ast.Load()), t)
            while self.accept("."):
                node = ast.Attribute(value=node, attr=self.expect_name(), ctx=ast.Load())
            return node
        if t.kind == "OP" and t.value == "." and self.peek(1).kind == "NAME":
            self.advance()
            node = self._loc(
                ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr=self.expect_name(),
                    ctx=ast.Load(),
                ),
                t,
            )
            while self.accept("."):
                node = ast.Attribute(value=node, attr=self.expect_name(), ctx=ast.Load())
            return node
        self.error("bad mapping pattern key")

    def parse_pattern_number(self) -> ast.expr:
        t = self.peek()
        neg = self.accept("-")
        nt = self.advance()
        if nt.kind != "NUMBER":
            self.error("expected a number in pattern", at=nt)
        node: ast.expr = self._loc(ast.Constant(value=self._number(nt)), nt)
        if neg:
            node = self._loc(ast.UnaryOp(op=ast.USub(), operand=node), t)
        if self.at("+") or self.at("-"):
            op = ast.Add() if self.advance().value == "+" else ast.Sub()
            t2 = self.advance()
            if t2.kind != "NUMBER":
                self.error("expected an imaginary number after +/- in pattern", at=t2)
            node = self._loc(
                ast.BinOp(left=node, op=op, right=ast.Constant(value=self._number(t2))), t
            )
        return node

    def parse_class_pattern(self, cls_node: ast.expr, t: Token) -> ast.pattern:
        self.expect("(")
        pats: list[ast.pattern] = []
        kwd_attrs: list[str] = []
        kwd_pats: list[ast.pattern] = []
        with self.bracket():
            while not self.at(")"):
                if self.peek().kind == "NAME" and self.peek(1).value == "=":
                    kwd_attrs.append(self.expect_name())
                    self.expect("=")
                    kwd_pats.append(self.parse_pattern())
                else:
                    if kwd_attrs:
                        self.error("positional patterns follow keyword patterns")
                    pats.append(self.parse_pattern())
                if not self.accept(","):
                    break
        self.expect(")")
        return self._loc(
            ast.MatchClass(cls=cls_node, patterns=pats, kwd_attrs=kwd_attrs, kwd_patterns=kwd_pats),
            t,
        )

    # ------------------------------------------------------------------ expressions
    def parse_star_exprs(self, allow_yield: bool, header: bool = False) -> ast.expr:
        """Comma list -> expr or Tuple (statement level, return, RHS, for-iter, subject).

        With ``header=True`` (for-iter, match subject) a `{` after a trailing comma is the block
        unless its matching `}` is itself followed by `{` (then it was a display).
        """
        t = self.peek()
        if allow_yield and self.at("yield"):
            return self.parse_yield()
        first = self.parse_star_or_namedexpr()
        if not self.cont(","):
            return first
        elts = [first]
        while self.accept_cont(","):
            if self.nl_terminates() or not self.starts_expr(self.peek()):
                break
            if header and self.at("{") and not self._brace_is_display():
                break
            elts.append(self.parse_star_or_namedexpr())
        return self._loc(ast.Tuple(elts=elts, ctx=ast.Load()), t)

    def _brace_is_display(self) -> bool:
        """At a `{`: True when its matching `}` is followed by another `{` (a display)."""
        depth = 0
        i = self._skip_nl(self.i)
        while i < len(self.toks):
            tok = self.toks[i]
            if tok.kind == "OP" and tok.value == "{":
                depth += 1
            elif tok.kind == "OP" and tok.value == "}":
                depth -= 1
                if depth == 0:
                    nxt = self._skip_nl(i + 1)
                    return self.toks[nxt].kind == "OP" and self.toks[nxt].value == "{"
            elif tok.kind == "EOF":
                return False
            i += 1
        return False

    def parse_yield(self) -> ast.expr:
        t = self.expect("yield")
        if self.accept_cont("from"):
            return self._loc(ast.YieldFrom(value=self.parse_test()), t)
        if self.optional_expr_follows() and not (self.at(")") or self.at("]") or self.at("}")):
            return self._loc(ast.Yield(value=self.parse_star_exprs(allow_yield=False)), t)
        return self._loc(ast.Yield(value=None), t)

    def parse_star_or_namedexpr(self) -> ast.expr:
        t = self.peek()
        if self.accept("*"):
            return self._loc(ast.Starred(value=self.parse_bitor(), ctx=ast.Load()), t)
        return self.parse_namedexpr()

    def parse_namedexpr(self) -> ast.expr:
        t = self.peek()
        node = self.parse_test()
        if self.cont(":="):
            self.advance()
            if not isinstance(node, ast.Name):
                self.error("the target of ':=' must be a name", at=t)
            value = self.parse_test()
            return self._loc(
                ast.NamedExpr(
                    target=cast(ast.Name, _set_ctx(node, ast.Store(), self)), value=value
                ),
                t,
            )
        return node

    def parse_test(self) -> ast.expr:
        """expression: lambda | disjunction '?' disjunction ':' expression | disjunction."""
        t = self.peek()
        if t.kind == "NAME" and t.value == "lambda":
            self.advance()
            self._operand_follows()
            with self.bracket():
                args, _ = self.parse_parameters(":", None)
            self.expect(":", hint="lambda PARAMS:BODY")
            self.scopes.append("def")
            try:
                body = self.parse_test()
            finally:
                self.scopes.pop()
            return self._loc(ast.Lambda(args=args, body=body), t)
        node = self.parse_or()
        if self.cont("?"):
            self.advance()
            if self.at("?"):
                self.error("'??' is not PyDense", code="E008", hint="the ternary is 'cond?a:b'")
            self._operand_follows()
            body = self.parse_or()
            self.expect(":", hint="the ternary is 'cond?a:b'")
            self._operand_follows()
            orelse = self.parse_test()
            return self._loc(ast.IfExp(test=node, body=body, orelse=orelse), t)
        if self.cont("if"):
            # Python spelling `a if c else b` accepted on input.
            self.advance()
            test = self.parse_or()
            self.expect("else", hint="'a if c else b' needs its else; or write 'c?a:b'")
            orelse = self.parse_test()
            return self._loc(ast.IfExp(test=test, body=node, orelse=orelse), t)
        return node

    def parse_or(self) -> ast.expr:
        t = self.peek()
        node = self.parse_and()
        if self.cont("or"):
            values = [node]
            while self.accept_cont("or"):
                self._operand_follows()
                values.append(self.parse_and())
            return self._loc(ast.BoolOp(op=ast.Or(), values=values), t)
        return node

    def parse_and(self) -> ast.expr:
        t = self.peek()
        node = self.parse_not()
        if self.cont("and"):
            values = [node]
            while self.accept_cont("and"):
                self._operand_follows()
                values.append(self.parse_not())
            return self._loc(ast.BoolOp(op=ast.And(), values=values), t)
        return node

    def parse_not(self) -> ast.expr:
        t = self.peek()
        if t.kind == "NAME" and t.value == "not":
            self.advance()
            return self._loc(ast.UnaryOp(op=ast.Not(), operand=self.parse_not()), t)
        return self.parse_comparison()

    def parse_comparison(self) -> ast.expr:
        t0 = self.peek()
        node = self.parse_bitor()
        ops: list[ast.cmpop] = []
        comps: list[ast.expr] = []
        while not self.nl_terminates():
            t = self.peek()
            if t.kind == "OP" and t.value in _CMPOPS:
                self.advance()
                ops.append(_CMPOPS[t.value]())
            elif t.kind == "NAME" and t.value == "in":
                self.advance()
                ops.append(ast.In())
            elif t.kind == "NAME" and t.value == "not" and self.peek(1).value == "in":
                self.advance()
                self.advance()
                ops.append(ast.NotIn())
            elif t.kind == "NAME" and t.value == "is":
                self.advance()
                ops.append(ast.IsNot() if self.accept("not") else ast.Is())
            else:
                break
            self._operand_follows()
            comps.append(self.parse_bitor())
        if ops:
            return self._loc(ast.Compare(left=node, ops=ops, comparators=comps), t0)
        return node

    def _operand_follows(self) -> None:
        """After an operator: the operand must be on the same line (SPEC 6.6)."""
        if self.nl_terminates():
            self.error(
                "the expression ends at this line break",
                hint="put the operand on the same line or bracket the whole expression",
            )

    def _binary_level(self, sub: Callable[[], ast.expr], ops: tuple[str, ...]) -> ast.expr:
        t0 = self.peek()
        node = sub()
        while not self.nl_terminates():
            t = self.peek()
            if t.kind == "OP" and t.value in ops:
                self.advance()
                self._operand_follows()
                if t.value == "@":
                    nxt = self.peek()
                    if nxt.kind == "NAME" and nxt.value in ("is", "in", "aw", "not"):
                        word = {"aw": "await"}.get(nxt.value, nxt.value)
                        self.error(
                            f"'@{nxt.value}' is not PyDense",
                            code="E008",
                            hint=f"write '{word}' as in Python",
                            at=t,
                        )
                if t.value in ("&", "|") and self.at(t.value):
                    self.error(
                        f"'{t.value * 2}' is not PyDense",
                        code="E008",
                        hint="write 'and' / 'or'",
                        at=t,
                    )
                node = self._loc(ast.BinOp(left=node, op=_BINOPS[t.value](), right=sub()), t0)
            else:
                break
        return node

    def parse_bitor(self) -> ast.expr:
        return self._binary_level(self.parse_bitxor, ("|",))

    def parse_bitxor(self) -> ast.expr:
        return self._binary_level(self.parse_bitand, ("^",))

    def parse_bitand(self) -> ast.expr:
        return self._binary_level(self.parse_shift, ("&",))

    def parse_shift(self) -> ast.expr:
        return self._binary_level(self.parse_arith, ("<<", ">>"))

    def parse_arith(self) -> ast.expr:
        return self._binary_level(self.parse_term, ("+", "-"))

    def parse_term(self) -> ast.expr:
        return self._binary_level(self.parse_factor, ("*", "/", "//", "%", "@"))

    def parse_factor(self) -> ast.expr:
        t = self.peek()
        if t.kind == "OP" and t.value in ("-", "+", "~"):
            self.advance()
            op = {"-": ast.USub, "+": ast.UAdd, "~": ast.Invert}[t.value]()
            return self._loc(ast.UnaryOp(op=op, operand=self.parse_factor()), t)
        return self.parse_power()

    def parse_power(self) -> ast.expr:
        t = self.peek()
        node = self.parse_await()
        if self.cont("**"):
            self.advance()
            self._operand_follows()
            return self._loc(ast.BinOp(left=node, op=ast.Pow(), right=self.parse_factor()), t)
        return node

    def parse_await(self) -> ast.expr:
        t = self.peek()
        if t.kind == "NAME" and t.value == "await":
            self.advance()
            return self._loc(ast.Await(value=self.parse_primary()), t)
        return self.parse_primary()

    def parse_primary(self) -> ast.expr:
        return self.parse_trailers(self.parse_atom())

    def parse_trailers(self, node: ast.expr) -> ast.expr:
        while not self.nl_terminates():
            t = self.peek()
            if t.kind != "OP":
                break
            if t.value == ".":
                nxt = self.peek(1)
                if nxt.kind != "NAME":
                    self.error(
                        f"expected an attribute name after '.' but found {self._describe(nxt)}",
                        at=nxt,
                    )
                self.advance()
                node = self._loc(
                    ast.Attribute(value=node, attr=self.advance().value, ctx=ast.Load()), t
                )
            elif t.value == "(":
                self.advance()
                with self.bracket():
                    args, keywords = self.parse_call_args()
                self.expect(")")
                node = ast.Call(func=node, args=args, keywords=keywords)
                node.lineno, node.col_offset = (
                    getattr(node.func, "lineno", t.line),
                    getattr(node.func, "col_offset", t.col),
                )
            elif t.value == "[":
                self.advance()
                with self.bracket():
                    sl = self.parse_subscript_list()
                self.expect("]")
                node = ast.Subscript(value=node, slice=sl, ctx=ast.Load())
                node.lineno, node.col_offset = (
                    getattr(node.value, "lineno", t.line),
                    getattr(node.value, "col_offset", t.col),
                )
            else:
                break
            self.last_atom_parenthesized = False
        return node

    def parse_call_args(self) -> tuple[list[ast.expr], list[ast.keyword]]:
        args: list[ast.expr] = []
        keywords: list[ast.keyword] = []
        bare_genexp = False
        while not self.at(")"):
            t = self.peek()
            if self.accept("**"):
                keywords.append(self._loc(ast.keyword(arg=None, value=self.parse_test()), t))
            elif self.accept("*"):
                if any(k.arg is None for k in keywords):
                    self.error(
                        "iterable argument unpacking follows keyword argument unpacking", at=t
                    )
                args.append(self._loc(ast.Starred(value=self.parse_test(), ctx=ast.Load()), t))
            elif (
                t.kind == "NAME"
                and t.value not in HARD_KEYWORDS
                and self.peek(1).value == "="
                and self.peek(1).kind == "OP"
            ):
                name = self.expect_name()
                self.expect("=")
                keywords.append(self._loc(ast.keyword(arg=name, value=self.parse_test()), t))
            else:
                if keywords:
                    self.error("positional argument follows keyword argument", at=t)
                e = self.parse_namedexpr()
                if self._at_comp_for():
                    e = self._loc(ast.GeneratorExp(elt=e, generators=self.parse_comp_for()), t)
                    bare_genexp = True
                args.append(e)
            if not self.accept(","):
                break
        if bare_genexp and len(args) + len(keywords) > 1:
            self.error("a generator expression argument needs parentheses next to other arguments")
        return args, keywords

    def parse_subscript_list(self) -> ast.expr:
        t = self.peek()
        items = [self.parse_slice_item()]
        trailing = False
        while self.accept(","):
            trailing = True
            if self.at("]"):
                break
            items.append(self.parse_slice_item())
            trailing = False
        if len(items) == 1 and not trailing and not isinstance(items[0], ast.Starred):
            return items[0]
        return self._loc(ast.Tuple(elts=items, ctx=ast.Load()), t)

    def parse_slice_item(self) -> ast.expr:
        t = self.peek()
        if self.accept("*"):
            return self._loc(ast.Starred(value=self.parse_bitor(), ctx=ast.Load()), t)
        lower = upper = step = None
        if not self.at(":"):
            lower = self.parse_namedexpr()
            if not self.at(":"):
                return lower
        self.expect(":")
        if not (self.at(":") or self.at("]") or self.at(",")):
            upper = self.parse_test()
        if self.accept(":"):
            if not (self.at("]") or self.at(",")):
                step = self.parse_test()
        return self._loc(ast.Slice(lower=lower, upper=upper, step=step), t)

    def _at_comp_for(self) -> bool:
        return self.at("for") or (self.at("async") and self.peek(1).value == "for")

    def parse_comp_for(self) -> list[ast.comprehension]:
        gens: list[ast.comprehension] = []
        while self._at_comp_for():
            is_async = 1 if self.accept("async") else 0
            self.expect("for")
            target = self.parse_target_list(stop={"in"})
            self.expect("in")
            it = self.parse_or()
            ifs: list[ast.expr] = []
            while self.at("if"):
                self.advance()
                ifs.append(self.parse_or())
            gens.append(ast.comprehension(target=target, iter=it, ifs=ifs, is_async=is_async))
        return gens

    def parse_atom(self) -> ast.expr:
        t = self.peek()
        self.last_atom_parenthesized = False
        if t.kind == "NUMBER":
            self.advance()
            return self._loc(ast.Constant(value=self._number(t)), t)
        if t.kind == "STRING":
            return self.parse_strings()
        if t.kind == "NAME":
            v = t.value
            if v in _SINGLETONS:
                self.advance()
                return self._loc(ast.Constant(value=_SINGLETONS[v]), t)
            if v == "yield":
                self.error("'yield' must be parenthesized here")
            if v == "lambda":
                return self.parse_test()
            if v in HARD_KEYWORDS:
                self.error(f"unexpected keyword {v!r}")
            self.advance()
            return self._loc(ast.Name(id=v, ctx=ast.Load()), t)
        if t.kind == "EOF":
            self._maybe_legacy_macro_error(t)
            if self.open_blocks:
                self._eof_error()
            self.error("expected an expression but found end of input")
        if t.kind != "OP":
            self.error(f"expected an expression but found {self._describe(t)}")
        v = t.value
        if v == ".":
            nxt = self.peek(1)
            if nxt.kind != "NAME":
                self.error(f"expected a name after '.' but found {self._describe(nxt)}", at=nxt)
            self.advance()
            attr = self.advance().value
            self_name = self._loc(ast.Name(id="self", ctx=ast.Load()), t)
            return self._loc(ast.Attribute(value=self_name, attr=attr, ctx=ast.Load()), t)
        if v == "...":
            self.advance()
            return self._loc(ast.Constant(value=Ellipsis), t)
        if v == "(":
            self.advance()
            with self.bracket():
                if self.at(")"):
                    self.advance()
                    return self._loc(ast.Tuple(elts=[], ctx=ast.Load()), t)
                if self.at("yield"):
                    node = self.parse_yield()
                    self.expect(")")
                    self.last_atom_parenthesized = True
                    return node
                first = self.parse_star_or_namedexpr()
                if self._at_comp_for():
                    if isinstance(first, ast.Starred):
                        self.error("iterable unpacking cannot be used in a comprehension", at=first)
                    node = self._loc(
                        ast.GeneratorExp(elt=first, generators=self.parse_comp_for()), t
                    )
                    self.expect(")")
                    return node
                if self.at(","):
                    elts = [first]
                    while self.accept(","):
                        if self.at(")"):
                            break
                        elts.append(self.parse_star_or_namedexpr())
                    self.expect(")")
                    return self._loc(ast.Tuple(elts=elts, ctx=ast.Load()), t)
            self.expect(")")
            self.last_atom_parenthesized = True
            return first
        if v == "[":
            self.advance()
            with self.bracket():
                if self.at("]"):
                    self.advance()
                    return self._loc(ast.List(elts=[], ctx=ast.Load()), t)
                first = self.parse_star_or_namedexpr()
                if self._at_comp_for():
                    if isinstance(first, ast.Starred):
                        self.error("iterable unpacking cannot be used in a comprehension", at=first)
                    node = self._loc(ast.ListComp(elt=first, generators=self.parse_comp_for()), t)
                    self.expect("]")
                    return node
                elts = [first]
                while self.accept(","):
                    if self.at("]"):
                        break
                    elts.append(self.parse_star_or_namedexpr())
            self.expect("]")
            return self._loc(ast.List(elts=elts, ctx=ast.Load()), t)
        if v == "{":
            return self.parse_brace_display()
        if v == "%" and self.peek(1).kind == "NAME":
            self.error(
                f"'%{self.peek(1).value}' macros are not PyDense",
                code="E008",
                hint="write the builtin's name (print, len, range, ...)",
                at=t,
            )
        if v in ("&", "|") and self.peek(1).value == v:
            self.error(f"'{v * 2}' is not PyDense", code="E008", hint="write 'and' / 'or'", at=t)
        if v == "?":
            self.error(
                "'?' here is not PyDense",
                code="E008",
                hint="the ternary is 'cond?a:b'; an if statement is 'if cond{'",
                at=t,
            )
        if v == "}":
            if not self.open_blocks and self.depth == 0:
                self.error(
                    "unmatched '}'", code="E002", hint="remove it or open a block before it", at=t
                )
            self.error("expected an expression before '}'", at=t)
        if v == "=" or v == ";" or v == ")" or v == "]":
            self._maybe_legacy_macro_error(t)
        self.error(f"expected an expression but found {self._describe(t)}")

    def _maybe_legacy_macro_error(self, t: Token) -> None:
        """`x=#T` lexes as `x=` + comment; detect legacy `#` macros for a better message."""
        prev = self.prev()
        gap = self.src[prev.end : t.pos] if t.pos >= prev.end else ""
        stripped = gap.lstrip(" \t")
        m = _LEGACY_MACRO_RE.match(stripped)
        if m:
            self.error(
                f"'{m.group(0)}' macros are not PyDense",
                code="E008",
                hint=LEGACY_MACRO_HINT,
                at=t,
            )

    def _number(self, t: Token) -> Any:
        try:
            return ast.literal_eval(t.value)
        except (SyntaxError, ValueError):
            self.error(f"invalid number literal {t.value!r}", at=t)

    def parse_brace_display(self) -> ast.expr:
        t = self.expect("{")
        with self.bracket():
            if self.at("}"):
                self.advance()
                self._last_close_display = True
                return self._loc(ast.Dict(keys=[], values=[]), t)
            if self.accept("**"):
                keys: list[ast.expr | None] = [None]
                values = [self.parse_bitor()]
                self._parse_dict_rest(keys, values)
                return self._loc(ast.Dict(keys=keys, values=values), t)
            first = self.parse_star_or_namedexpr()
            if self.at(":"):
                self.advance()
                value = self.parse_test()
                if self._at_comp_for():
                    node = self._loc(
                        ast.DictComp(key=first, value=value, generators=self.parse_comp_for()), t
                    )
                    self.expect("}")
                    return node
                keys = [first]
                values = [value]
                self._parse_dict_rest(keys, values)
                return self._loc(ast.Dict(keys=keys, values=values), t)
            if self._at_comp_for():
                if isinstance(first, ast.Starred):
                    self.error("iterable unpacking cannot be used in a comprehension", at=first)
                node = self._loc(ast.SetComp(elt=first, generators=self.parse_comp_for()), t)
                self.expect("}")
                return node
            elts = [first]
            while self.accept(","):
                if self.at("}"):
                    break
                elts.append(self.parse_star_or_namedexpr())
        self.expect("}")
        self._last_close_display = True
        return self._loc(ast.Set(elts=elts), t)

    def _parse_dict_rest(self, keys: list[ast.expr | None], values: list[ast.expr]) -> None:
        while self.accept(","):
            if self.at("}"):
                break
            if self.accept("**"):
                keys.append(None)
                values.append(self.parse_bitor())
            else:
                keys.append(self.parse_test())
                self.expect(":")
                values.append(self.parse_test())
        self.expect("}")
        self._last_close_display = True

    # ------------------------------------------------------------------ strings
    def parse_strings(self) -> ast.expr:
        t0 = self.peek()
        parts: list[Token] = []
        while self.peek().kind == "STRING" and not (parts and self.nl_terminates()):
            parts.append(self.advance())
        values = [self._string_value(p) for p in parts]
        if len(values) == 1:
            return self._loc(values[0], t0)
        if all(isinstance(v, ast.Constant) for v in values):
            consts = [v for v in values if isinstance(v, ast.Constant)]
            kinds = {type(v.value) for v in consts}
            if len(kinds) != 1:
                self.error("cannot mix bytes and str literals", at=t0)
            total: Any = consts[0].value
            for v in consts[1:]:
                total = total + v.value
            return self._loc(ast.Constant(value=total, kind=consts[0].kind), t0)
        pieces: list[ast.expr] = []
        for item in values:
            if isinstance(item, ast.JoinedStr):
                pieces.extend(item.values)
            elif isinstance(item, ast.Constant) and isinstance(item.value, bytes):
                self.error("cannot mix bytes and f-string literals", at=t0)
            else:
                pieces.append(item)
        return self._loc(ast.JoinedStr(values=_merge_constants(pieces)), t0)

    def _string_value(self, tok: Token) -> ast.expr:
        text = tok.value
        m = _NAME_RE.match(text)
        prefix = m.group().lower() if m and text[m.end()] in "'\"" else ""
        body_start = len(prefix)
        if "f" in prefix:
            q = text[body_start]
            quote = q * 3 if text.startswith(q * 3, body_start) else q
            body = text[body_start + len(quote) : -len(quote)]
            return parse_fstring_body(self, body, raw="r" in prefix, tok=tok)
        try:
            value = ast.literal_eval(text)
        except (ValueError, SyntaxError) as exc:
            self.error(f"invalid string literal: {exc}", at=tok)
        # CPython records kind='u' only for a lowercase u prefix.
        raw_prefix = m.group() if m and text[m.end()] in "'\"" else ""
        return ast.Constant(value=value, kind="u" if "u" in raw_prefix else None)


def _fix_locations(node: ast.AST, lineno: int, col: int) -> tuple[int, int]:
    """Fill in missing positions so that ``compile()`` accepts the tree.

    Nodes the parser positioned keep their start; missing starts inherit the parent's.  End
    positions are the
    maximum of the node's own start and its children's ends, so every range is valid.
    """
    positioned = "lineno" in node._attributes
    if positioned:
        if getattr(node, "lineno", None) is None:
            node.lineno, node.col_offset = lineno, col  # type: ignore[attr-defined]
        lineno, col = node.lineno, node.col_offset  # type: ignore[attr-defined]
    end: tuple[int, int] = (lineno, col)
    for child in ast.iter_child_nodes(node):
        c_end = _fix_locations(child, lineno, col)
        if c_end > end:
            end = c_end
    if positioned:
        end_line = getattr(node, "end_lineno", None)
        end_col = getattr(node, "end_col_offset", None)
        if end_line is None or end_col is None or (end_line, end_col) < (lineno, col):
            node.end_lineno, node.end_col_offset = end  # type: ignore[attr-defined]
        else:
            end = max(end, (end_line, end_col))
    return end


def parse(text: str, *, filename: str = "<dpy>") -> ast.Module:
    """Parse .dpy text into an ``ast.Module``."""
    return with_deep_recursion(
        Parser(text, filename, collect_warnings=False).parse_module, filename
    )


def parse_with_warnings(
    text: str, *, filename: str = "<dpy>"
) -> tuple[ast.Module, list[Diagnostic]]:
    p = Parser(text, filename, collect_warnings=True)
    mod = with_deep_recursion(p.parse_module, filename)
    return mod, sorted(p.warnings, key=lambda d: (d.lineno, d.col))
