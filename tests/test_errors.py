"""Diagnostics E001–E009 (SPEC §13, API contract): code, line:col, hint, and check() behaviour."""

from __future__ import annotations

import re

import pytest


def _raise(pydense_mod, text: str, **kw):
    with pytest.raises(pydense_mod.PyDenseSyntaxError) as info:
        pydense_mod.parse(text, **kw)
    return info.value


def _common(err, code: str) -> None:
    assert isinstance(err, SyntaxError)
    assert err.code == code
    assert err.lineno is not None and err.lineno >= 1
    assert err.col >= 0
    assert err.offset == err.col + 1, "SyntaxError.offset is 1-based, col is 0-based"
    assert str(err).startswith(f"{code} {err.lineno}:{err.col}: ")
    assert err.msg and err.msg.strip()
    assert isinstance(err.hint, str)


# --------------------------------------------------------------------------- E001


def test_e001_single_unclosed_brace(pydense_mod) -> None:
    err = _raise(pydense_mod, "if x{a=1")
    _common(err, "E001")
    assert err.lineno == 1
    assert "1:4" in err.msg, f"must list the position of the unmatched '{{': {err}"
    assert "}" in (err.msg + err.hint)


def test_e001_lists_every_unmatched_brace(pydense_mod) -> None:
    text = "def f(){\nif x{\na=1"
    err = _raise(pydense_mod, text)
    _common(err, "E001")
    assert "1:7" in err.msg and "2:4" in err.msg, err.msg
    assert "2" in err.msg.split("unclosed")[0] or "2 unclosed" in err.msg, err.msg
    assert err.lineno == 3, "reported at end of input"


def test_e001_three_levels(pydense_mod) -> None:
    text = "class A{\ndef f(){\nfor x in y{\n"
    err = _raise(pydense_mod, text)
    _common(err, "E001")
    for pos in ("1:7", "2:7", "3:10"):
        assert pos in err.msg, f"{pos} missing from {err.msg!r}"


def test_e001_does_not_count_closed_blocks(pydense_mod) -> None:
    err = _raise(pydense_mod, "if a{x=1}\nif b{y=2}\nif c{")
    _common(err, "E001")
    assert "3:4" in err.msg
    assert "1:4" not in err.msg and "2:4" not in err.msg


def test_e001_hint_mentions_closing_brace(pydense_mod) -> None:
    err = _raise(pydense_mod, "while x{")
    assert err.code == "E001"
    assert "}" in err.hint or "close" in err.hint.lower() or "}" in err.msg


# --------------------------------------------------------------------------- E002


@pytest.mark.parametrize(
    "text,line,col",
    [
        ("x=1}", 1, 3),
        ("if x{a}}", 1, 7),
        ("x=1\n}", 2, 0),
        ("def f(){\nreturn 1}\n}", 3, 0),
    ],
)
def test_e002_unmatched_close(pydense_mod, text, line, col) -> None:
    err = _raise(pydense_mod, text)
    _common(err, "E002")
    assert (err.lineno, err.col) == (line, col)
    assert "}" in err.msg


# --------------------------------------------------------------------------- E003


@pytest.mark.parametrize(
    "text,line,col,token",
    [
        ("x=1 y=2", 1, 4, "y"),
        ("if x{a=1 b=2}", 1, 9, "b"),
        ("f(a) g(b)", 1, 5, "g"),
        ("x=1\ny=2 z=3", 2, 4, "z"),
    ],
)
def test_e003_missing_separator(pydense_mod, text, line, col, token) -> None:
    err = _raise(pydense_mod, text)
    _common(err, "E003")
    assert (err.lineno, err.col) == (line, col)
    assert token in err.msg
    assert ";" in (err.msg + err.hint) or "newline" in (err.msg + err.hint).lower()


def test_e003_not_raised_for_newline_or_semicolon(pydense_mod) -> None:
    pydense_mod.parse("x=1\ny=2")
    pydense_mod.parse("x=1;y=2")
    pydense_mod.parse("if x{a=1\nb=2}")


# --------------------------------------------------------------------------- E004


@pytest.mark.parametrize(
    "text",
    [
        "@a or b def f(){}",
        "@a+b def f(){}",
        "@not a def f(){}",
        "@a if c else b def f(){}",
        "@a==b class C{}",
    ],
)
def test_e004_non_chain_decorator(pydense_mod, text) -> None:
    err = _raise(pydense_mod, text)
    _common(err, "E004")
    assert err.lineno == 1
    assert "@(" in (err.msg + err.hint), "hint must show the parenthesised form"


def test_e004_not_raised_for_chains(pydense_mod) -> None:
    for text in (
        "@a def f(){}",
        "@a.b def f(){}",
        "@a(1) def f(){}",
        "@a[0].b(1)(2) def f(){}",
        "@(a or b)def f(){}",
        "@(a@b)def f(){}",
        "@a@b def f(){}",
    ):
        pydense_mod.parse(text)


# --------------------------------------------------------------------------- E005


@pytest.mark.parametrize(
    "text",
    ["x=f'{c?a:b}'", "x=f'{c?a:b:>10}'", "x=f'{lambda:1}'", 's=f"{c?a:b!r}"', "x=f'{v:{c?a:b}}'"],
)
def test_e005_ternary_or_lambda_in_fstring_field(pydense_mod, text) -> None:
    err = _raise(pydense_mod, text)
    _common(err, "E005")
    assert "(" in (err.msg + err.hint), "hint must say to parenthesise"


def test_e005_not_raised_when_parenthesised(pydense_mod) -> None:
    pydense_mod.parse("x=f'{(c?a:b)}'")
    pydense_mod.parse("x=f'{(lambda:1)()}'")
    pydense_mod.parse("x=f'{x:{w}}'")


# --------------------------------------------------------------------------- E006


@pytest.mark.parametrize("text", ["x=\\ 1", "x = a \\ + b", "x=\\\n\\ 1"])
def test_e006_stray_backslash(pydense_mod, text) -> None:
    err = _raise(pydense_mod, text)
    _common(err, "E006")
    assert "\\" in err.msg
    assert "lambda" in (err.msg + err.hint) or "continuation" in (err.msg + err.hint)


def test_e006_not_raised_for_line_continuation(pydense_mod) -> None:
    pydense_mod.parse("x=1\\\n+2")
    pydense_mod.parse("x='back\\\\slash'")


# --------------------------------------------------------------------------- E007


@pytest.mark.parametrize(
    "text,line",
    [
        ("def!f(){}", 1),
        ("x=1\ndef!f(this,x){}", 2),
        ("def g(){\ndef!h(x){}}", 2),
        ("class A{def m(){\ndef!h(x){}}}", 2),
    ],
)
def test_e007_def_bang_outside_class(pydense_mod, text, line) -> None:
    err = _raise(pydense_mod, text)
    _common(err, "E007")
    assert err.lineno == line
    assert "def!" in err.msg or "def !" in err.msg
    assert "method" in (err.msg + err.hint).lower()


def test_e007_not_raised_in_class(pydense_mod) -> None:
    pydense_mod.parse("class A{def!f(this,x){}}")
    pydense_mod.parse("class A{if T{def!f(){}}}")


# --------------------------------------------------------------------------- E008


def test_e008_sigil_at_statement_start(pydense_mod) -> None:
    err = _raise(pydense_mod, "x=1\n?c{a}")
    _common(err, "E008")
    assert (err.lineno, err.col) == (2, 0)
    assert "if" in (err.msg + err.hint)


def test_e008_brace_colon_else_position(pydense_mod) -> None:
    err = _raise(pydense_mod, "if c{a}:{b}")
    _common(err, "E008")
    assert (err.lineno, err.col) == (1, 7)
    assert "else" in (err.msg + err.hint)


# --------------------------------------------------------------------------- E009


@pytest.mark.parametrize(
    "text",
    [
        "try{a()}except E{b()}except*F{c()}",
        "try{a()}except*E{b()}except F{c()}",
        "try{}except*E{}except{}",
    ],
)
def test_e009_mixed_except(pydense_mod, text) -> None:
    err = _raise(pydense_mod, text)
    _common(err, "E009")
    assert "except" in err.msg and "*" in err.msg


def test_e009_not_raised_when_uniform(pydense_mod) -> None:
    pydense_mod.parse("try{a()}except E{b()}except F{c()}")
    pydense_mod.parse("try{a()}except*E{b()}except*F{c()}")


# --------------------------------------------------------------------------- E000 and plumbing


def test_e000_for_other_syntax_errors(pydense_mod) -> None:
    err = _raise(pydense_mod, "x=)")
    _common(err, "E000")


def test_error_codes_are_well_formed(pydense_mod) -> None:
    for text in (
        "x=)",
        "if x{a=1",
        "x=1}",
        "x=1 y=2",
        "@a or b def f(){}",
        "x=f'{c?a:b}'",
        "x=\\ 1",
        "def!f(){}",
        "?x{}",
        "try{}except E{}except*F{}",
    ):
        err = _raise(pydense_mod, text)
        assert re.fullmatch(r"E00\d", err.code), err.code


def test_filename_and_text_are_recorded(pydense_mod) -> None:
    err = _raise(pydense_mod, "x=1\ny=2 z=3", filename="prog.dpy")
    assert err.filename == "prog.dpy"
    assert err.text is None or "z=3" in err.text
    default = _raise(pydense_mod, "x=1 y=2")
    assert default.filename == "<dpy>"


def test_str_includes_hint_when_present(pydense_mod) -> None:
    err = _raise(pydense_mod, "if x{a=1")
    if err.hint:
        assert "hint:" in str(err)
        assert err.hint in str(err)


def test_check_never_raises_and_reports_first_error(pydense_mod) -> None:
    diags = pydense_mod.check("x=1 y=2\nz=1}")
    errors = [d for d in diags if d.severity == "error"]
    assert len(errors) == 1
    assert errors[0].code == "E003"
    assert (errors[0].lineno, errors[0].col) == (1, 4)
    assert str(errors[0]).startswith("E003 1:4: ")


def test_check_clean_input_is_empty(pydense_mod) -> None:
    assert pydense_mod.check("x=1\nif x{\ny=2}") == []


def test_diagnostic_is_frozen_dataclass(pydense_mod) -> None:
    d = pydense_mod.Diagnostic("E001", "msg", 1, 0, "error", "fix")
    assert str(d) == "E001 1:0: msg (hint: fix)"
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        d.code = "E002"  # type: ignore[misc]
    assert str(pydense_mod.Diagnostic("W004", "m", 2, 3, "warning")) == "W004 2:3: m"


def test_lint_on_text_raises_on_syntax_error(pydense_mod) -> None:
    with pytest.raises(pydense_mod.PyDenseSyntaxError):
        pydense_mod.lint("x=1 y=2")
