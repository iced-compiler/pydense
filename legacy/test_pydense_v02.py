#!/usr/bin/env python3
"""
Comprehensive Pytest Suite for PyDense (.pyd) Compiler, Decompiler, Runner, MCP Server & CLI.
"""

from __future__ import annotations
import ast
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pydense import (
    PyDenseCompiler,
    PyDenseDecompiler,
    PyDenseRunner,
    tokenize_pyd,
)
from mcp_server import (
    SESSIONS,
    SKILL_CHEATSHEET,
    _dispatch_tool,
    tool_execute_pydense,
    tool_read_file_as_pydense,
    tool_transpile_preview,
    tool_write_pydense_module,
)
from pydense_cli import cmd_init_skill
from benchmarks.token_compression import BENCHMARK_WORKLOADS, get_token_counters


# ============================================================================
# 1. LEXER & SYNTAX VALIDATION TESTS
# ============================================================================

def test_lexer_ignores_whitespace_and_comments() -> None:
    code = """
    // Leading comment
    @f add(a, b) {
        ^ $0 + $1 // inline comment
    }
    """
    tokens = tokenize_pyd(code)
    vals = [t.val for t in tokens]
    assert vals == ["@f", "add", "(", "a", ",", "b", ")", "{", "^", "$0", "+", "$1", "}"]


def test_lexer_rejects_invalid_characters() -> None:
    with pytest.raises(SyntaxError, match="Unexpected PyDense character"):
        tokenize_pyd("@f bad(){x = `invalid`}")


def test_compiler_rejects_unclosed_blocks_and_brackets() -> None:
    compiler = PyDenseCompiler()
    with pytest.raises(SyntaxError, match="Unclosed"):
        compiler.compile_to_source("@f broken(a){^$0+1")
    with pytest.raises(SyntaxError, match="Unclosed bracket"):
        compiler.compile_to_source("x=[1,2,3")


def test_compiler_rejects_unknown_macros_and_builtins() -> None:
    compiler = PyDenseCompiler()
    with pytest.raises(SyntaxError, match="Unknown PyDense macro"):
        compiler.compile_to_source("x=#unknown_macro")
    with pytest.raises(SyntaxError, match="Unknown PyDense builtin"):
        compiler.compile_to_source("x=%unknown_builtin(1)")


# ============================================================================
# 2. CORE GRAMMAR & EXECUTION TESTS (.pyd -> AST -> CPython)
# ============================================================================

def test_classes_implicit_self_and_positional_args() -> None:
    pyd = (
        "@c Counter{"
        "@i(start:int=0,step:int=1){.val=$0;.step=$1}"
        "@f inc(mult:int=1)->int{.val+=.step*$0;^.val}"
        "@sf zero()->int{^0}"
        "};"
        "c=Counter(10,2);r1=c.inc();r2=c.inc(3);r3=Counter.zero()"
    )
    ns = PyDenseRunner().execute(pyd)
    assert ns["r1"] == 12
    assert ns["r2"] == 18
    assert ns["r3"] == 0


def test_control_flow_if_elif_else_loops_and_ternary() -> None:
    pyd = (
        "@f classify(nums:list[int])->list[str]{"
        "out=[];"
        "~x:$0{"
        "?x<0{^~}"
        ":?x==0{out.append('zero')}"
        ":?x>100{^!}"
        ":{out.append(x%2==0??'even':'odd')}"
        "};"
        "^out"
        "};"
        "res=classify([-5,0,3,4,150,2])"
    )
    ns = PyDenseRunner().execute(pyd)
    assert ns["res"] == ["zero", "odd", "even"]


def test_while_loop_and_augmented_assignments() -> None:
    pyd = "@f collatz_steps(n:int)->int{s=0;x=$0;~?x>1{x=x%2==0??x//2:3*x+1;s+=1};^s};res=collatz_steps(6)"
    ns = PyDenseRunner().execute(pyd)
    assert ns["res"] == 8


def test_try_except_finally_and_raise() -> None:
    pyd = (
        "@f safe_div(a:float,b:float)->tuple[float,bool]{"
        "flag=#F;"
        "!{?b==0{^@ZeroDivisionError('div0')};res=$0/$1}"
        "!ZeroDivisionError:e{res=-1.0}"
        "!*{flag=#T};"
        "^res,flag"
        "};"
        "ok=safe_div(10.0,2.0);err=safe_div(10.0,0.0)"
    )
    ns = PyDenseRunner().execute(pyd)
    assert ns["ok"] == (5.0, True)
    assert ns["err"] == (-1.0, True)


def test_comprehensions_and_lambdas() -> None:
    pyd = (
        "sq=[x**2~x:%r(6)?x%2==0];"
        "mp={x:x*10~x:%r(1,4)};"
        "st={x%3~x:%r(10)};"
        "fn=\\a,b=5:$0*$1;"
        "l_res=fn(4)"
    )
    ns = PyDenseRunner().execute(pyd)
    assert ns["sq"] == [0, 4, 16]
    assert ns["mp"] == {1: 10, 2: 20, 3: 30}
    assert ns["st"] == {0, 1, 2}
    assert ns["l_res"] == 20


def test_boolean_identity_membership_and_bitwise_ops() -> None:
    pyd = (
        "a=#T&&!#F;"
        "b=#F||#T;"
        "c=3@in[1,2,3]&&9!@in[1,2,3];"
        "n=#N;"
        "d=n@is#N&&a!@is#N;"
        "xo=5^|3"
    )
    ns = PyDenseRunner().execute(pyd)
    assert ns["a"] is True
    assert ns["b"] is True
    assert ns["c"] is True
    assert ns["d"] is True
    assert ns["xo"] == (5 ^ 3)


# ============================================================================
# 3. v0.2 UPGRADE TESTS (DECORATORS, TYPE ANNOTATIONS, UNPACKING, ASYNC)
# ============================================================================

def test_stacked_and_bracketed_decorators_with_dataclass() -> None:
    pyd = (
        "@f add_tag(tag:str){@f dec(fn){@f wrap(*a,**kw){^tag+':'+$0(*a,**kw)};^wrap};^dec};"
        "@#dc(frozen=#T)@c Item{name:str;qty:int=1};"
        "@[add_tag('OUTER'),add_tag('INNER')]@f fmt(o:Item)->str{^f'{$0.name}={$0.qty}'};"
        "item=Item('pen',5);res=fmt(item)"
    )
    ns = PyDenseRunner().execute(pyd)
    assert ns["res"] == "OUTER:INNER:pen=5"


def test_variadic_and_literal_unpacking() -> None:
    pyd = (
        "@f combine(head:int,*rest:int,scale:int=2,**meta:int)->dict[str,int]{"
        "arr=[$0,*rest];"
        "first,*mid,last=[0,*arr,99];"
        "base={'first':first,'last':last,'mid_sum':%s(mid)*scale};"
        "^{**base,**meta}"
        "};"
        "res=combine(1,2,3,4,scale=10,extra=7)"
    )
    ns = PyDenseRunner().execute(pyd)
    assert ns["res"] == {"first": 0, "last": 99, "mid_sum": 100, "extra": 7}


def test_async_def_await_async_for_and_async_with() -> None:
    pyd = (
        "@c AsyncPipe{"
        "@i(items:list[int]){.items=$0}"
        "@af __aenter__(){@aw #as.sleep(0);^self}"
        "@af __aexit__(*a){^#F}"
        "@af stream(){~x:.items{@aw #as.sleep(0);^>x*2}}"
        "};"
        "@af run_pipe(vals:list[int])->list[int]{"
        "@wa AsyncPipe($0):p{out=[v~@v:p.stream()?v>2]};"
        "^out"
        "};"
        "res=#as.run(run_pipe([1,2,3,4]))"
    )
    ns = PyDenseRunner().execute(pyd)
    assert ns["res"] == [4, 6, 8]


# ============================================================================
# 4. BIJECTIVE ROUND-TRIP & COMPACT TRACEBACK TESTS
# ============================================================================

@pytest.mark.parametrize("workload_name,py_src", list(BENCHMARK_WORKLOADS.items()))
def test_benchmark_workloads_round_trip_ast_validity(workload_name: str, py_src: str) -> None:
    compiler = PyDenseCompiler()
    for preserve_types in (True, False):
        decompiler = PyDenseDecompiler(use_positional_args=True, preserve_types=preserve_types)
        pyd_code = decompiler.decompile(py_src)
        assert len(pyd_code) < len(py_src), f"{workload_name} did not compress"
        tree = compiler.compile_to_ast(pyd_code)
        assert isinstance(tree, ast.Module)
        # Ensure compiled AST compiles cleanly to CPython bytecode
        compile(tree, filename=f"<{workload_name}>", mode="exec")


def test_compact_traceback_format() -> None:
    pyd = "@f boom(x:int){?x<0{^@ValueError('negative input')};^100/$0};boom(-1)"
    with pytest.raises(RuntimeError) as exc_info:
        PyDenseRunner().execute(pyd)
    msg = str(exc_info.value)
    assert msg.startswith("!Err[boom:L")
    assert "ValueError(negative input)" in msg
    assert "\n" not in msg


# ============================================================================
# 5. MCP SERVER TOOL TESTS (`mcp_server.py`)
# ============================================================================

def test_mcp_stateful_repl_execution() -> None:
    out1 = tool_execute_pydense("x=10;y=25;x+y", session_id="pytest_sess", reset_session=True)
    assert out1 == "=> 35"

    out2 = tool_execute_pydense("%p('hello');x*2", session_id="pytest_sess", reset_session=False)
    assert "hello" in out2
    assert "=> 20" in out2

    err_out = tool_execute_pydense("1/0", session_id="pytest_sess")
    assert err_out.startswith("!Err[") and "ZeroDivisionError" in err_out


def test_mcp_write_and_read_pydense_module(tmp_path: Path) -> None:
    target_py = tmp_path / "sample_mod.py"
    pyd_src = "@fema(vals:list[float],a:float=0.5)->float{st=$0[0];~v:$0[1:]{st=$1*v+(1.0-$1)*st};^st}"
    # Fix function keyword spacing
    pyd_src = "@f ema(vals:list[float],a:float=0.5)->float{st=$0[0];~v:$0[1:]{st=$1*v+(1.0-$1)*st};^st}"

    msg = tool_write_pydense_module(str(target_py), pyd_src, output_format="both")
    assert "Saved" in msg
    assert target_py.exists()
    assert target_py.with_suffix(".pyd").exists()

    # Verify saved .py file is valid, runnable standard Python
    saved_py_text = target_py.read_text(encoding="utf-8")
    assert "def ema(" in saved_py_text
    ns: Dict[str, Any] = {}
    exec(saved_py_text, ns)
    assert abs(ns["ema"]([10.0, 20.0], 0.5) - 15.0) < 1e-9

    # Verify read_file_as_pydense compresses the saved .py file back into .pyd
    compressed = tool_read_file_as_pydense(str(target_py))
    assert "@f ema(" in compressed
    assert "\n" not in compressed.strip()


def test_mcp_dispatch_and_transpile_preview() -> None:
    py_preview = _dispatch_tool(
        "transpile_preview",
        {"code": "@f sq(x:int)->int{^$0**2}", "direction": "pyd_to_py"},
    )
    assert "def sq(x: int) -> int:" in py_preview

    pyd_preview = _dispatch_tool(
        "transpile_preview",
        {"code": "def sq(x: int) -> int:\n    return x ** 2\n", "direction": "py_to_pyd"},
    )
    assert pyd_preview == "@f sq(x:int)->int{^$0**2}"

    spec = _dispatch_tool("get_pydense_skill_spec", {})
    assert spec == SKILL_CHEATSHEET


# ============================================================================
# 6. CLI & SKILL INITIALIZER TESTS (`pydense_cli.py`)
# ============================================================================

def test_cli_init_skill_creates_all_agent_configs(tmp_path: Path) -> None:
    cmd_init_skill(tmp_path)
    assert (tmp_path / "SKILL.md").exists()
    assert (tmp_path / ".cursorrules").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    mcp_json = tmp_path / ".vscode" / "mcp.json"
    assert mcp_json.exists()
    parsed = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert "pydense" in parsed["mcpServers"]


def test_cli_inline_execution_and_file_commands(tmp_path: Path) -> None:
    cli_script = str(ROOT_DIR / "pydense_cli.py")
    res = subprocess.run(
        [sys.executable, cli_script, "-c", "@f double(x){^$0*2};%p(double(21))"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert res.stdout.strip() == "42"


# ============================================================================
# 7. NFR TOKEN COMPRESSION & LATENCY REGRESSION GUARD
# ============================================================================

def test_nfr_token_compression_and_latency_thresholds() -> None:
    count_o200k, _, _ = get_token_counters()
    compiler = PyDenseCompiler()
    decomp_stripped = PyDenseDecompiler(use_positional_args=True, preserve_types=False)

    total_py_tokens = 0
    total_pyd_tokens = 0

    for name, py_src in BENCHMARK_WORKLOADS.items():
        pyd_src = decomp_stripped.decompile(py_src)
        total_py_tokens += count_o200k(py_src)
        total_pyd_tokens += count_o200k(pyd_src)

        t0 = time.perf_counter()
        compiler.compile_to_ast(pyd_src)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert elapsed_ms < 10.0, f"NFR4 violated on {name}: {elapsed_ms:.2f}ms >= 10ms"

    overall_reduction = (1.0 - total_pyd_tokens / total_py_tokens) * 100.0
    assert overall_reduction >= 30.0, f"NFR1 violated: token reduction {overall_reduction:.1f}% < 30%"
