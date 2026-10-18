"""``pydense-mcp``: the PyDense MCP server.

The six tools are plain callables (``tool_*``) shared by two transports: the official ``mcp`` SDK
server (``MCPServer`` in mcp 2.x, ``FastMCP`` in mcp 1.x) when it is importable, and a
zero-dependency newline-delimited JSON-RPC 2.0 stdio loop otherwise (or with ``--stdio-fallback``).
Sessions for ``execute_dpy`` are per-process dictionaries keyed by ``session_id``.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, get_args

from ._version import __version__
from .emitter import Mode
from .skill import AGENT_WORKFLOW, CHEATSHEET

__all__ = [
    "MODES",
    "SESSIONS",
    "TOOL_SCHEMAS",
    "build_sdk_server",
    "dispatch",
    "handle_request",
    "main",
    "run_stdio_fallback",
    "tool_check_dpy",
    "tool_execute_dpy",
    "tool_get_dpy_cheatsheet",
    "tool_read_file_as_dpy",
    "tool_transpile_dpy",
    "tool_write_dpy_file",
]

SERVER_NAME = "pydense-mcp"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
PROMPT_NAME = "pydense"
USAGE = "usage: pydense-mcp [-h] [--self-test] [--stdio-fallback]"

SESSIONS: dict[str, dict[str, Any]] = {}

# The ``Literal`` aliases type the tool signatures so the SDK derives JSON-schema enums from them;
# ``MODES`` is the single source for the mode enum (``Mode.coerce`` does the validation).
ModeName = Literal["full", "nodoc", "stripped"]
OutputFormat = Literal["py", "dpy", "both"]
Direction = Literal["dpy_to_py", "py_to_dpy"]

MODES: list[str] = [m.value for m in Mode]
_FORMATS: tuple[str, ...] = get_args(OutputFormat)
_DIRECTIONS: tuple[str, ...] = get_args(Direction)

_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _err(tool: str, exc: BaseException) -> str:
    text = " ".join(str(exc).splitlines()) or type(exc).__name__
    return f"!Err[{tool}]: {type(exc).__name__}({text})"


def _path(file_path: str) -> Path:
    return Path(file_path).expanduser()


def _count_docstrings(tree: ast.AST) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, _DOCSTRING_OWNERS) and ast.get_docstring(node, clean=False) is not None
    )


def _docstrings_at_risk(py_path: Path, new_tree: ast.AST) -> int:
    """Docstrings in the existing ``py_path`` that ``new_tree`` (with none) would delete."""
    if not py_path.is_file():
        return 0
    try:
        existing = _count_docstrings(ast.parse(py_path.read_text(encoding="utf-8")))
    except (OSError, SyntaxError, ValueError):  # not (valid) Python: nothing to protect
        return 0
    if existing and _count_docstrings(new_tree) == 0:
        return existing
    return 0


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------


def tool_read_file_as_dpy(file_path: str, mode: ModeName = "full") -> str:
    """Read a Python file as PyDense (.dpy) text to save input tokens.

    A file that already ends in ``.dpy`` is returned verbatim. ``mode`` is ``full`` (default,
    lossless: safe to edit and write back), ``nodoc`` (docstrings dropped) or ``stripped`` (also
    drops annotations); the last two are read-only views.
    """
    import pydense

    try:
        path = _path(file_path)
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".dpy":
            return text
        return pydense.encode(text, mode=Mode.coerce(mode), filename=str(path))
    except Exception as exc:
        return _err("read_file_as_dpy", exc)


def tool_write_dpy_file(
    file_path: str,
    dpy_code: str,
    output_format: OutputFormat = "py",
    allow_docstring_loss: bool = False,
) -> str:
    """Write PyDense code to disk as clean Python (``py``), dense text (``dpy``) or ``both``.

    Nothing is written when ``dpy_code`` does not parse; the diagnostics are returned instead.
    Parent directories are created. With ``py`` the target keeps ``file_path`` unless it ends in
    ``.dpy`` (then ``.py`` is substituted); with ``dpy`` the suffix becomes ``.dpy``.
    When the target ``.py`` exists and has docstrings that ``dpy_code`` lacks entirely (typically a
    ``nodoc`` read written back), the write is refused unless ``allow_docstring_loss`` is true.
    """
    import pydense

    if output_format not in _FORMATS:
        return _err(
            "write_dpy_file", ValueError(f"output_format must be one of {', '.join(_FORMATS)}")
        )
    try:
        path = _path(file_path)
        diagnostics = pydense.check(dpy_code, filename=str(path))
        errors = [d for d in diagnostics if d.severity == "error"]
        if errors:
            lines = [str(d) for d in diagnostics]
            return "!Err[write_dpy_file]: not written, fix the syntax error first\n" + "\n".join(
                lines
            )
        warnings = [str(d) for d in diagnostics]
        py_path = path.with_suffix(".py") if path.suffix == ".dpy" else path
        if output_format in ("py", "both") and not allow_docstring_loss:
            tree = pydense.parse(dpy_code, filename=str(path))
            dropped = _docstrings_at_risk(py_path, tree)
            if dropped:
                return (
                    f"!Err[write_dpy_file]: would drop {dropped} docstrings; "
                    "re-read with mode=full or pass allow_docstring_loss=true"
                )
        written: list[str] = []
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if output_format in ("py", "both"):
                source = pydense.decode(dpy_code, filename=str(path))
                py_path.write_text(source, encoding="utf-8")
                written.append(f"{py_path} ({len(source.encode('utf-8'))} bytes of Python)")
            if output_format in ("dpy", "both"):
                dpy_path = path.with_suffix(".dpy")
                dpy_path.write_text(dpy_code, encoding="utf-8")
                written.append(f"{dpy_path} ({len(dpy_code.encode('utf-8'))} bytes of PyDense)")
        except OSError as exc:
            done = ("; already written: " + ", ".join(written)) if written else ""
            return f"!Err[write_dpy_file]: {type(exc).__name__}: {exc}{done}"
        message = "Wrote " + " and ".join(written)
        if warnings:
            message += "\nwarnings:\n" + "\n".join(warnings)
        return message
    except Exception as exc:
        return _err("write_dpy_file", exc)


def tool_execute_dpy(
    dpy_code: str, session_id: str = "default", reset_session: bool = False
) -> str:
    """Execute PyDense code in a persistent REPL session (Jupyter semantics).

    Returns captured stdout, ``[stderr] ...`` lines, ``=> repr`` of a trailing expression, or an
    ``!Err[frame:Lline]: Type(msg)`` compact traceback. ``reset_session`` clears the session first.
    """
    from .runtime import run_repl

    if reset_session or session_id not in SESSIONS:
        SESSIONS[session_id] = {"__name__": "__main__"}
    result = run_repl(dpy_code, SESSIONS[session_id], filename="<dpy>")
    parts: list[str] = []
    if result.stdout:
        parts.append(result.stdout.rstrip("\n"))
    if result.stderr:
        parts.extend(f"[stderr] {line}" for line in result.stderr.rstrip("\n").splitlines())
    if result.error is not None:
        parts.append(result.error)
    elif result.value_repr is not None:
        parts.append(f"=> {result.value_repr}")
    return "\n".join(parts) if parts else "OK"


def tool_transpile_dpy(
    code: str, direction: Direction = "dpy_to_py", mode: ModeName = "nodoc"
) -> str:
    """Convert between PyDense and Python without executing or saving anything.

    ``direction`` is ``dpy_to_py`` (default) or ``py_to_dpy``; ``mode`` applies to ``py_to_dpy``.
    """
    import pydense

    try:
        if direction == "dpy_to_py":
            return pydense.decode(code)
        if direction == "py_to_dpy":
            return pydense.encode(code, mode=Mode.coerce(mode))
        raise ValueError(f"direction must be one of {', '.join(_DIRECTIONS)}; got {direction!r}")
    except Exception as exc:
        return _err("transpile_dpy", exc)


def tool_check_dpy(dpy_code: str) -> str:
    """Check PyDense code: ``OK`` or one diagnostic per line (``CODE line:col: message (hint)``)."""
    import pydense

    try:
        diagnostics = pydense.check(dpy_code)
    except Exception as exc:
        return _err("check_dpy", exc)
    return "\n".join(str(d) for d in diagnostics) if diagnostics else "OK"


def tool_get_dpy_cheatsheet() -> str:
    """Return the 418-token PyDense cheat sheet."""
    return CHEATSHEET


# ---------------------------------------------------------------------------
# schemas and dispatch (shared by both transports)
# ---------------------------------------------------------------------------


def _mode_schema(default: str) -> dict[str, Any]:
    return {
        "type": "string",
        "enum": list(MODES),
        "default": default,
        "description": (
            "full: lossless, docstrings kept; nodoc: docstrings dropped; stripped: also drops "
            "annotations. nodoc and stripped are read-only views: never write them back whole."
        ),
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "read_file_as_dpy",
        "description": (
            "Read a Python file as PyDense (.dpy), a whitespace-free brace-blocked Python with the "
            "same AST, to spend fewer input tokens. A .dpy file is returned as is."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to a .py or .dpy file."},
                "mode": _mode_schema("full"),
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_dpy_file",
        "description": (
            "Write PyDense code to disk as clean standard Python (.py), as dense text (.dpy) or "
            "both. Nothing is written when the code does not parse; diagnostics come back instead. "
            "Refuses to replace a .py that has docstrings with code that has none unless "
            "allow_docstring_loss is true."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Target path, e.g. src/mod.py."},
                "dpy_code": {"type": "string", "description": "The module written in PyDense."},
                "output_format": {
                    "type": "string",
                    "enum": list(_FORMATS),
                    "default": "py",
                    "description": "py: clean Python; dpy: dense text; both: both files.",
                },
                "allow_docstring_loss": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Overwrite an existing .py that has docstrings with code that has none."
                    ),
                },
            },
            "required": ["file_path", "dpy_code"],
        },
    },
    {
        "name": "execute_dpy",
        "description": (
            "Execute PyDense code in a persistent REPL session. Returns stdout, [stderr] lines, "
            "=> repr of the last expression, or an !Err[frame:Lline]: Type(msg) compact traceback."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dpy_code": {"type": "string", "description": "PyDense code to execute."},
                "session_id": {
                    "type": "string",
                    "default": "default",
                    "description": "Session key.",
                },
                "reset_session": {
                    "type": "boolean",
                    "default": False,
                    "description": "Clear the session before running.",
                },
            },
            "required": ["dpy_code"],
        },
    },
    {
        "name": "transpile_dpy",
        "description": "Convert between PyDense and Python without executing or saving.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Source text to convert."},
                "direction": {"type": "string", "enum": list(_DIRECTIONS), "default": "dpy_to_py"},
                "mode": _mode_schema("nodoc"),
            },
            "required": ["code"],
        },
    },
    {
        "name": "check_dpy",
        "description": (
            "Parse and lint PyDense code; returns OK or one diagnostic per line with a fix hint."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"dpy_code": {"type": "string", "description": "PyDense code to check."}},
            "required": ["dpy_code"],
        },
    },
    {
        "name": "get_dpy_cheatsheet",
        "description": "Return the 418-token PyDense cheat sheet (how to write .dpy).",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

_TOOLS: dict[str, Callable[..., str]] = {
    "read_file_as_dpy": tool_read_file_as_dpy,
    "write_dpy_file": tool_write_dpy_file,
    "execute_dpy": tool_execute_dpy,
    "transpile_dpy": tool_transpile_dpy,
    "check_dpy": tool_check_dpy,
    "get_dpy_cheatsheet": tool_get_dpy_cheatsheet,
}


def dispatch(name: str, arguments: dict[str, Any] | None = None) -> str:
    """Call tool ``name`` with ``arguments``. Raises ``KeyError`` for an unknown tool."""
    if name not in _TOOLS:
        raise KeyError(f"unknown tool: {name}")
    return _TOOLS[name](**(arguments or {}))


# ---------------------------------------------------------------------------
# zero-dependency stdio JSON-RPC 2.0 transport
# ---------------------------------------------------------------------------


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _prompt_descriptor() -> dict[str, Any]:
    return {
        "name": PROMPT_NAME,
        "description": "The PyDense (.dpy) cheat sheet: how to read and write dense Python.",
        "arguments": [],
    }


def _handle_method(method: str, params: dict[str, Any]) -> dict[str, Any]:
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "prompts": {}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "instructions": AGENT_WORKFLOW,
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOL_SCHEMAS}
    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        if name not in _TOOLS:
            raise _RpcError(-32602, f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            raise _RpcError(-32602, "arguments must be an object")
        try:
            text = dispatch(name, arguments)
            is_error = text.startswith("!Err")
        except Exception as exc:  # bad arguments, unexpected tool failure
            text, is_error = _err(name, exc), True
        return {"content": [{"type": "text", "text": text}], "isError": is_error}
    if method == "prompts/list":
        return {"prompts": [_prompt_descriptor()]}
    if method == "prompts/get":
        name = params.get("name", PROMPT_NAME)
        if name != PROMPT_NAME:
            raise _RpcError(-32602, f"Unknown prompt: {name}")
        return {
            "description": _prompt_descriptor()["description"],
            "messages": [{"role": "user", "content": {"type": "text", "text": CHEATSHEET}}],
        }
    if method == "resources/list":
        return {"resources": []}
    raise _RpcError(-32601, f"Method not found: {method}")


_ID_RE = re.compile(r'"id"\s*:\s*("(?:[^"\\]|\\.)*"|-?\d+)')


def handle_request(line: str) -> dict[str, Any] | None:
    """Handle one newline-delimited JSON-RPC message; return the response or ``None`` (no reply)."""
    try:
        request = json.loads(line)
    except ValueError:
        match = _ID_RE.search(line)
        if match is None:
            return None
        try:
            recovered = json.loads(match.group(1))
        except ValueError:
            return None
        return {
            "jsonrpc": "2.0",
            "id": recovered,
            "error": {"code": -32700, "message": "Parse error"},
        }
    if not isinstance(request, dict):
        return None
    request_id = request.get("id")
    if request_id is None:  # notification (notifications/initialized, cancelled, ...)
        return None
    method = request.get("method")
    params = request.get("params") or {}
    if not isinstance(method, str):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32600, "message": "Invalid Request"},
        }
    if not isinstance(params, dict):
        params = {}
    try:
        result = _handle_method(method, params)
    except _RpcError as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": exc.code, "message": str(exc)},
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(exc)}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def run_stdio_fallback(stdin: Any = None, stdout: Any = None) -> None:
    """Serve newline-delimited JSON-RPC 2.0 over stdio until EOF."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    for raw in stdin:
        line = raw.strip()
        if not line:
            continue
        response = handle_request(line)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
            stdout.flush()


# ---------------------------------------------------------------------------
# official SDK transport
# ---------------------------------------------------------------------------


def _tool_error_type() -> type[Exception]:
    """The SDK's anticipated-failure exception: its text reaches the model with ``isError``.

    Any other exception is treated as a crash by mcp 2.x (the client sees only
    ``Error executing tool X``), hence the lookup with a 1.x fallback.
    """
    try:
        from mcp.server.mcpserver.exceptions import ToolError  # mcp >= 2
    except ImportError:
        try:
            from mcp.server.fastmcp.exceptions import (  # type: ignore[import-not-found,no-redef]
                ToolError,
            )
        except ImportError:  # pragma: no cover - neither layout: the SDK still sets isError
            return RuntimeError
    return ToolError


def _as_error_raising(func: Any, error_type: type[Exception]) -> Any:
    """Wrap a tool so an ``!Err`` text result becomes ``error_type`` (the SDK then sets isError)."""
    import functools

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        result = func(*args, **kwargs)
        if isinstance(result, str) and result.startswith("!Err"):
            raise error_type(result)
        return result

    return wrapper


def build_sdk_server() -> Any:
    """Build an ``mcp`` SDK server with the six tools and the prompt registered.

    Raises ``ImportError`` when the ``mcp`` package is not installed.
    """
    try:
        from mcp.server.mcpserver import MCPServer as Server  # mcp >= 2
    except ImportError:
        from mcp.server.fastmcp import FastMCP as Server  # type: ignore[attr-defined,no-redef]  # mcp 1.x

    tool_error = _tool_error_type()
    server = Server(SERVER_NAME, instructions=AGENT_WORKFLOW)
    for schema in TOOL_SCHEMAS:
        server.tool(name=schema["name"], description=schema["description"])(
            _as_error_raising(_TOOLS[schema["name"]], tool_error)
        )

    def pydense_cheatsheet() -> str:
        """The PyDense (.dpy) cheat sheet: how to read and write dense Python."""
        return CHEATSHEET

    server.prompt(name=PROMPT_NAME, description=_prompt_descriptor()["description"])(
        pydense_cheatsheet
    )
    return server


def self_test() -> int:
    """Exercise every tool once through ``dispatch`` and print the results."""
    calls: list[tuple[str, dict[str, Any]]] = [
        ("execute_dpy", {"dpy_code": "a=[x**2 for x in range(5)]\nsum(a)", "reset_session": True}),
        ("execute_dpy", {"dpy_code": "[v+10 for v in a]"}),
        ("execute_dpy", {"dpy_code": "def f(){\nraise ValueError('boom')}\nf()"}),
        ("transpile_dpy", {"code": "class A{\ndef __init__(x){\n.x=x}}", "direction": "dpy_to_py"}),
        (
            "transpile_dpy",
            {"code": "def f(a, b=1):\n    return a if b else -a\n", "direction": "py_to_dpy"},
        ),
        ("check_dpy", {"dpy_code": "if x{\ny=1"}),
        ("get_dpy_cheatsheet", {}),
    ]
    failures = 0
    for name, args in calls:
        try:
            out = dispatch(name, args)
        except Exception as exc:  # noqa: BLE001 - report and continue
            out, failures = f"EXCEPTION {type(exc).__name__}: {exc}", failures + 1
        print(f"--- {name}({json.dumps(args)[:70]})\n{out}\n")
    print("self-test:", "OK" if failures == 0 else f"{failures} failure(s)")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    """Console entry point: ``pydense-mcp [--self-test] [--stdio-fallback]``."""
    args = sys.argv[1:] if argv is None else argv
    if "--help" in args or "-h" in args:
        print(
            f"{USAGE}\n\n"
            "PyDense MCP server over stdio: six tools and the cheat-sheet prompt.\n\n"
            "  --self-test       run every tool once through dispatch and exit\n"
            "  --stdio-fallback  serve newline-delimited JSON-RPC 2.0 without the mcp package"
        )
        return 0
    if "--self-test" in args:
        return self_test()
    if "--stdio-fallback" not in args:
        try:
            server = build_sdk_server()
        except ImportError:
            server = None
        if server is not None:
            server.run(transport="stdio")
            return 0
    run_stdio_fallback()
    return 0


if __name__ == "__main__":
    sys.exit(main())
