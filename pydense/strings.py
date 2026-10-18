"""String and f-string literal handling shared by the lexer and the parser (docs/SPEC.md section 2).

The lexer uses the scanners to find the end of a (possibly prefixed) string literal, PEP 701
f-strings included; the parser uses the field functions to turn an f-string body into
``JoinedStr`` nodes, parsing each replacement field as a PyDense expression with a sub-parser.
"""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING, Any, cast

from .errors import PyDenseSyntaxError

if TYPE_CHECKING:  # pragma: no cover - typing only (avoids a lexer <-> strings import cycle)
    from .lexer import LineMap, Token
    from .parser import Parser

_NAME_RE = re.compile(r"[^\W\d]\w*", re.UNICODE)
STRING_PREFIXES = frozenset({"", "r", "u", "b", "br", "rb", "f", "fr", "rf"})


# ---------------------------------------------------------------------------- scanning (lexer side)


def _scan_plain_string(src: str, i: int, quote: str, start: int, lm: LineMap, filename: str) -> int:
    n = len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if src.startswith(quote, i):
            return i + len(quote)
        if c == "\n" and len(quote) == 1:
            break
        i += 1
    line, col = lm.position(start)
    raise PyDenseSyntaxError(
        "unterminated string literal",
        code="E000",
        lineno=line,
        col=col,
        filename=filename,
        text=lm.line_text(line),
        hint="close the quote",
    )


def _scan_fstring(src: str, i: int, quote: str, start: int, lm: LineMap, filename: str) -> int:
    n = len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            if src.startswith("\\N{", i):  # \N{NAME} escape: the braces are not a field
                close = src.find("}", i + 3)
                i = close + 1 if close != -1 else i + 3
                continue
            i += 1 if src[i + 1 : i + 2] in ("{", "}") else 2
            continue
        if src.startswith(quote, i):
            return i + len(quote)
        if c == "{":
            if src.startswith("{{", i):
                i += 2
                continue
            i = scan_field(src, i + 1, start, lm, filename)
            continue
        if c == "}":
            i += 2 if src.startswith("}}", i) else 1
            continue
        if c == "\n" and len(quote) == 1:
            break
        i += 1
    line, col = lm.position(start)
    raise PyDenseSyntaxError(
        "unterminated f-string literal",
        code="E000",
        lineno=line,
        col=col,
        filename=filename,
        text=lm.line_text(line),
        hint="close the quote",
    )


def _string_prefix_at(src: str, i: int) -> tuple[str, int] | None:
    """If a (possibly prefixed) string literal starts at i, return (prefix_lower, quote_pos)."""
    c = src[i : i + 1]
    if c in ("'", '"'):
        return "", i
    m = _NAME_RE.match(src, i)
    if m and src[m.end() : m.end() + 1] in ("'", '"') and m.group().lower() in STRING_PREFIXES:
        return m.group().lower(), m.end()
    return None


def scan_string_at(src: str, i: int, lm: LineMap, filename: str) -> int:
    """src[i] starts a (possibly prefixed) string literal. Returns the offset just past it."""
    start = i
    pq = _string_prefix_at(src, i)
    if pq is None:
        line, col = lm.position(i)
        raise PyDenseSyntaxError("bad string literal", lineno=line, col=col, filename=filename)
    prefix, i = pq
    q = src[i]
    quote = q * 3 if src.startswith(q * 3, i) else q
    j = i + len(quote)
    if "f" in prefix:
        return _scan_fstring(src, j, quote, start, lm, filename)
    return _scan_plain_string(src, j, quote, start, lm, filename)


def scan_field(src: str, i: int, start: int, lm: LineMap, filename: str) -> int:
    """i is just past the '{' of an f-string replacement field. Returns the offset past its '}'."""
    n = len(src)
    depth = 0
    while i < n:
        c = src[i]
        if c in "([{":
            depth += 1
            i += 1
        elif c in ")]}":
            if depth == 0:
                if c == "}":
                    return i + 1
                line, col = lm.position(i)
                raise PyDenseSyntaxError(
                    "unbalanced bracket in f-string replacement field",
                    lineno=line,
                    col=col,
                    filename=filename,
                    text=lm.line_text(line),
                )
            depth -= 1
            i += 1
        elif _string_prefix_at(src, i) is not None:
            i = scan_string_at(src, i, lm, filename)
        elif c == "!" and depth == 0 and src[i + 1 : i + 2] != "=":
            i += 2
        elif c == ":" and depth == 0:
            return _scan_spec(src, i + 1, start, lm, filename)
        elif c == "#":  # PEP 701: a comment runs to the end of the line inside a field
            j = src.find("\n", i)
            if j == -1:
                break
            i = j
        else:
            m = _NAME_RE.match(src, i)
            i = m.end() if m else i + 1
    line, col = lm.position(start)
    raise PyDenseSyntaxError(
        "unterminated f-string replacement field",
        lineno=line,
        col=col,
        filename=filename,
        text=lm.line_text(line),
        hint="add the closing '}'",
    )


def _scan_spec(src: str, i: int, start: int, lm: LineMap, filename: str) -> int:
    n = len(src)
    while i < n:
        c = src[i]
        if c == "{":  # inside a format spec every '{' opens a nested field (CPython 3.12+)
            i = scan_field(src, i + 1, start, lm, filename)
        elif c == "}":
            return i + 1
        elif c == "\\":
            i += 2
        else:
            i += 1
    line, col = lm.position(start)
    raise PyDenseSyntaxError(
        "unterminated f-string format spec",
        lineno=line,
        col=col,
        filename=filename,
        text=lm.line_text(line),
    )


# ---------------------------------------------------------------------------- fields (parser side)


def parse_fstring_body(
    parser: Parser, body: str, raw: bool, tok: Token, spec: bool = False
) -> ast.JoinedStr:
    """Parse the inside of an f-string.

    In a format spec (``spec=True``) every ``{`` opens a nested field, as in CPython 3.12+.
    """
    values: list[ast.expr] = []
    lit: list[str] = []
    i, n = 0, len(body)

    def flush() -> None:
        if lit:
            values.append(ast.Constant(value=_decode_literal("".join(lit), raw)))
            lit.clear()

    while i < n:
        c = body[i]
        if c == "{":
            if not spec and body.startswith("{{", i):
                lit.append("{")
                i += 2
                continue
            flush()
            end = scan_field(body, i + 1, 0, parser.lm, parser.filename)
            field = body[i + 1 : end - 1]
            values.extend(parse_field(parser, field, tok))
            i = end
        elif c == "}":
            if not body.startswith("}}", i):
                parser.error("single '}' is not allowed in an f-string", at=tok)
            lit.append("}")
            i += 2
        elif c == "\\" and not raw:
            if body.startswith("\\N{", i):
                close = body.find("}", i + 3)
                end = close + 1 if close != -1 else i + 3
                lit.append(body[i:end])
                i = end
            elif body[i + 1 : i + 2] in ("{", "}"):
                lit.append("\\\\" if not raw else "\\")  # literal backslash before a brace
                i += 1
            else:
                lit.append(body[i : i + 2])
                i += 2
        else:
            lit.append(c)
            i += 1
    flush()
    return ast.JoinedStr(values=_merge_constants(values))


def parse_field(parser: Parser, field: str, tok: Token) -> list[ast.expr]:
    expr_text, debug_text, conversion, spec = _split_field(field)
    if conversion != -1 and chr(conversion) not in "rsa":
        parser.error(
            f"invalid f-string conversion character {chr(conversion)!r}",
            hint="use !r, !s or !a with no space",
            at=tok,
        )
    out: list[ast.expr] = []
    sub = type(parser)(expr_text, parser.filename, collect_warnings=False)
    sub.scopes = list(parser.scopes)
    try:
        node = sub.parse_star_exprs(allow_yield=True)
        if sub.peek().kind != "EOF":
            nxt = sub.peek()
            if nxt.kind == "OP" and nxt.value == ":":
                raise PyDenseSyntaxError(
                    "':' inside an f-string field starts the format spec",
                    code="E005",
                    hint="parenthesize the ternary or lambda: f'{(c?a:b)}'",
                )
            sub.error(f"unexpected {sub._describe(nxt)} in f-string replacement field")
    except PyDenseSyntaxError as exc:
        if (
            spec is not None
            and exc.code == "E000"
            and ("?" in expr_text or expr_text.lstrip().startswith("lambda"))
        ):
            raise PyDenseSyntaxError(
                "':' inside an f-string field starts the format spec",
                code="E005",
                lineno=tok.line,
                col=tok.col,
                filename=parser.filename,
                text=parser.lm.line_text(tok.line),
                hint="parenthesize the ternary or lambda: f'{(c?a:b)}'",
            ) from None
        raise PyDenseSyntaxError(
            exc.msg,
            code=exc.code,
            lineno=tok.line,
            col=tok.col,
            filename=parser.filename,
            text=parser.lm.line_text(tok.line),
            hint=exc.hint or "check the expression inside {}",
        ) from None
    if debug_text is not None:
        out.append(ast.Constant(value=debug_text))
        if conversion == -1 and spec is None:
            conversion = ord("r")
    spec_node = None
    if spec is not None:
        spec_node = parse_fstring_body(parser, spec, raw=False, tok=tok, spec=True)
    out.append(ast.FormattedValue(value=node, conversion=conversion, format_spec=spec_node))
    return out


def _merge_constants(values: list[ast.expr]) -> list[ast.expr]:
    out: list[ast.expr] = []
    for v in values:
        if isinstance(v, ast.Constant) and out and isinstance(out[-1], ast.Constant):
            out[-1] = ast.Constant(value=cast(Any, out[-1].value) + v.value)
        else:
            out.append(v)
    return [v for v in out if not (isinstance(v, ast.Constant) and v.value == "")]


def _decode_literal(part: str, raw: bool) -> str:
    if raw:
        return part
    for q in ('"""', "'''"):
        if q not in part and not part.endswith(q[0]):
            return ast.literal_eval(q + part + q)
    esc = part.replace('"', '\\"')
    return ast.literal_eval('"""' + esc + '"""')


def _split_field(field: str) -> tuple[str, str | None, int, str | None]:
    """Split a replacement field into (expr_text, debug_literal, conversion, spec)."""
    i, n = 0, len(field)
    depth = 0
    expr_end: int | None = None
    conversion = -1
    spec: str | None = None
    debug: str | None = None
    while i < n:
        c = field[i]
        if c in "([{":
            depth += 1
            i += 1
        elif c in ")]}":
            depth -= 1
            i += 1
        elif c in "'\"" or (c.isalpha() and _string_prefix_at(field, i) is not None):
            i = _skip_string(field, i)
        elif (
            depth == 0
            and c == "="
            and field[i + 1 : i + 2] != "="
            and (i == 0 or field[i - 1] not in "=!<>:")
        ):
            j = i + 1
            while j < n and field[j] in " \t":
                j += 1
            if j >= n or field[j] in "!:":
                expr_end = i
                debug = field[:j]
                i = j
                break
            i += 1
        elif depth == 0 and c == "!" and field[i + 1 : i + 2] != "=":
            expr_end = i
            conversion = ord(field[i + 1]) if i + 1 < n else -1
            i += 2
            break
        elif depth == 0 and c == ":":
            expr_end = i
            break
        else:
            m = _NAME_RE.match(field, i)
            i = m.end() if m else i + 1
    if expr_end is None:
        return field, None, -1, None
    rest = field[i:]
    if debug is not None and rest.startswith("!"):
        conversion = ord(rest[1]) if len(rest) > 1 else -1
        rest = rest[2:]
    if rest.startswith(":"):
        spec = rest[1:]
    return field[:expr_end], debug, conversion, spec


def _skip_string(s: str, i: int) -> int:
    m = _NAME_RE.match(s, i)
    if m and s[m.end() : m.end() + 1] in ("'", '"'):
        i = m.end()
    q = s[i]
    quote = q * 3 if s.startswith(q * 3, i) else q
    j = i + len(quote)
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s.startswith(quote, j):
            return j + len(quote)
        j += 1
    return len(s)
