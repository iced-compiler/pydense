"""Parser spellings that only hand-written ``.dpy`` reaches (the emitter never produces them):
implicit string concatenation, trailing-comma brace lookahead in headers, dotted / ``.k`` mapping
pattern keys, f-string corners (SPEC §9.2), spellings that must raise ``PyDenseSyntaxError``, nesting
depth and non-identifier characters.  Wherever CPython accepts the Python spelling the AST is compared
with ``ast.parse``."""

from __future__ import annotations

import ast

import pytest
from _util import needs, plain_dump


def _same(pydense_mod, dpy: str, py: str) -> ast.Module:
    tree = pydense_mod.parse(dpy)
    got, want = plain_dump(tree), plain_dump(ast.parse(py))
    assert got == want, f"\ndpy ={dpy!r}\nback={ast.unparse(tree)!r}\nwant={py!r}"
    return tree


def _raises(pydense_mod, dpy: str) -> Exception:
    with pytest.raises(pydense_mod.PyDenseSyntaxError) as info:
        pydense_mod.parse(dpy)
    return info.value


# --------------------------------------------------------------------------- implicit concatenation


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("x='a' 'b'", "x = 'a' 'b'"),
        ("x='a' 'b' 'c'", "x = 'a' 'b' 'c'"),
        ("x='a' f'{b}'", "x = 'a' f'{b}'"),
        ("x=f'{b}' 'a'", "x = f'{b}' 'a'"),
        ("x=f'{a}' f'{b}'", "x = f'{a}' f'{b}'"),
        ("x=b'a' b'b'", "x = b'a' b'b'"),
        ("x=r'\\d' '\\n'", "x = r'\\d' '\\n'"),
        ("f('a'\n'b')", "f('a'\n'b')"),
    ],
)
def test_implicit_string_concatenation(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


def test_mixed_bytes_and_str_concatenation_is_error(pydense_mod) -> None:
    with pytest.raises(SyntaxError):  # Python's own rule
        ast.parse("x = 'a' b'c'")
    _raises(pydense_mod, "x='a' b'c'")
    _raises(pydense_mod, "x=b'c' f'{a}'")


# --------------------------------------------------------------------------- header trailing-comma lookahead


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("for x in a,{1,2}{pass}", "for x in a, {1, 2}:\n    pass"),
        ("for x in a,{}{pass}", "for x in a, {}:\n    pass"),
        ("for x in a,{k:v}{pass}", "for x in a, {k: v}:\n    pass"),
        ("match a,{1}{case _{}}", "match a, {1}:\n    case _:\n        pass"),
        ("match a,{}{case _{}}", "match a, {}:\n    case _:\n        pass"),
        ("for x in a,{pass}", "for x in (a,):\n    pass"),
        ("match a,{case _{}}", "match (a,):\n    case _:\n        pass"),
    ],
)
def test_header_trailing_comma_brace_lookahead(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


# --------------------------------------------------------------------------- mapping pattern keys


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("match x{case {A.B:v}{}}", "match x:\n    case {A.B: v}:\n        pass"),
        ("match x{case {A.B.C:v,**r}{}}", "match x:\n    case {A.B.C: v, **r}:\n        pass"),
        ("match x{case {.k:v}{}}", "match x:\n    case {self.k: v}:\n        pass"),
        ("match x{case {.k:v,'s':w}{}}", "match x:\n    case {self.k: v, 's': w}:\n        pass"),
        (
            "match x{case {1:v,-2:w,None:z}{}}",
            "match x:\n    case {1: v, -2: w, None: z}:\n        pass",
        ),
    ],
)
def test_mapping_pattern_dotted_and_self_keys(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


# --------------------------------------------------------------------------- f-string corners


def test_fstring_field_trailing_token_is_error(pydense_mod) -> None:
    err = _raises(pydense_mod, "x=f'{a b}'")
    assert err.lineno == 1


def test_fstring_named_unicode_escape(pydense_mod) -> None:
    tree = _same(pydense_mod, "x=f'\\N{EM DASH}{a}'", "x = f'\\N{EM DASH}{a}'")
    joined = tree.body[0].value  # type: ignore[attr-defined]
    assert isinstance(joined, ast.JoinedStr)
    assert joined.values[0].value == "\u2014"  # type: ignore[attr-defined]
    assert isinstance(joined.values[1], ast.FormattedValue)


@needs(3, 12)
def test_fstring_pep701_comment_inside_field(pydense_mod) -> None:
    _same(pydense_mod, "x=f'{a # c\n}'", "x = f'{a # c\n}'")


@needs(3, 12)
def test_fstring_format_spec_with_nested_field(pydense_mod) -> None:
    # CPython reads ``{{`` inside a spec as a nested replacement field holding ``{}``, not an escape
    tree = _same(pydense_mod, "x=f'{a:{{}}>5}'", "x = f'{a:{{}}>5}'")
    field = tree.body[0].value.values[0]  # type: ignore[attr-defined]
    assert isinstance(field.format_spec.values[0], ast.FormattedValue)
    assert isinstance(field.format_spec.values[0].value, ast.Dict)


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("x=f'{a:{w}>5}'", "x = f'{a:{w}>5}'"),
        ("x=f'{a:{w}.{p}f}'", "x = f'{a:{w}.{p}f}'"),
        ("x=f'{a!r:>{w}}'", "x = f'{a!r:>{w}}'"),
        ("x=f'{{}}'", "x = f'{{}}'"),
        ("x=f'{a}{{'", "x = f'{a}{{'"),
    ],
)
def test_fstring_specs_and_escapes(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


# --------------------------------------------------------------------------- spellings that must raise

# (dpy, python equivalent or None when the shape is dpy-only); every row raises PyDenseSyntaxError and,
# when a Python spelling exists, CPython rejects it too.
INVALID: list[tuple[str, str | None]] = [
    ("def f(*){}", "def f(*): pass"),
    ("del *x", "del *x"),
    ("[*x for x in a]", "[*x for x in a]"),
    ("g(a=1,b)", "g(a=1, b)"),
    ("g(**e,*c)", "g(**e, *c)"),
    ("g(x for x in a,1)", "g(x for x in a, 1)"),
    ("f'{a! r}'", "f'{a! r}'"),
    ("f'{a!x}'", "f'{a!x}'"),
    ("f'{a}}'", "f'{a}}'"),
    ("import a.\nb", "import a.\nb"),
    ("class A{def f(/){}}", None),  # the implicit receiver does not count as a parameter before '/'
    ("try{}except*{}", "try:\n    pass\nexcept*:\n    pass"),
    ("x=lambda\n:1", None),  # a depth-0 newline ends the lambda header (SPEC §6.6)
    ("from a import b,\nc", "from a import b,\nc"),
    ("x=\ny=2", "x =\ny = 2"),
    ("x=a and\nb", "x = a and\nb"),
]


@pytest.mark.parametrize("dpy,py", INVALID, ids=[repr(d) for d, _ in INVALID])
def test_invalid_spellings_raise(pydense_mod, dpy, py) -> None:
    if py is not None:
        with pytest.raises(SyntaxError):
            ast.parse(py)
    err = _raises(pydense_mod, dpy)
    assert err.code.startswith("E") and err.lineno >= 1


# --------------------------------------------------------------------------- nesting depth


def _nested(n: int, open_: str = "(", close: str = ")") -> str:
    return "x=" + open_ * n + "1" + close * n


def test_deep_nesting_within_cpython_limit_parses(pydense_mod) -> None:
    for open_, close in (("(", ")"), ("[", "]")):
        dpy = _nested(150, open_, close)
        assert plain_dump(pydense_mod.parse(dpy)) == plain_dump(ast.parse(dpy))


def test_nesting_beyond_cpython_limit_is_e000(pydense_mod) -> None:
    with pytest.raises(SyntaxError):  # CPython: too many nested parentheses
        ast.parse(_nested(600))
    err = _raises(pydense_mod, _nested(600))
    assert err.code == "E000"
    assert "nested" in err.msg


# --------------------------------------------------------------------------- non-identifier characters


@pytest.mark.parametrize("dpy", ["a²=1", "x=⑴", "x=a²", "f(①)"])
def test_non_identifier_characters_raise(pydense_mod, dpy) -> None:
    with pytest.raises(SyntaxError):  # not XID_Start / XID_Continue, so Python rejects them too
        ast.parse(dpy)
    err = _raises(pydense_mod, dpy)
    assert err.code == "E000"
