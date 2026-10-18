"""pydense.runtime: run(), run_repl() and compact tracebacks."""

from __future__ import annotations

import pytest

import pydense
from pydense import PyDenseSyntaxError
from pydense.runtime import PyDenseRuntimeError, RunResult, format_compact_error, run, run_repl

# --- compile ---------------------------------------------------------------------------------------


def test_compile_wraps_cpython_errors_as_pydense_syntax_error() -> None:
    # The .dpy parses (PyDense has no symbol table); CPython's own compile step rejects it.
    with pytest.raises(PyDenseSyntaxError) as info:
        pydense.compile("def f(a,a){}", "dup.dpy")
    err = info.value
    assert err.msg == "duplicate argument 'a' in function definition"
    assert err.filename == "dup.dpy" and err.lineno == 1
    assert err.hint == "CPython rejected the program"
    assert str(err).endswith("(hint: CPython rejected the program)")
    assert err.__cause__ is None  # the CPython SyntaxError is not chained into the message


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("nonlocal x", "nonlocal declaration not allowed at module level"),
        ("return 1", "'return' outside function"),
        ("def f(){\nyield 1\nreturn}\nclass C{\nreturn}", "'return' outside function"),
    ],
)
def test_compile_cpython_rejections_report_the_dpy_filename(code: str, message: str) -> None:
    with pytest.raises(PyDenseSyntaxError) as info:
        pydense.compile(code, "prog.dpy")
    assert info.value.msg == message
    assert info.value.filename == "prog.dpy"
    assert info.value.lineno >= 1


def test_run_surfaces_cpython_rejection_as_syntax_error() -> None:
    with pytest.raises(PyDenseSyntaxError):
        run("def f(a,a){}")
    result = run_repl("def f(a,a){}", {})
    assert result.error is not None and "duplicate argument" in result.error


def test_compile_eval_mode_accepts_a_single_expression() -> None:
    assert eval(pydense.compile("1+2*3", mode="eval")) == 7
    assert eval(pydense.compile("[x*2 for x in range(3)]", mode="eval")) == [0, 2, 4]
    assert eval(pydense.compile("1>0?'y':'n'", mode="eval")) == "y"
    assert eval(pydense.compile("a+b", mode="eval"), {"a": 2, "b": 3}) == 5
    code = pydense.compile("x", "expr.dpy", mode="eval")
    assert code.co_filename == "expr.dpy"


@pytest.mark.parametrize("code", ["x=1", "1\n2", "", "if x{\n1}", "import os"])
def test_compile_eval_mode_rejects_statements(code: str) -> None:
    with pytest.raises(PyDenseSyntaxError) as info:
        pydense.compile(code, "expr.dpy", mode="eval")
    assert info.value.msg == "eval mode needs a single expression"
    assert info.value.filename == "expr.dpy"


def test_compile_eval_mode_still_reports_dpy_syntax_errors() -> None:
    with pytest.raises(PyDenseSyntaxError) as info:
        pydense.compile("f(1", mode="eval")
    assert info.value.code != "E000" or "eval mode" not in info.value.msg


# --- run -------------------------------------------------------------------------------------------


def test_run_returns_new_env_with_bindings() -> None:
    env = run("x=1\ny=x+1")
    assert env["x"] == 1 and env["y"] == 2
    assert env["__name__"] == "__main__"


def test_run_uses_given_env_and_returns_it() -> None:
    env: dict = {"base": 10}
    out = run("total=base*2", env)
    assert out is env
    assert env["total"] == 20


def test_run_executes_dense_class_and_method() -> None:
    env = run(
        "class A{\ndef __init__(a,b=1){\n.a=a\n.b=b}\ndef total(){\nreturn.a+.b}}\nt=A(2).total()"
    )
    assert env["t"] == 3


def test_run_is_re_exported_from_package() -> None:
    assert pydense.run is run
    assert pydense.format_compact_error is format_compact_error


def test_run_wraps_runtime_exception_compactly() -> None:
    with pytest.raises(PyDenseRuntimeError) as info:
        run("def boom(){\nraise ValueError('bad')}\nboom()", filename="<dpy>")
    err = info.value
    assert str(err) == "!Err[boom:L2]: ValueError(bad)"
    assert isinstance(err.original, ValueError)
    assert "\n" not in str(err)


def test_run_module_level_error_names_module_frame() -> None:
    with pytest.raises(PyDenseRuntimeError) as info:
        run("x=1\ny=1/0")
    assert str(info.value) == "!Err[<module>:L2]: ZeroDivisionError(division by zero)"


def test_run_syntax_error_propagates_as_syntax_error() -> None:
    with pytest.raises(SyntaxError):
        run("if x{\ny=1")


def test_run_system_exit_is_not_wrapped() -> None:
    with pytest.raises(SystemExit):
        run("import sys\nsys.exit(3)")


# --- run_repl --------------------------------------------------------------------------------------


def test_run_repl_returns_last_expression_value() -> None:
    env: dict = {}
    result = run_repl("a=[x**2 for x in range(5)]\nsum(a)", env)
    assert isinstance(result, RunResult)
    assert result.ok
    assert result.value == 30
    assert result.value_repr == "30"
    assert env["a"] == [0, 1, 4, 9, 16]
    assert result.stdout == "" and result.stderr == ""


def test_run_repl_none_last_value_has_no_repr() -> None:
    result = run_repl("x=None\nx", {})
    assert result.error is None
    assert result.value is None
    assert result.value_repr is None


def test_run_repl_statement_last_has_no_value() -> None:
    env: dict = {}
    result = run_repl("x=5", env)
    assert result.value is None and result.value_repr is None and result.error is None
    assert env["x"] == 5


def test_run_repl_captures_stdout_and_stderr() -> None:
    result = run_repl("import sys\nprint('hello')\nsys.stderr.write('warn\\n')\n'done'", {})
    assert result.stdout == "hello\n"
    assert result.stderr == "warn\n"
    assert result.value == "done"
    assert result.value_repr == "'done'"


def test_run_repl_state_persists_between_calls() -> None:
    env: dict = {}
    assert run_repl("counter=1", env).ok
    assert run_repl("counter+=1\ncounter", env).value == 2


def test_run_repl_runtime_error_is_compact_and_single_line() -> None:
    result = run_repl("def f(n){\nreturn 1/n}\nprint('before')\nf(0)", {})
    assert result.stdout == "before\n"
    assert result.value is None and result.value_repr is None
    assert result.error == "!Err[f:L2]: ZeroDivisionError(division by zero)"


def test_run_repl_syntax_error_does_not_raise() -> None:
    result = run_repl("if x{\ny=1", {})
    assert result.error is not None
    assert result.error.startswith("!Err[")
    assert "E001" in result.error
    assert "\n" not in result.error


def test_run_repl_last_expression_with_side_effect_runs_once() -> None:
    env: dict = {"calls": []}
    result = run_repl("calls.append(1)\nlen(calls)", env)
    assert result.value == 1
    assert env["calls"] == [1]


# --- format_compact_error ---------------------------------------------------------------------------


def _raise_from_dpy(text: str, filename: str = "<dpy>") -> BaseException:
    code = pydense.compile(text, filename)
    try:
        exec(code, {"__name__": "__main__"})
    except Exception as exc:  # noqa: BLE001 - the test wants the exception object
        return exc
    raise AssertionError("code did not raise")


def test_format_compact_error_picks_innermost_dpy_frame() -> None:
    exc = _raise_from_dpy(
        "def outer(){\nreturn inner()}\ndef inner(){\nraise KeyError('k')}\nouter()"
    )
    assert format_compact_error(exc) == "!Err[inner:L4]: KeyError('k')"


def test_format_compact_error_with_explicit_filename() -> None:
    exc = _raise_from_dpy("def g(){\nraise TypeError('t')}\ng()", filename="prog.dpy")
    assert format_compact_error(exc, "prog.dpy") == "!Err[g:L2]: TypeError(t)"
    assert format_compact_error(exc) == "!Err[g:L2]: TypeError(t)"


def test_format_compact_error_skips_library_frames_below_dpy_frame() -> None:
    # The innermost frames belong to json (a non-dpy file); the reported frame is the dpy caller.
    exc = _raise_from_dpy("import json\ndef load(){\nreturn json.loads('{bad')}\nload()")
    assert format_compact_error(exc).startswith("!Err[load:L3]: JSONDecodeError(")


def test_format_compact_error_falls_back_to_last_frame() -> None:
    def helper() -> None:
        raise RuntimeError("plain python")

    try:
        helper()
    except RuntimeError as exc:
        text = format_compact_error(exc)
    assert text.startswith("!Err[helper:L")
    assert text.endswith("]: RuntimeError(plain python)")


def test_format_compact_error_without_traceback() -> None:
    assert format_compact_error(ValueError("x")) == "!Err: ValueError(x)"


def test_format_compact_error_is_single_line_for_multiline_messages() -> None:
    exc = _raise_from_dpy("raise ValueError('a\\nb')")
    text = format_compact_error(exc)
    assert "\n" not in text
    assert text == "!Err[<module>:L1]: ValueError(a b)"
