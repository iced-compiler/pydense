"""Lexer for PyDense (.dpy) text — docs/SPEC.md section 2.

Produces NAME, NUMBER, STRING, OP, NEWLINE and EOF tokens.  Whitespace and comments are dropped.
A NEWLINE token is produced only when the newline occurs outside ``(`` ``)`` ``[`` ``]``; the parser
decides whether a newline inside ``{`` ``}`` matters (display vs block) because the lexer cannot
know.
String literals (including PEP 701 f-strings with nested quotes) are single tokens; their inner
structure is parsed later.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass

from .errors import PyDenseSyntaxError
from .rules import LEGACY_MACRO_ALTERNATION, LEGACY_MACRO_HINT
from .strings import _NAME_RE, _string_prefix_at, scan_string_at

HARD_KEYWORDS = frozenset(
    {
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield",
    }
)

_WORD_RE = re.compile(r"\w*", re.UNICODE)
_NUMBER_RE = re.compile(
    r"0[xX](?:_?[0-9a-fA-F])+|0[oO](?:_?[0-7])+|0[bB](?:_?[01])+"
    r"|(?:\d(?:_?\d)*)?\.\d(?:_?\d)*(?:[eE][+-]?\d(?:_?\d)*)?[jJ]?"
    r"|\d(?:_?\d)*\.(?!\.)(?:[eE][+-]?\d(?:_?\d)*)?[jJ]?"
    r"|\d(?:_?\d)*(?:[eE][+-]?\d(?:_?\d)*)?[jJ]?"
)
_OPS3 = ("**=", "//=", ">>=", "<<=", "...")
_OPS2 = (
    "**",
    "//",
    ">>",
    "<<",
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
)
_OPS1 = frozenset("+-*/%@&|^~<>()[]{},:;.=?!")
# a whole-line comment that is exactly a v0.2 macro (`#T`, `#np.array(x)`) is rejected, not skipped
_LEGACY_COMMENT_RE = re.compile(rf"#(?:{LEGACY_MACRO_ALTERNATION})(?:$|[^\w\s])")


@dataclass(slots=True)
class Token:
    kind: str  # NAME NUMBER STRING OP NEWLINE EOF
    value: str
    pos: int  # 0-based offset of the first character
    end: int  # offset just past the token
    line: int  # 1-based
    col: int  # 0-based

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Token({self.kind}, {self.value!r}, {self.line}:{self.col})"


class LineMap:
    """Maps character offsets to (line, col)."""

    def __init__(self, src: str) -> None:
        self.src = src
        self.starts = [0] + [i + 1 for i, ch in enumerate(src) if ch == "\n"]

    def position(self, pos: int) -> tuple[int, int]:
        idx = bisect.bisect_right(self.starts, pos) - 1
        return idx + 1, pos - self.starts[idx]

    def line_text(self, line: int) -> str:
        start = self.starts[line - 1] if 0 < line <= len(self.starts) else 0
        end = self.src.find("\n", start)
        return self.src[start:] if end == -1 else self.src[start:end]


def tokenize(src: str, filename: str = "<dpy>") -> list[Token]:
    """Tokenize .dpy text. Raises PyDenseSyntaxError on lexical errors."""
    lm = LineMap(src)
    toks: list[Token] = []
    i, n = 0, len(src)
    depth = 0  # ( and [ nesting; newlines inside are never significant

    def emit(kind: str, value: str, start: int, end: int) -> None:
        line, col = lm.position(start)
        toks.append(Token(kind, value, start, end, line, col))

    def err(msg: str, at: int, code: str = "E000", hint: str = "") -> PyDenseSyntaxError:
        line, col = lm.position(at)
        return PyDenseSyntaxError(
            msg,
            code=code,
            lineno=line,
            col=col,
            filename=filename,
            text=lm.line_text(line),
            hint=hint,
        )

    while i < n:
        c = src[i]
        if c == "\n":
            if depth == 0 and toks and toks[-1].kind != "NEWLINE":
                emit("NEWLINE", "\n", i, i + 1)
            i += 1
            continue
        if c in " \t\r\f\v":
            i += 1
            continue
        if c == "#":
            j = src.find("\n", i)
            comment = src[i : n if j == -1 else j]
            line_start = src.rfind("\n", 0, i) + 1
            if src[line_start:i].strip() == "" and _LEGACY_COMMENT_RE.match(comment):
                raise err(
                    f"'{comment.split()[0][:5]}' macros are not PyDense",
                    i,
                    code="E008",
                    hint=LEGACY_MACRO_HINT,
                )
            i = n if j == -1 else j
            continue
        if c == "\\":
            j = i + 1
            while j < n and src[j] in " \t\r":
                j += 1
            if j < n and src[j] == "\n":
                i = j + 1  # explicit line join
                continue
            if j >= n:
                i = j
                continue
            nxt = src[j]
            if j == i + 1 and (nxt == ":" or nxt == "_" or nxt.isalpha()):
                raise err(
                    "'\\' lambda shorthand is not PyDense",
                    i,
                    code="E008",
                    hint="write 'lambda a,b:a+b'",
                )
            raise err(
                "'\\' is only a line continuation in PyDense",
                i,
                code="E006",
                hint="put '\\' only at the end of a line",
            )
        if c in "'\"" or (c.isalpha() and _string_prefix_at(src, i) is not None):
            j = scan_string_at(src, i, lm, filename)
            emit("STRING", src[i:j], i, j)
            i = j
            continue
        m = _NAME_RE.match(src, i)
        if m or c.isidentifier():
            j = m.end() if m else i + 1
            # PEP 3131: continuation characters such as combining marks are valid identifier
            # characters but are not matched by \w; extend with str.isidentifier.
            while j < n:
                if src[j].isascii():
                    m2 = _WORD_RE.match(src, j)
                    if m2 is None or m2.end() == j:
                        break
                    j = m2.end()
                elif src[i : j + 1].isidentifier():
                    j += 1
                else:
                    break
            name = src[i:j]
            if not name.isascii():
                # e.g. `a²`: `²` is alphanumeric for \w but not an identifier character
                while j > i and not src[i:j].isidentifier():
                    j -= 1
                if j == i:
                    raise err(f"invalid character {src[i]!r}", i)
                name = unicodedata.normalize("NFKC", src[i:j])
            emit("NAME", name, i, j)
            i = j
            continue
        if c.isdigit() or (c == "." and src[i + 1 : i + 2].isdigit()):
            m = _NUMBER_RE.match(src, i)
            if not m:
                raise err(f"invalid number literal {src[i : i + 10]!r}", i)
            emit("NUMBER", m.group(), i, m.end())
            i = m.end()
            continue
        if src.startswith(_OPS3, i):
            op = src[i : i + 3]
        elif src.startswith(_OPS2, i):
            op = src[i : i + 2]
        elif c in _OPS1:
            op = c
        elif c == "$":
            raise err(
                "'$n' positional shorthand is not PyDense",
                i,
                code="E008",
                hint="use the parameter's name",
            )
        elif c == "`":
            raise err("unexpected character '`'", i)
        else:
            raise err(f"unexpected character {c!r}", i)
        if op in ("(", "["):
            depth += 1
        elif op in (")", "]"):
            depth = max(0, depth - 1)
        emit("OP", op, i, i + len(op))
        i += len(op)
    if toks and toks[-1].kind == "NEWLINE":
        pass
    emit("EOF", "", n, n)
    return toks
