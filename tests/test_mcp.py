"""pydense.mcp_server: the tool callables, dispatch, schemas and the stdio JSON-RPC fallback."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, get_args

import pytest

from pydense import Mode, mcp_server
from pydense.mcp_server import (
    MODES,
    SESSIONS,
    TOOL_SCHEMAS,
    dispatch,
    handle_request,
    tool_check_dpy,
    tool_execute_dpy,
    tool_get_dpy_cheatsheet,
    tool_read_file_as_dpy,
    tool_transpile_dpy,
    tool_write_dpy_file,
)
from pydense.skill import CHEATSHEET

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PY = (
    "class A:\n"
    '    """Doc."""\n'
    "\n"
    "    def __init__(self, a, b=1):\n"
    "        self.a = a\n"
    "        self.b = b\n"
    "\n"
    "    def total(self):\n"
    "        return self.a + self.b\n"
)
SAMPLE_DPY = "class A{\ndef __init__(a,b=1){\n.a=a\n.b=b}\ndef total(){\nreturn.a+.b}}"
SAMPLE_DPY_FULL = (
    'class A{\n"""Doc."""\ndef __init__(a,b=1){\n.a=a\n.b=b}\ndef total(){\nreturn.a+.b}}'
)
BAD_DPY = "def f(a){\nreturn a"  # E001: unclosed brace
DOCSTRING_GUARD_MESSAGE = (
    "!Err[write_dpy_file]: would drop {n} docstrings; "
    "re-read with mode=full or pass allow_docstring_loss=true"
)


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


@pytest.fixture(autouse=True)
def _fresh_sessions() -> None:
    SESSIONS.clear()


# --- read_file_as_dpy ----------------------------------------------------------------------------------


def test_read_file_as_dpy_default_mode_is_full_and_lossless(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text(SAMPLE_PY, encoding="utf-8")
    assert tool_read_file_as_dpy(str(path)) == SAMPLE_DPY_FULL
    assert tool_read_file_as_dpy(str(path), mode="full") == SAMPLE_DPY_FULL
    assert dispatch("read_file_as_dpy", {"file_path": str(path)}) == SAMPLE_DPY_FULL
    assert tool_read_file_as_dpy(str(path), mode="nodoc") == SAMPLE_DPY
    assert tool_read_file_as_dpy(str(path), mode="FULL") == SAMPLE_DPY_FULL  # Mode.coerce


def test_read_edit_write_round_trip_keeps_docstrings(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text(SAMPLE_PY, encoding="utf-8")
    dense = tool_read_file_as_dpy(str(path))
    edited = dense.replace("return.a+.b", "return.a*.b")
    assert tool_write_dpy_file(str(path), edited).startswith("Wrote ")
    source = path.read_text(encoding="utf-8")
    assert '"""Doc."""' in source and "return self.a * self.b" in source


def test_read_file_as_dpy_returns_raw_dpy(tmp_path: Path) -> None:
    path = tmp_path / "raw.dpy"
    path.write_text(
        "x=1   # comment kept because the file is returned verbatim\n", encoding="utf-8"
    )
    assert tool_read_file_as_dpy(str(path)) == path.read_text(encoding="utf-8")


def test_read_file_as_dpy_expands_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "h.py").write_text("x = 1\n", encoding="utf-8")
    assert tool_read_file_as_dpy("~/h.py") == "x=1"


def test_read_file_as_dpy_errors(tmp_path: Path) -> None:
    missing = tool_read_file_as_dpy(str(tmp_path / "nope.py"))
    assert missing.startswith("!Err[read_file_as_dpy]: FileNotFoundError(")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert tool_read_file_as_dpy(str(tmp_path / "a.py"), mode="bogus").startswith("!Err[")


# --- write_dpy_file ------------------------------------------------------------------------------------


def test_write_dpy_file_py_creates_parents_and_reports_bytes(tmp_path: Path) -> None:
    target = tmp_path / "pkg" / "sub" / "mod.py"
    message = tool_write_dpy_file(str(target), SAMPLE_DPY)
    assert message.startswith("Wrote ")
    assert str(target) in message and "bytes" in message
    source = target.read_text(encoding="utf-8")
    assert "def __init__(self, a, b=1):" in source
    assert not (tmp_path / "pkg" / "sub" / "mod.dpy").exists()


def test_write_dpy_file_dpy_and_both(tmp_path: Path) -> None:
    target = tmp_path / "m.py"
    tool_write_dpy_file(str(target), SAMPLE_DPY, output_format="dpy")
    assert (tmp_path / "m.dpy").read_text(encoding="utf-8") == SAMPLE_DPY
    assert not target.exists()
    message = tool_write_dpy_file(str(tmp_path / "n.dpy"), SAMPLE_DPY, output_format="both")
    assert (tmp_path / "n.py").exists() and (tmp_path / "n.dpy").exists()
    assert "n.py" in message and "n.dpy" in message


def test_write_dpy_file_never_writes_on_syntax_error(tmp_path: Path) -> None:
    target = tmp_path / "new" / "bad.py"
    message = tool_write_dpy_file(str(target), "def f(a){\nreturn a")
    assert message.startswith("!Err[write_dpy_file]")
    assert "E001" in message
    assert not target.exists()
    assert not target.parent.exists()


def test_write_dpy_file_bad_format(tmp_path: Path) -> None:
    out = tool_write_dpy_file(str(tmp_path / "x.py"), "x=1", output_format="rust")
    assert out.startswith("!Err[write_dpy_file]")
    assert not (tmp_path / "x.py").exists()


def test_write_dpy_file_refuses_to_drop_docstrings(tmp_path: Path) -> None:
    target = tmp_path / "m.py"
    target.write_text(SAMPLE_PY, encoding="utf-8")
    out = tool_write_dpy_file(str(target), SAMPLE_DPY)  # a nodoc read written back whole
    assert out == DOCSTRING_GUARD_MESSAGE.format(n=1)
    assert target.read_text(encoding="utf-8") == SAMPLE_PY
    # the same through dispatch (the transports), then the explicit opt-out
    args: dict[str, Any] = {"file_path": str(target), "dpy_code": SAMPLE_DPY}
    assert dispatch("write_dpy_file", args) == DOCSTRING_GUARD_MESSAGE.format(n=1)
    out = dispatch("write_dpy_file", {**args, "allow_docstring_loss": True})
    assert out.startswith("Wrote ")
    assert '"""Doc."""' not in target.read_text(encoding="utf-8")


def test_write_dpy_file_docstring_guard_counts_module_class_and_def(tmp_path: Path) -> None:
    target = tmp_path / "pkg" / "m.dpy"  # .dpy target: the guard looks at the .py it will write
    py_target = target.with_suffix(".py")
    py_target.parent.mkdir()
    py_target.write_text(
        '"""Module."""\n\n\nclass A:\n    """Class."""\n\n    def f(self):\n        """Def."""\n'
        "        return 1\n\n\nasync def g():\n    pass\n",
        encoding="utf-8",
    )
    out = tool_write_dpy_file(str(target), "class A{\ndef f(){\nreturn 1}}\nasync def g(){\npass}")
    assert out == DOCSTRING_GUARD_MESSAGE.format(n=3)
    assert "Class." in py_target.read_text(encoding="utf-8")
    # keeping even one docstring is a deliberate edit, not a lossy round trip: allowed
    out = tool_write_dpy_file(str(target), '"""Module."""\nclass A{\ndef f(){\nreturn 1}}')
    assert out.startswith("Wrote ")
    assert "Class." not in py_target.read_text(encoding="utf-8")


def test_write_dpy_file_docstring_guard_is_skipped_when_nothing_is_at_risk(tmp_path: Path) -> None:
    plain = tmp_path / "plain.py"
    plain.write_text("x = 1\n", encoding="utf-8")  # existing file without docstrings
    assert tool_write_dpy_file(str(plain), "x=2").startswith("Wrote ")
    broken = tmp_path / "broken.py"
    broken.write_text("def (:\n", encoding="utf-8")  # not Python: nothing to protect
    assert tool_write_dpy_file(str(broken), "x=2").startswith("Wrote ")
    missing = tmp_path / "new.py"
    assert tool_write_dpy_file(str(missing), "x=2").startswith("Wrote ")
    # dpy output never touches the .py, so the guard does not apply
    target = tmp_path / "doc.py"
    target.write_text(SAMPLE_PY, encoding="utf-8")
    assert tool_write_dpy_file(str(target), SAMPLE_DPY, output_format="dpy").startswith("Wrote ")
    assert target.read_text(encoding="utf-8") == SAMPLE_PY
    # a syntax error is reported before the guard, and nothing is written
    out = tool_write_dpy_file(str(target), BAD_DPY)
    assert out.startswith("!Err[write_dpy_file]: not written") and "E001" in out


# --- execute_dpy -------------------------------------------------------------------------------------------


def test_execute_dpy_returns_last_expression() -> None:
    assert tool_execute_dpy("a=[x**2 for x in range(5)]\nsum(a)") == "=> 30"


def test_execute_dpy_sessions_persist_and_reset() -> None:
    tool_execute_dpy("n=41", session_id="s1")
    assert tool_execute_dpy("n+1", session_id="s1") == "=> 42"
    assert tool_execute_dpy("'n' in dir()", session_id="s2") == "=> False"
    out = tool_execute_dpy("n", session_id="s1", reset_session=True)
    assert out.startswith("!Err[<module>:L1]: NameError(")


def test_execute_dpy_stdout_stderr_and_none() -> None:
    out = tool_execute_dpy("import sys\nprint('hi')\nsys.stderr.write('w1\\nw2\\n')\nNone")
    assert out == "hi\n[stderr] w1\n[stderr] w2"
    assert tool_execute_dpy("x=1") == "OK"


def test_execute_dpy_compact_error() -> None:
    out = tool_execute_dpy("def f(){\nraise ValueError('bad')}\nprint('pre')\nf()")
    assert out == "pre\n!Err[f:L2]: ValueError(bad)"


def test_execute_dpy_syntax_error_is_reported_not_raised() -> None:
    out = tool_execute_dpy("if x{")
    assert out.startswith("!Err[") and "E001" in out


# --- transpile / check / cheatsheet ------------------------------------------------------------------------


def test_transpile_both_directions() -> None:
    py = tool_transpile_dpy(SAMPLE_DPY)
    assert "return self.a + self.b" in py
    assert tool_transpile_dpy(SAMPLE_PY, direction="py_to_dpy") == SAMPLE_DPY
    assert '"""Doc."""' in tool_transpile_dpy(SAMPLE_PY, direction="py_to_dpy", mode="full")
    assert tool_transpile_dpy("x", direction="sideways").startswith("!Err[transpile_dpy]")
    assert tool_transpile_dpy("if x{", direction="dpy_to_py").startswith("!Err[transpile_dpy]")


def test_check_dpy_ok_and_diagnostics() -> None:
    assert tool_check_dpy(SAMPLE_DPY) == "OK"
    out = tool_check_dpy("if x{\ny=1")
    assert out.splitlines()[0].startswith("E001 ")
    out = tool_check_dpy("class A{\ndef f(this,x){\nreturn x}}")
    assert out.startswith("W002 ")


def test_get_dpy_cheatsheet() -> None:
    assert tool_get_dpy_cheatsheet() == CHEATSHEET
    assert dispatch("get_dpy_cheatsheet", {}) == CHEATSHEET


# --- schemas and dispatch -----------------------------------------------------------------------------------


def test_tool_schemas_match_contract() -> None:
    names = [schema["name"] for schema in TOOL_SCHEMAS]
    assert names == [
        "read_file_as_dpy",
        "write_dpy_file",
        "execute_dpy",
        "transpile_dpy",
        "check_dpy",
        "get_dpy_cheatsheet",
    ]
    by_name = {schema["name"]: schema for schema in TOOL_SCHEMAS}
    assert by_name["read_file_as_dpy"]["inputSchema"]["required"] == ["file_path"]
    assert by_name["read_file_as_dpy"]["inputSchema"]["properties"]["mode"]["default"] == "full"
    assert by_name["transpile_dpy"]["inputSchema"]["properties"]["mode"]["default"] == "nodoc"
    for name in ("read_file_as_dpy", "transpile_dpy"):
        assert by_name[name]["inputSchema"]["properties"]["mode"]["enum"] == MODES
    assert by_name["write_dpy_file"]["inputSchema"]["required"] == ["file_path", "dpy_code"]
    allow = by_name["write_dpy_file"]["inputSchema"]["properties"]["allow_docstring_loss"]
    assert allow["type"] == "boolean" and allow["default"] is False
    assert by_name["write_dpy_file"]["inputSchema"]["properties"]["output_format"]["enum"] == [
        "py",
        "dpy",
        "both",
    ]
    assert by_name["execute_dpy"]["inputSchema"]["required"] == ["dpy_code"]
    assert by_name["transpile_dpy"]["inputSchema"]["properties"]["direction"]["enum"] == [
        "dpy_to_py",
        "py_to_dpy",
    ]
    assert by_name["get_dpy_cheatsheet"]["inputSchema"]["properties"] == {}
    for schema in TOOL_SCHEMAS:
        assert schema["description"]
        assert schema["inputSchema"]["type"] == "object"


def test_mode_enum_is_derived_from_mode() -> None:
    assert MODES == [m.value for m in Mode] == ["full", "nodoc", "stripped"]
    assert get_args(mcp_server.ModeName) == tuple(MODES)
    assert list(get_args(mcp_server.OutputFormat)) == ["py", "dpy", "both"]
    assert list(get_args(mcp_server.Direction)) == ["dpy_to_py", "py_to_dpy"]


def test_dispatch_unknown_tool() -> None:
    with pytest.raises(KeyError):
        dispatch("nope", {})


# --- official SDK transport (in-process) --------------------------------------------------------------------


def _sdk_server() -> Any:
    pytest.importorskip("mcp")
    return mcp_server.build_sdk_server()


def _tool_error_types() -> tuple[type[Exception], type[Exception] | None]:
    """``(ToolError, UnexpectedToolError or None)`` for the installed SDK major version."""
    try:
        from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

        return ToolError, UnexpectedToolError
    except ImportError:
        from mcp.server.fastmcp.exceptions import ToolError  # type: ignore[import-not-found,no-redef]

        return ToolError, None


def _input_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "input_schema", None) or tool.inputSchema  # mcp 2.x / 1.x
    return schema


def _is_error(result: Any) -> bool:
    flag = getattr(result, "is_error", None)
    return bool(flag if flag is not None else getattr(result, "isError", False))


def test_sdk_server_registers_all_tools() -> None:
    server = _sdk_server()
    tools = asyncio.run(server.list_tools())
    assert sorted(t.name for t in tools) == sorted(schema["name"] for schema in TOOL_SCHEMAS)
    prompts = asyncio.run(server.list_prompts())
    assert [p.name for p in prompts] == ["pydense"]


def test_sdk_schemas_have_enums_for_literal_parameters() -> None:
    tools = {t.name: t for t in asyncio.run(_sdk_server().list_tools())}
    props = {name: _input_schema(tool)["properties"] for name, tool in tools.items()}
    assert props["read_file_as_dpy"]["mode"]["enum"] == MODES
    assert props["read_file_as_dpy"]["mode"]["default"] == "full"
    assert props["transpile_dpy"]["mode"]["enum"] == MODES
    assert props["transpile_dpy"]["mode"]["default"] == "nodoc"
    assert props["transpile_dpy"]["direction"]["enum"] == ["dpy_to_py", "py_to_dpy"]
    assert props["write_dpy_file"]["output_format"]["enum"] == ["py", "dpy", "both"]
    assert props["write_dpy_file"]["allow_docstring_loss"]["type"] == "boolean"
    assert props["write_dpy_file"]["allow_docstring_loss"]["default"] is False
    # every enum and required list in TOOL_SCHEMAS is mirrored by the SDK-derived schema
    for schema in TOOL_SCHEMAS:
        sdk = _input_schema(tools[schema["name"]])
        assert sdk.get("required", []) == schema["inputSchema"].get("required", [])
        for name, prop in schema["inputSchema"]["properties"].items():
            assert name in sdk["properties"]
            if "enum" in prop:
                assert sdk["properties"][name]["enum"] == prop["enum"], (schema["name"], name)
                assert sdk["properties"][name]["default"] == prop["default"]


def test_sdk_call_tool_reports_bad_code_as_tool_error_not_crash(tmp_path: Path) -> None:
    server = _sdk_server()
    tool_error, unexpected = _tool_error_types()
    target = tmp_path / "x.py"
    with pytest.raises(tool_error) as info:
        asyncio.run(
            server.call_tool("write_dpy_file", {"file_path": str(target), "dpy_code": BAD_DPY})
        )
    text = str(info.value)
    assert "!Err[write_dpy_file]: not written" in text
    for diagnostic in pydense_check(BAD_DPY):
        assert diagnostic in text  # "E001 2:8: ... (hint: add the missing '}')"
    assert "(hint: add the missing '}')" in text
    if unexpected is not None:
        assert not isinstance(info.value, unexpected)  # a crash would hide the text from the model
    assert not target.exists()

    with pytest.raises(tool_error) as info:
        asyncio.run(server.call_tool("execute_dpy", {"dpy_code": "if x{"}))
    text = str(info.value)
    assert "!Err[" in text and "E001" in text and "add the missing '}'" in text
    if unexpected is not None:
        assert not isinstance(info.value, unexpected)

    # a successful call still goes through the wrapper untouched
    result = asyncio.run(
        server.call_tool("write_dpy_file", {"file_path": str(tmp_path / "y.py"), "dpy_code": "x=1"})
    )
    assert not _is_error(result)
    assert result.content[0].text.startswith("Wrote ")
    assert (tmp_path / "y.py").read_text(encoding="utf-8") == "x = 1\n"


def pydense_check(code: str) -> list[str]:
    import pydense

    return [str(d) for d in pydense.check(code)]


def test_sdk_in_process_client_sees_is_error_and_text(tmp_path: Path) -> None:
    server = _sdk_server()
    try:
        from mcp import Client
    except ImportError:
        pytest.skip("mcp.Client (in-process client) needs mcp >= 2")

    async def go() -> tuple[Any, Any]:
        async with Client(server) as client:
            ok = await client.call_tool("execute_dpy", {"dpy_code": "sum([1,2,3])"})
            bad = await client.call_tool(
                "write_dpy_file", {"file_path": str(tmp_path / "x.py"), "dpy_code": BAD_DPY}
            )
            return ok, bad

    ok, bad = asyncio.run(go())
    assert not _is_error(ok) and ok.content[0].text == "=> 6"
    assert _is_error(bad)
    assert "E001" in bad.content[0].text and "add the missing '}'" in bad.content[0].text
    assert not (tmp_path / "x.py").exists()


# --- stdio JSON-RPC fallback (in-process) -------------------------------------------------------------------


def test_handle_request_notifications_are_silent() -> None:
    assert handle_request('{"jsonrpc":"2.0","method":"notifications/initialized"}') is None
    assert (
        handle_request('{"jsonrpc":"2.0","method":"notifications/cancelled","params":{}}') is None
    )


def test_handle_request_malformed_json() -> None:
    assert handle_request("this is not json") is None
    resp = handle_request('{"jsonrpc":"2.0","id":9,"method":"ping",')
    assert resp == {"jsonrpc": "2.0", "id": 9, "error": {"code": -32700, "message": "Parse error"}}
    resp = handle_request('{"id":"abc","method":')
    assert resp is not None and resp["id"] == "abc" and resp["error"]["code"] == -32700


def test_handle_request_initialize_echoes_protocol_version() -> None:
    resp = handle_request(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
    )
    assert resp is not None
    assert resp["result"]["protocolVersion"] == "2025-06-18"
    assert resp["result"]["serverInfo"]["name"] == "pydense-mcp"
    assert "tools" in resp["result"]["capabilities"] and "prompts" in resp["result"]["capabilities"]
    resp = handle_request(
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}})
    )
    assert resp is not None and resp["result"]["protocolVersion"] == "2024-11-05"


def test_handle_request_prompts() -> None:
    resp = handle_request('{"jsonrpc":"2.0","id":3,"method":"prompts/list"}')
    assert resp is not None and resp["result"]["prompts"][0]["name"] == "pydense"
    resp = handle_request(
        '{"jsonrpc":"2.0","id":4,"method":"prompts/get","params":{"name":"pydense"}}'
    )
    assert resp is not None
    assert resp["result"]["messages"][0]["content"]["text"] == CHEATSHEET
    resp = handle_request(
        '{"jsonrpc":"2.0","id":5,"method":"prompts/get","params":{"name":"other"}}'
    )
    assert resp is not None and resp["error"]["code"] == -32602


def test_handle_request_tools_call_unknown_tool_is_invalid_params() -> None:
    resp = handle_request(
        '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"nope","arguments":{}}}'
    )
    assert resp is not None and resp["error"]["code"] == -32602


# --- stdio JSON-RPC fallback (subprocess, scripted conversation) ------------------------------------------------


def _conversation(tmp_path: Path) -> list[dict]:
    return [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "execute_dpy",
                "arguments": {"dpy_code": "a=[x**2 for x in range(5)]\nprint('hi')\nsum(a)"},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "write_dpy_file",
                "arguments": {"file_path": str(tmp_path / "out" / "m.py"), "dpy_code": SAMPLE_DPY},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "execute_dpy",
                "arguments": {"dpy_code": "def f(){\nraise ValueError('bad')}\nf()"},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "check_dpy", "arguments": {}},
        },
        {"jsonrpc": "2.0", "id": 7, "method": "ping"},
        {"jsonrpc": "2.0", "id": 8, "method": "no/such/method"},
        {"jsonrpc": "2.0", "id": 9, "method": "prompts/get", "params": {"name": "pydense"}},
    ]


def test_stdio_fallback_scripted_conversation(tmp_path: Path) -> None:
    messages = _conversation(tmp_path)
    stdin = "".join(json.dumps(m) + "\n" for m in messages) + "not json at all\n"
    env = _subprocess_env()
    proc = subprocess.run(
        [sys.executable, "-m", "pydense.mcp_server", "--stdio-fallback"],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    # one reply per request; the notification and the malformed line produce nothing
    assert [r["id"] for r in responses] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert all(r["jsonrpc"] == "2.0" for r in responses)
    by_id = {r["id"]: r for r in responses}

    init = by_id[1]["result"]
    assert init["protocolVersion"] == "2025-03-26"
    assert init["serverInfo"] == {"name": "pydense-mcp", "version": mcp_server.__version__}

    tools = by_id[2]["result"]["tools"]
    assert [t["name"] for t in tools] == [s["name"] for s in TOOL_SCHEMAS]

    call = by_id[3]["result"]
    assert call["isError"] is False
    assert call["content"] == [{"type": "text", "text": "hi\n=> 30"}]

    write = by_id[4]["result"]
    assert write["isError"] is False
    assert write["content"][0]["text"].startswith("Wrote ")
    assert (tmp_path / "out" / "m.py").exists()

    failed = by_id[5]["result"]
    assert failed["isError"] is True
    assert failed["content"][0]["text"] == "!Err[f:L2]: ValueError(bad)"

    bad_args = by_id[6]["result"]
    assert bad_args["isError"] is True
    assert bad_args["content"][0]["text"].startswith("!Err[check_dpy]: TypeError(")

    assert by_id[7]["result"] == {}
    assert by_id[8]["error"]["code"] == -32601
    assert by_id[9]["result"]["messages"][0]["content"]["text"] == CHEATSHEET


# --- official SDK transport (real stdio client against a server subprocess) -------------------------------------


def test_sdk_stdio_client_round_trip(tmp_path: Path) -> None:
    pytest.importorskip("mcp")
    try:
        from mcp import StdioServerParameters
    except ImportError:  # pragma: no cover - very old mcp
        pytest.skip("mcp has no stdio client API")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pydense.mcp_server"],
        env=_subprocess_env(),
        cwd=str(tmp_path),
    )
    target = tmp_path / "out" / "m.py"
    calls = [
        ("execute_dpy", {"dpy_code": "a=[x**2 for x in range(5)]\nprint('hi')\nsum(a)"}),
        ("write_dpy_file", {"file_path": str(target), "dpy_code": BAD_DPY}),
        ("write_dpy_file", {"file_path": str(target), "dpy_code": SAMPLE_DPY_FULL}),
        ("read_file_as_dpy", {"file_path": str(target)}),
    ]

    async def with_client() -> tuple[Any, Any, list[Any]]:
        from mcp import Client

        async with Client(params) as client:
            init = client.initialize_result if hasattr(client, "initialize_result") else None
            tools = await client.list_tools()
            results = [await client.call_tool(name, args) for name, args in calls]
            return init, tools, results

    async def with_session() -> tuple[Any, Any, list[Any]]:
        from mcp import ClientSession, stdio_client

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                results = [await session.call_tool(name, args) for name, args in calls]
                return init, tools, results

    try:
        import mcp

        runner = with_client if hasattr(mcp, "Client") else with_session
        init, tools, results = asyncio.run(asyncio.wait_for(runner(), timeout=120))
    except OSError as exc:  # pragma: no cover - sandboxed CI without subprocess support
        pytest.skip(f"cannot spawn the server: {exc}")

    if init is not None:
        assert init.serverInfo.name == "pydense-mcp"
    assert sorted(t.name for t in tools.tools) == sorted(s["name"] for s in TOOL_SCHEMAS)
    run, bad_write, good_write, read_back = results
    assert not _is_error(run) and run.content[0].text == "hi\n=> 30"
    assert _is_error(bad_write)
    text = bad_write.content[0].text
    assert "E001" in text and "add the missing '}'" in text and "!Err[write_dpy_file]" in text
    assert not _is_error(good_write) and good_write.content[0].text.startswith("Wrote ")
    assert '"""Doc."""' in target.read_text(encoding="utf-8")
    assert not _is_error(read_back) and read_back.content[0].text == SAMPLE_DPY_FULL
