#!/usr/bin/env python3
"""
PyDense MCP (Model Context Protocol) Server v0.1
Exposes PyDense execution, context-compression reading, and hybrid .pyd->.py file writing
to VSCode (GitHub Copilot / Cline / Roo), Cursor, and Claude Code.
"""

from __future__ import annotations
import ast
import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict

from pydense import PyDenseCompiler, PyDenseDecompiler, PyDenseRunner

# ============================================================================
# 1. STATEFUL SESSION REGISTRY & COMPACT SKILL SPEC
# ============================================================================

SESSIONS: Dict[str, Dict[str, Any]] = {}

SKILL_CHEATSHEET = """# PyDense (.pyd) Quick Syntax Reference
- Blocks: `{stmt1;stmt2}` (no indentation, `;` between statements, omit `;` after `}`)
- Class/Func: `@c Name(Base){...}` | `@i(a,b=1){...}` (__init__) | `@f fn(a,b){...}` | `@af` (async) | `@sf` (static)
- Implicit self & pos-args: `.x` -> `self.x` | `$0`, `$1` -> 1st, 2nd function param
- Control: `?c{...}:?c2{...}:{...}` (if/elif/else) | `c??t:f` (ternary) | `~x:it{...}` (for) | `~?c{...}` (while)
- Exceptions & Context: `!{...}!Exc:e{...}!*{...}` (try/except/finally) | `@w expr:v{...}` (with)
- Flow & Logic: `^x` (return) | `^>x` (yield) | `^!` (break) | `^~` (continue) | `^@e` (raise) | `&&` `||` `!` `@in` `!@in` `@is` `!@is`
- Comprehensions: `[expr~x:it?cond]` | `{k:v~k,v:it?cond}` | Lambda: `\\a,b:a+b`
- Constants & Macros: `#T` `#F` `#N` | `#np` `#pd` `#sp` `#os` `#sys` `#js` `#re` `#m` `#dt` `#pl` `#as`
- Builtins: `%p`(print) `%l`(len) `%r`(range) `%e`(enumerate) `%z`(zip) `%s`(sum) `%m`(map) `%f`(filter) `%d`(dict) `%li`(list) `%st`(set) `%i`(isinstance) `%a`(abs) `%mn`(min) `%mx`(max) `%rd`(round) `%o`(open)
"""


# ============================================================================
# 2. CORE TOOL IMPLEMENTATIONS
# ============================================================================

def tool_execute_pydense(
    pyd_code: str,
    session_id: str = "default",
    reset_session: bool = False,
) -> str:
    """
    Compiles and executes PyDense (.pyd) code in a persistent in-memory Python session.
    Automatically evaluates and returns the final expression (REPL style) plus stdout.
    """
    if reset_session or session_id not in SESSIONS:
        SESSIONS[session_id] = {"__name__": "__main__"}

    env = SESSIONS[session_id]
    compiler = PyDenseCompiler()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        tree = compiler.compile_to_ast(pyd_code, filename="<pydense>")
        last_expr_val = None

        # If final statement is an expression, split it to evaluate & return REPL-style
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_expr_node = tree.body.pop()
            exec_mod = ast.Module(body=tree.body, type_ignores=[])
            ast.fix_missing_locations(exec_mod)
            eval_expr = ast.Expression(body=last_expr_node.value)
            ast.fix_missing_locations(eval_expr)

            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                if exec_mod.body:
                    exec(compile(exec_mod, "<pydense>", "exec"), env)
                last_expr_val = eval(compile(eval_expr, "<pydense>", "eval"), env)
        else:
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                exec(compile(tree, "<pydense>", "exec"), env)

        out_parts = []
        if stdout_buf.getvalue():
            out_parts.append(stdout_buf.getvalue().rstrip())
        if stderr_buf.getvalue():
            out_parts.append(f"[stderr] {stderr_buf.getvalue().rstrip()}")
        if last_expr_val is not None:
            out_parts.append(f"=> {last_expr_val!r}")

        return "\n".join(out_parts) if out_parts else "OK (no output)"

    except Exception as exc:
        return PyDenseRunner.format_compact_error(exc)


def tool_write_pydense_module(
    file_path: str,
    pyd_code: str,
    output_format: str = "py",
) -> str:
    """
    Takes ultra-compact PyDense (.pyd) code from the AI agent and writes it to disk.
    - output_format='py' (default): Transpiles .pyd to clean, standard Python (.py) before saving.
    - output_format='pyd': Saves raw .pyd code directly.
    - output_format='both': Saves both .py and .pyd side-by-side.
    """
    compiler = PyDenseCompiler()
    try:
        tree = compiler.compile_to_ast(pyd_code, filename=file_path)
        clean_py = ast.unparse(tree) + "\n"
    except Exception as exc:
        return f"Transpilation failed — file not written: {PyDenseRunner.format_compact_error(exc)}"

    target = Path(file_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    written_files = []
    if output_format in ("py", "both"):
        py_path = target.with_suffix(".py") if output_format == "both" else target
        py_path.write_text(clean_py, encoding="utf-8")
        written_files.append(str(py_path))

    if output_format in ("pyd", "both"):
        pyd_path = target.with_suffix(".pyd")
        pyd_path.write_text(pyd_code.strip() + "\n", encoding="utf-8")
        written_files.append(str(pyd_path))

    pyd_len = len(pyd_code)
    py_len = len(clean_py)
    saved_pct = (1.0 - pyd_len / max(py_len, 1)) * 100.0
    return (
        f"Saved {', '.join(written_files)} | "
        f"Agent emitted {pyd_len} .pyd chars vs {py_len} .py chars ({saved_pct:.1f}% compression)"
    )


def tool_read_file_as_pydense(
    file_path: str,
    use_positional_args: bool = True,
) -> str:
    """
    Reads a Python (.py) file from disk and compresses it into PyDense (.pyd) on the fly,
    cutting input context token usage by ~50%.
    """
    target = Path(file_path).expanduser().resolve()
    if not target.exists():
        return f"!Err[FileNotFound]: {file_path}"

    raw_src = target.read_text(encoding="utf-8")
    if target.suffix == ".pyd":
        return raw_src

    decompiler = PyDenseDecompiler(use_positional_args=use_positional_args)
    try:
        return decompiler.decompile(raw_src)
    except Exception:
        # Fault-tolerant per-statement fallback for unsupported edge-case syntax
        tree = ast.parse(raw_src)
        chunks = []
        for stmt in tree.body:
            try:
                single_mod = ast.Module(body=[stmt], type_ignores=[])
                piece = decompiler.visit_Module(single_mod)
                if piece:
                    chunks.append(piece)
            except Exception:
                chunks.append(ast.unparse(stmt))
        return ";".join(chunks)


def tool_transpile_preview(code: str, direction: str = "pyd_to_py") -> str:
    """
    Previews transpilation without writing to disk or executing.
    - direction='pyd_to_py': Converts .pyd string into formatted Python source.
    - direction='py_to_pyd': Compresses Python source into .pyd string.
    """
    try:
        if direction == "pyd_to_py":
            tree = PyDenseCompiler().compile_to_ast(code)
            return ast.unparse(tree)
        elif direction == "py_to_pyd":
            return PyDenseDecompiler().decompile(code)
        return f"!Err: Unknown direction '{direction}'. Use 'pyd_to_py' or 'py_to_pyd'."
    except Exception as exc:
        return PyDenseRunner.format_compact_error(exc)


# ============================================================================
# 3. DUAL-ENGINE MCP TRANSPORT (FastMCP + Zero-Dependency Stdio Fallback)
# ============================================================================

TOOL_SCHEMAS = [
    {
        "name": "execute_pydense",
        "description": (
            "Execute ultra-compact PyDense (.pyd) code in a stateful Python REPL session. "
            "Always prefer writing .pyd here instead of verbose Python to save ~50% output tokens. "
            "Syntax summary: @c Class, @i __init__, @f def, .x self.x, $0/$1 pos args, ?/:?/: if/elif/else, "
            "~x:it for, ^ return, #np/#pd/#m/#js macros, %l/%r/%s/%p builtins."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pyd_code": {"type": "string", "description": "Valid whitespace-free PyDense (.pyd) code to execute."},
                "session_id": {"type": "string", "default": "default", "description": "REPL session namespace ID."},
                "reset_session": {"type": "boolean", "default": False, "description": "Clear session state before run."},
            },
            "required": ["pyd_code"],
        },
    },
    {
        "name": "write_pydense_module",
        "description": (
            "Write code to disk by emitting compact PyDense (.pyd) in the tool call while automatically "
            "transpiling and saving clean, standard PEP-8 Python (.py) to the filesystem."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Target file path (e.g. 'src/optimizer.py')."},
                "pyd_code": {"type": "string", "description": "The module implementation written in PyDense (.pyd)."},
                "output_format": {
                    "type": "string",
                    "enum": ["py", "pyd", "both"],
                    "default": "py",
                    "description": "'py' saves clean Python, 'pyd' saves raw PyDense, 'both' saves both.",
                },
            },
            "required": ["file_path", "pyd_code"],
        },
    },
    {
        "name": "read_file_as_pydense",
        "description": (
            "Read a Python (.py) file from disk compressed into PyDense (.pyd) to save ~50% input context tokens."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the .py or .pyd file to read."},
                "use_positional_args": {
                    "type": "boolean",
                    "default": True,
                    "description": "Replace function parameter references with $0, $1 shorthands.",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "transpile_preview",
        "description": "Convert between PyDense (.pyd) and standard Python (.py) without executing or saving.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Source code to convert."},
                "direction": {"type": "string", "enum": ["pyd_to_py", "py_to_pyd"], "default": "pyd_to_py"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "get_pydense_skill_spec",
        "description": "Return the compact PyDense (.pyd) grammar specification and macro cheat sheet.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _dispatch_tool(name: str, args: Dict[str, Any]) -> str:
    if name == "execute_pydense":
        return tool_execute_pydense(
            pyd_code=args["pyd_code"],
            session_id=args.get("session_id", "default"),
            reset_session=args.get("reset_session", False),
        )
    if name == "write_pydense_module":
        return tool_write_pydense_module(
            file_path=args["file_path"],
            pyd_code=args["pyd_code"],
            output_format=args.get("output_format", "py"),
        )
    if name == "read_file_as_pydense":
        return tool_read_file_as_pydense(
            file_path=args["file_path"],
            use_positional_args=args.get("use_positional_args", True),
        )
    if name == "transpile_preview":
        return tool_transpile_preview(
            code=args["code"],
            direction=args.get("direction", "pyd_to_py"),
        )
    if name == "get_pydense_skill_spec":
        return SKILL_CHEATSHEET
    raise ValueError(f"Unknown tool: {name}")


def run_builtin_stdio_server() -> None:
    """Zero-dependency MCP JSON-RPC 2.0 stdio transport loop."""
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        # Notifications (no id) require no response
        if req_id is None:
            continue

        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "prompts": {}},
                "serverInfo": {"name": "pydense-mcp", "version": "0.1.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOL_SCHEMAS}
        elif method == "tools/call":
            t_name = params.get("name", "")
            t_args = params.get("arguments", {})
            try:
                text_out = _dispatch_tool(t_name, t_args)
                result = {"content": [{"type": "text", "text": text_out}], "isError": False}
            except Exception as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        elif method == "prompts/list":
            result = {
                "prompts": [
                    {
                        "name": "pydense-skill",
                        "description": "Activate PyDense (.pyd) 50% token-saving coding mode",
                    }
                ]
            }
        elif method == "prompts/get":
            result = {
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": SKILL_CHEATSHEET},
                    }
                ]
            }
        elif method == "ping":
            result = {}
        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


def main() -> None:
    # Support a quick "--self-test" flag to verify all MCP tools from the terminal
    if "--self-test" in sys.argv:
        print("=== Testing PyDense MCP Server Tools ===")
        res1 = _dispatch_tool("execute_pydense", {"pyd_code": "a=[x**2~x:%r(5)];%s(a)"})
        print(f"1. execute_pydense (stateful step 1) -> {res1}")
        res2 = _dispatch_tool("execute_pydense", {"pyd_code": "[v+10~v:a]"})
        print(f"2. execute_pydense (stateful step 2) -> {res2}")
        res3 = _dispatch_tool(
            "transpile_preview",
            {"code": "@f zscore(s){m=$0.mean();sd=$0.std();^sd>0??($0-m)/sd:$0*0.0}", "direction": "pyd_to_py"},
        )
        print(f"3. transpile_preview (.pyd -> .py):\n{res3}")
        return

    # Use official FastMCP if installed unless --stdio-fallback is passed
    if "--stdio-fallback" not in sys.argv:
        try:
            from mcp.server.fastmcp import FastMCP

            mcp = FastMCP("pydense-mcp")
            mcp.tool(name="execute_pydense")(tool_execute_pydense)
            mcp.tool(name="write_pydense_module")(tool_write_pydense_module)
            mcp.tool(name="read_file_as_pydense")(tool_read_file_as_pydense)
            mcp.tool(name="transpile_preview")(tool_transpile_preview)
            mcp.tool(name="get_pydense_skill_spec")(lambda: SKILL_CHEATSHEET)
            mcp.run(transport="stdio")
            return
        except ImportError:
            pass

    run_builtin_stdio_server()


if __name__ == "__main__":
    main()