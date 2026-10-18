"""Lenient-input battery (SPEC §17.6): every tolerated spelling parses to the AST of its strict form."""

from __future__ import annotations

import ast

import pytest
from _util import PY, load_pairs, plain_dump

PAIRS = load_pairs("lenient")


def _params():
    out = []
    for item in PAIRS:
        name, dpy, py = item[0], item[1], item[2]
        ver = item[3] if len(item) > 3 else (3, 10)
        marks = [pytest.mark.skipif(PY < ver, reason=f"needs Python {ver[0]}.{ver[1]}+")]
        out.append(pytest.param(dpy, py, id=name, marks=marks))
    return out


@pytest.mark.parametrize("dpy,py", _params())
def test_lenient_parses_to_reference_ast(dpy, py, pydense_mod) -> None:
    want = plain_dump(ast.parse(py))
    got = pydense_mod.parse(dpy)
    assert isinstance(got, ast.Module)
    got_dump = plain_dump(got)
    assert got_dump == want, f"\ndpy ={dpy!r}\nback={ast.unparse(got)!r}\nwant={py!r}"


@pytest.mark.parametrize("dpy,py", _params())
def test_lenient_equals_strict_spelling(dpy, py, pydense_mod) -> None:
    """The canonical re-encoding of the lenient text parses to the same AST, and the strict
    spelling itself is accepted (emit(parse(text)) is a fixed point of parse)."""
    strict = pydense_mod.encode(py)
    assert plain_dump(pydense_mod.parse(strict)) == plain_dump(ast.parse(py))
    assert pydense_mod.encode(pydense_mod.parse(dpy)) == strict


@pytest.mark.parametrize("dpy,py", _params())
def test_lenient_check_reports_no_error(dpy, py, pydense_mod) -> None:
    diags = pydense_mod.check(dpy)
    assert all(d.severity == "warning" for d in diags), [str(d) for d in diags]


@pytest.mark.parametrize("dpy,py", _params())
def test_lenient_decode_is_python(dpy, py, pydense_mod) -> None:
    out = pydense_mod.decode(dpy)
    assert plain_dump(ast.parse(out)) == plain_dump(ast.parse(py))
