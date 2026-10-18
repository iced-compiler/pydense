"""Rejected-input battery (SPEC §17.7): legacy sigils must raise PyDenseSyntaxError with code E008."""

from __future__ import annotations

import pytest
from _util import load_pairs

PAIRS = load_pairs("rejected")


@pytest.mark.parametrize("dpy,code", [pytest.param(d, c, id=n) for n, d, c in PAIRS])
def test_rejected_raises_with_code(dpy, code, pydense_mod) -> None:
    with pytest.raises(pydense_mod.PyDenseSyntaxError) as info:
        pydense_mod.parse(dpy)
    err = info.value
    assert err.code == code, f"{dpy!r}: got {err.code} ({err})"
    assert isinstance(err, SyntaxError)
    assert err.lineno is not None and err.lineno >= 1
    assert str(err).startswith(f"{code} {err.lineno}:")


@pytest.mark.parametrize("dpy,code", [pytest.param(d, c, id=n) for n, d, c in PAIRS])
def test_rejected_check_reports_one_error(dpy, code, pydense_mod) -> None:
    diags = pydense_mod.check(dpy)
    errors = [d for d in diags if d.severity == "error"]
    assert len(errors) == 1, [str(d) for d in diags]
    assert errors[0].code == code
    assert diags[0] is errors[0] or diags.index(errors[0]) == 0, "the error comes first"


def test_e008_message_points_to_python_keywords(pydense_mod) -> None:
    """The E008 text names the Python spelling to use (SPEC §13)."""
    cases = {
        "?x{a()}": "if",
        "~x:y{f(x)}": "for",
        "^x": "return",
        "@f f(){}": "def",
        "@c A{}": "class",
        "@i(x){.x=x}": "__init__",
        "try{a()}!E:e{b()}": "except",
        "f=\\x:x": "lambda",
        "import a=b": "as",
        "x=a&&b": "and",
        "x=a||b": "or",
        "if c{a}:{b}": "else",
    }
    for text, keyword in cases.items():
        with pytest.raises(pydense_mod.PyDenseSyntaxError) as info:
            pydense_mod.parse(text)
        err = info.value
        assert err.code == "E008"
        assert keyword in (err.msg + " " + err.hint), f"{text!r}: {err}"


def test_decode_and_compile_reject_too(pydense_mod) -> None:
    with pytest.raises(pydense_mod.PyDenseSyntaxError):
        pydense_mod.decode("?x{a()}")
    with pytest.raises(pydense_mod.PyDenseSyntaxError):
        pydense_mod.compile("^x")
