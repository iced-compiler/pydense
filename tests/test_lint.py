"""Lint warnings W001–W005 (SPEC §13) with positive and negative cases."""

from __future__ import annotations

import ast

import pytest


def _codes(pydense_mod, text: str) -> list[str]:
    return [d.code for d in pydense_mod.lint(text)]


def _find(pydense_mod, text: str, code: str):
    hits = [d for d in pydense_mod.lint(text) if d.code == code]
    assert hits, f"{code} expected for {text!r}, got {[str(d) for d in pydense_mod.lint(text)]}"
    return hits


# --------------------------------------------------------------------------- W001


@pytest.mark.parametrize(
    "text,line",
    [
        ("foo()\n.bar()", 2),
        ("x=foo()\n.bar()", 2),
        ("x=a[0]\n.bar()", 2),
        ("foo()\n.bar[0]", 2),
        ("x=foo()\n.bar()\n.baz()", 2),
        ("class A{def f(){\nx=foo()\n.bar()}}", 3),
    ],
)
def test_w001_split_call_chain(pydense_mod, text, line) -> None:
    hits = _find(pydense_mod, text, "W001")
    assert hits[0].lineno == line
    assert hits[0].col == 0
    assert hits[0].severity == "warning"
    # the text still parses: two statements, the second being self.bar(...)
    tree = pydense_mod.parse(text)
    assert isinstance(tree, ast.Module)


@pytest.mark.parametrize(
    "text",
    [
        "x=1\n.y=2",  # previous statement ends in a NUMBER
        "foo()\nx=.bar()",  # statement does not start with .NAME(
        "foo()\n.bar=1",  # attribute assignment, not a call/subscript
        "x=(foo()\n.bar())",  # bracketed: a single statement
        "foo()\nbar()",
        "class A{def f(){\n.count+=1\n.mean=value}}",
        "import time\n.last=1",
    ],
)
def test_w001_negative(pydense_mod, text) -> None:
    assert "W001" not in _codes(pydense_mod, text)


# --------------------------------------------------------------------------- W002


@pytest.mark.parametrize(
    "name", ["this", "mcs", "metacls", "meta", "klass", "kls", "that", "me", "obj"]
)
def test_w002_receiver_like_first_parameter(pydense_mod, name) -> None:
    text = f"class A{{def f({name},x){{}}}}"
    hits = _find(pydense_mod, text, "W002")
    assert hits[0].lineno == 1
    assert name in hits[0].message
    assert "def!" in (hits[0].message + hits[0].hint) or "self" in (hits[0].message + hits[0].hint)


def test_w002_classmethod_klass(pydense_mod) -> None:
    _find(pydense_mod, "class A{@classmethod def c(klass,x){}}", "W002")


@pytest.mark.parametrize(
    "text",
    [
        "class A{def!f(this,x){}}",  # def! is the escape
        "class A{def f(x){}}",  # ordinary parameter name
        "class A{def f(self,x){}}",
        "class A{def f(cls,x){}}",
        "def f(this,x){}",  # not in a class
        "class A{def m(){def f(this,x){}}}",  # nested function is not a method
        "class A{@staticmethod def s(this){}}",  # no receiver is injected under @staticmethod
        "class A{def f(x,this){}}",  # 'this' is not the first parameter
    ],
)
def test_w002_negative(pydense_mod, text) -> None:
    assert "W002" not in _codes(pydense_mod, text)


# --------------------------------------------------------------------------- W003


@pytest.mark.parametrize(
    "text", ["x={1}\nelse{y=2}", "d={'k':v}finally{x}", "s={1,2}except E{}", "x={}elif c{}"]
)
def test_w003_continuation_after_display(pydense_mod, text) -> None:
    """Impossible in valid input: parse fails, and check() points at the real mistake with W003."""
    diags = pydense_mod.check(text)
    assert any(d.severity == "error" for d in diags)
    assert any(d.code == "W003" for d in diags), [str(d) for d in diags]


def test_w003_negative(pydense_mod) -> None:
    assert "W003" not in _codes(pydense_mod, "if c{x={1}}else{y=2}")
    assert "W003" not in _codes(pydense_mod, "try{x={}}finally{y}")


# --------------------------------------------------------------------------- W004


@pytest.mark.parametrize(
    "text,line,col",
    [
        ("x=1;", 1, 3),
        ("if x{a();}", 1, 8),
        ("if x{a()};y=1", 1, 9),
        ("if x{a()};", 1, 9),
        ("def f(){\nreturn 1;}", 2, 8),
    ],
)
def test_w004_semicolon_at_brace(pydense_mod, text, line, col) -> None:
    hits = _find(pydense_mod, text, "W004")
    assert (hits[0].lineno, hits[0].col) == (line, col)
    assert ";" in hits[0].message


@pytest.mark.parametrize(
    "text", ["x=1;y=2", "x=1\ny=2", "if x{a()}\ny=1", "x=';'", "if x{a();b()}"]
)
def test_w004_negative(pydense_mod, text) -> None:
    assert "W004" not in _codes(pydense_mod, text)


# --------------------------------------------------------------------------- W005


@pytest.mark.parametrize(
    "text,line",
    [
        ("x=a\n+b", 2),
        ("x=a\n-b", 2),
        ("x=a\n+b\n+c", 2),
        ("def f(){\ny=a\n+b}", 3),
    ],
)
def test_w005_binary_operator_after_newline(pydense_mod, text, line) -> None:
    hits = _find(pydense_mod, text, "W005")
    assert hits[0].lineno == line
    assert hits[0].col == 0
    # still two statements, as in Python
    tree = pydense_mod.parse(text)
    assert isinstance(tree, ast.Module)


@pytest.mark.parametrize(
    "text",
    ["x=a\nb", "x=(a\n+b)", "x=a\n(b)", "x=a\n.b=1", "x=[a,\n-b]", "x=a+\\\nb", "x=a\nnot b"],
)
def test_w005_negative(pydense_mod, text) -> None:
    assert "W005" not in _codes(pydense_mod, text)


# --------------------------------------------------------------------------- plumbing


def test_lint_accepts_text_and_tree(pydense_mod) -> None:
    text = "class A{def f(this,x){}}"
    from_text = pydense_mod.lint(text)
    from_tree = pydense_mod.lint(pydense_mod.parse(text))
    assert [d.code for d in from_text] == ["W002"]
    # token-level rules need the text; a bare tree may carry fewer warnings but never different codes
    assert {d.code for d in from_tree} <= {d.code for d in from_text}


def test_lint_results_are_sorted_and_warnings_only(pydense_mod) -> None:
    text = "if c{a();}\nfoo()\n.bar()\ny=a\n+b"
    diags = pydense_mod.lint(text)
    assert all(d.severity == "warning" for d in diags)
    assert {d.code for d in diags} >= {"W001", "W004", "W005"}
    positions = [(d.lineno, d.col) for d in diags]
    assert positions == sorted(positions)


def test_check_reports_at_most_one_error_first(pydense_mod) -> None:
    diags = pydense_mod.check("if c{a();}\nfoo()\n.bar()\nz=1}")
    errors = [d for d in diags if d.severity == "error"]
    assert len(errors) == 1 and errors[0].code == "E002"
    assert diags[0] is errors[0]
    assert all(d.severity == "warning" for d in diags[1:])
    assert {d.code for d in diags[1:]} <= {"W001", "W002", "W003", "W004", "W005"}


def test_canonical_output_is_lint_clean(pydense_mod) -> None:
    src = "class A:\n    def f(self, other):\n        x = foo().bar()\n        y = self.go()\n        return x + y\n"
    dpy = pydense_mod.encode(src)
    assert pydense_mod.lint(dpy) == []
    assert pydense_mod.check(dpy) == []
