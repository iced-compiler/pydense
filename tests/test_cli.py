"""The ``pydense`` console script, driven through ``python -m pydense.cli`` in a subprocess."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

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


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _python(*args: str, cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, *args],
        cwd=cwd,
        env=_env(),
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
    )


def pydense_cli(
    *args: str, cwd: Path, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = _env()
    return subprocess.run(
        [PYTHON, "-m", "pydense.cli", *args],
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=120,
    )


# --- usage -----------------------------------------------------------------------------------------


def test_no_arguments_is_a_usage_error(tmp_path: Path) -> None:
    proc = pydense_cli(cwd=tmp_path)
    assert proc.returncode == 2
    assert "usage" in (proc.stderr + proc.stdout).lower()


def test_unknown_subcommand_is_a_usage_error(tmp_path: Path) -> None:
    proc = pydense_cli("frobnicate", cwd=tmp_path)
    assert proc.returncode == 2


def test_version_flag(tmp_path: Path) -> None:
    proc = pydense_cli("--version", cwd=tmp_path)
    assert proc.returncode == 0
    assert "1.0.0" in proc.stdout


def test_help_texts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "250")  # no argparse wrapping
    proc = pydense_cli("--help", cwd=tmp_path)
    assert proc.returncode == 0
    lines = {line.split()[0]: line for line in proc.stdout.splitlines() if line.strip()}
    assert "418-token cheat sheet" in lines["skill"]
    assert "400-token" not in proc.stdout
    for command in ("encode", "decode", "check", "run"):
        assert "FILE may be - for stdin" in lines[command], command
    assert ".vscode/mcp.json and .cursor/mcp.json" in lines["init-skill"]
    proc = pydense_cli("encode", "--help", cwd=tmp_path)
    assert "{full,nodoc,stripped}" in proc.stdout  # --mode choices derived from Mode


def test_pydense_mcp_help_is_a_plain_usage_line(tmp_path: Path) -> None:
    for args in (["-m", "pydense.mcp_server", "--help"], ["-m", "pydense.mcp_server", "-h"]):
        proc = _python(*args, cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        first = proc.stdout.splitlines()[0]
        assert first == "usage: pydense-mcp [-h] [--self-test] [--stdio-fallback]"
        assert "``" not in proc.stdout and "Console entry point" not in proc.stdout
    proc = pydense_cli("mcp", "--help", cwd=tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.startswith("usage: pydense mcp")


# --- encode / decode ---------------------------------------------------------------------------------


def test_encode_to_stdout_and_file(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(SAMPLE_PY, encoding="utf-8")
    proc = pydense_cli("encode", "a.py", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (
        proc.stdout.rstrip("\n")
        == 'class A{\n"""Doc."""\ndef __init__(a,b=1){\n.a=a\n.b=b}\ndef total(){\nreturn.a+.b}}'
    )

    proc = pydense_cli("encode", "a.py", "-o", "a.dpy", "--mode", "nodoc", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    assert (tmp_path / "a.dpy").read_text(encoding="utf-8") == SAMPLE_DPY


def test_encode_pretty_and_stripped(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("def f(x: int) -> int:\n    return x\n", encoding="utf-8")
    proc = pydense_cli("encode", "f.py", "--mode", "stripped", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.rstrip("\n") == "def f(x){\nreturn x}"
    (tmp_path / "g.py").write_text("def g(self):\n    return self.x\n", encoding="utf-8")
    proc = pydense_cli("encode", "g.py", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.rstrip("\n") == "def g(self){\nreturn.x}"  # SPEC 6.5: .x anywhere
    proc = pydense_cli("encode", "g.py", "--pretty", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.rstrip("\n") == "def g(self){\nreturn .x}"
    (tmp_path / "h.py").write_text(
        "class H:\n    def g(self):\n        return self.x\n", encoding="utf-8"
    )
    proc = pydense_cli("encode", "h.py", "--pretty", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "return .x}" in proc.stdout


def test_encode_from_stdin(tmp_path: Path) -> None:
    proc = pydense_cli("encode", "-", cwd=tmp_path, stdin="x = 1\nif x:\n    y = 2\n")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.rstrip("\n") == "x=1\nif x{\ny=2}"


def test_encode_rejects_bad_python(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")
    proc = pydense_cli("encode", "bad.py", cwd=tmp_path)
    assert proc.returncode == 1
    assert proc.stderr.strip()
    assert "did you mean" not in proc.stderr  # the hint is only for a .dpy given to encode


def test_encode_of_a_dpy_file_hints_decode(tmp_path: Path) -> None:
    (tmp_path / "a.dpy").write_text(SAMPLE_DPY, encoding="utf-8")
    proc = pydense_cli("encode", "a.dpy", cwd=tmp_path)
    assert proc.returncode == 1
    assert proc.stderr.startswith("error: ")
    assert "did you mean pydense decode?" in proc.stderr


def test_decode_of_a_py_file_hints_encode(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(SAMPLE_PY, encoding="utf-8")
    proc = pydense_cli("decode", "a.py", cwd=tmp_path)
    assert proc.returncode == 1
    assert "E000" in proc.stderr
    assert "did you mean pydense encode?" in proc.stderr
    (tmp_path / "bad.dpy").write_text("if x{", encoding="utf-8")
    proc = pydense_cli("decode", "bad.dpy", cwd=tmp_path)
    assert proc.returncode == 1 and "did you mean" not in proc.stderr


def test_decode_roundtrip(tmp_path: Path) -> None:
    (tmp_path / "a.dpy").write_text(SAMPLE_DPY, encoding="utf-8")
    proc = pydense_cli("decode", "a.dpy", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.endswith("\n")
    assert "def __init__(self, a, b=1):" in proc.stdout
    assert "return self.a + self.b" in proc.stdout

    proc = pydense_cli("decode", "a.dpy", "-o", "out.py", cwd=tmp_path)
    assert proc.returncode == 0
    compiled = compile((tmp_path / "out.py").read_text(encoding="utf-8"), "out.py", "exec")
    assert compiled is not None


def test_decode_from_stdin_reports_syntax_error(tmp_path: Path) -> None:
    proc = pydense_cli("decode", "-", cwd=tmp_path, stdin="if x{\ny=1")
    assert proc.returncode == 1
    assert "E001" in proc.stderr


# --- check -----------------------------------------------------------------------------------------


def test_check_clean_file(tmp_path: Path) -> None:
    (tmp_path / "ok.dpy").write_text(SAMPLE_DPY, encoding="utf-8")
    proc = pydense_cli("check", "ok.dpy", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ""


def test_check_reports_error_with_position_and_exit_1(tmp_path: Path) -> None:
    (tmp_path / "bad.dpy").write_text("def f(a){\nreturn a", encoding="utf-8")
    proc = pydense_cli("check", "bad.dpy", cwd=tmp_path)
    assert proc.returncode == 1
    first = proc.stdout.splitlines()[0]
    assert first.startswith("E001 ")
    assert ":" in first.split()[1]  # line:col


def test_check_and_run_read_stdin(tmp_path: Path) -> None:
    proc = pydense_cli("check", "-", cwd=tmp_path, stdin="if x{\ny=1")
    assert proc.returncode == 1
    assert proc.stdout.startswith("E001 ")
    proc = pydense_cli("run", "-", cwd=tmp_path, stdin="print(sum([1,2,3]))")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "6\n"


def test_check_warning_only_exits_0(tmp_path: Path) -> None:
    (tmp_path / "warn.dpy").write_text("x=1}", encoding="utf-8")  # E002: a real error
    proc = pydense_cli("check", "warn.dpy", cwd=tmp_path)
    assert proc.returncode == 1
    (tmp_path / "w.dpy").write_text("class A{\ndef f(this,x){\nreturn x}}", encoding="utf-8")
    proc = pydense_cli("check", "w.dpy", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("W002 ")


# --- run / -c --------------------------------------------------------------------------------------


def test_run_file(tmp_path: Path) -> None:
    (tmp_path / "prog.dpy").write_text(
        "import sys\ndef main(args){\nprint('args',args)}\nif __name__=='__main__'{\nmain(sys.argv[1:])}",
        encoding="utf-8",
    )
    proc = pydense_cli("run", "prog.dpy", "a", "b", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "args ['a', 'b']\n"


def test_run_file_error_is_compact(tmp_path: Path) -> None:
    (tmp_path / "boom.dpy").write_text("def f(){\nraise ValueError('bad')}\nf()", encoding="utf-8")
    proc = pydense_cli("run", "boom.dpy", cwd=tmp_path)
    assert proc.returncode == 1
    assert proc.stderr.strip() == "!Err[f:L2]: ValueError(bad)"


def test_run_file_exit_code_propagates(tmp_path: Path) -> None:
    (tmp_path / "exit.dpy").write_text("import sys\nsys.exit(7)", encoding="utf-8")
    proc = pydense_cli("run", "exit.dpy", cwd=tmp_path)
    assert proc.returncode == 7


def test_inline_command(tmp_path: Path) -> None:
    proc = pydense_cli("-c", "x=[i*2 for i in range(3)]\nprint(x[-1]?x:0)", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "[0, 2, 4]\n"


def test_inline_command_syntax_error(tmp_path: Path) -> None:
    proc = pydense_cli("-c", "if x{", cwd=tmp_path)
    assert proc.returncode == 1
    assert "E001" in proc.stderr


# --- skill / init-skill --------------------------------------------------------------------------------


def test_skill_prints_cheatsheet(tmp_path: Path) -> None:
    from pydense.skill import AGENT_WORKFLOW, CHEATSHEET

    proc = pydense_cli("skill", cwd=tmp_path)
    assert proc.returncode == 0
    assert proc.stdout == CHEATSHEET
    proc = pydense_cli("skill", "--workflow", cwd=tmp_path)
    assert proc.stdout == AGENT_WORKFLOW


def _expected_mcp_command() -> tuple[str, list[str]]:
    """What init-skill must write: the console script when on PATH, else this interpreter."""
    if shutil.which("pydense-mcp"):
        return "pydense-mcp", []
    return sys.executable, ["-m", "pydense.mcp_server"]


def test_init_skill_writes_all_files(tmp_path: Path) -> None:
    from pydense.skill import AGENT_WORKFLOW, CHEATSHEET

    target = tmp_path / "proj"
    proc = pydense_cli("init-skill", str(target), cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    skill = (target / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: pydense\n")
    assert CHEATSHEET in skill and AGENT_WORKFLOW in skill
    assert CHEATSHEET in (target / "CLAUDE.md").read_text(encoding="utf-8")
    assert CHEATSHEET in (target / ".cursorrules").read_text(encoding="utf-8")

    command, args = _expected_mcp_command()
    config = json.loads((target / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
    server = config["servers"]["pydense"]
    assert server["type"] == "stdio"
    assert (server["command"], server["args"]) == (command, args)
    assert server["env"] == {"PYTHONUNBUFFERED": "1"}
    cursor = json.loads((target / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    cursor_server = cursor["mcpServers"]["pydense"]
    assert (cursor_server["command"], cursor_server["args"]) == (command, args)

    assert "  - SKILL.md: created" in proc.stdout
    assert "  - .vscode/mcp.json: created" in proc.stdout
    assert "  - .cursor/mcp.json: created" in proc.stdout
    assert "claude mcp add pydense -- pydense-mcp" in proc.stdout.splitlines()[-1]
    hint = [line for line in proc.stdout.splitlines() if line.startswith("MCP server command: ")]
    assert len(hint) == 1
    if command == "pydense-mcp":
        assert hint[0].startswith("MCP server command: pydense-mcp (resolved to ")
    else:
        assert sys.executable in hint[0] and "not on PATH" in hint[0]


def test_init_skill_prefers_the_console_script_when_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / ("pydense-mcp.exe" if os.name == "nt" else "pydense-mcp")
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    target = tmp_path / "proj"
    proc = pydense_cli("init-skill", str(target), cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    for rel, key in ((".vscode", "servers"), (".cursor", "mcpServers")):
        config = json.loads((target / rel / "mcp.json").read_text(encoding="utf-8"))
        assert config[key]["pydense"]["command"] == "pydense-mcp"  # portable: no absolute path
        assert config[key]["pydense"]["args"] == []
    assert f"MCP server command: pydense-mcp (resolved to {script})" in proc.stdout
    assert proc.stdout.splitlines()[-1] == "Claude Code: claude mcp add pydense -- pydense-mcp"


def test_init_skill_falls_back_to_the_interpreter_without_the_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))  # pydense-mcp cannot be found
    target = tmp_path / "proj"
    proc = pydense_cli("init-skill", str(target), cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    config = json.loads((target / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
    assert config["servers"]["pydense"]["command"] == sys.executable
    assert config["servers"]["pydense"]["args"] == ["-m", "pydense.mcp_server"]
    hint = f"MCP server command: {sys.executable} -m pydense.mcp_server (pydense-mcp is not on PATH"
    assert hint in proc.stdout
    assert "claude mcp add pydense -- pydense-mcp" in proc.stdout


def test_init_skill_never_clobbers_an_edited_skill_md(tmp_path: Path) -> None:
    edited = "---\nname: pydense\n---\n\nMy own notes.\n"
    (tmp_path / "SKILL.md").write_text(edited, encoding="utf-8")
    proc = pydense_cli("init-skill", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "SKILL.md").read_text(encoding="utf-8") == edited
    assert "  - SKILL.md: kept (edited)" in proc.stdout
    # a SKILL.md that init-skill itself wrote is reported as unchanged on the next run
    (tmp_path / "SKILL.md").unlink()
    assert "  - SKILL.md: created" in pydense_cli("init-skill", cwd=tmp_path).stdout
    assert "  - SKILL.md: unchanged" in pydense_cli("init-skill", cwd=tmp_path).stdout


def test_init_skill_never_overwrites_claude_md(tmp_path: Path) -> None:
    from pydense.skill import CHEATSHEET

    (tmp_path / "CLAUDE.md").write_text("# My project\n\nKeep this.\n", encoding="utf-8")
    proc = pydense_cli("init-skill", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith("# My project\n\nKeep this.\n")
    assert text.count("<!-- pydense:begin -->") == 1
    assert CHEATSHEET in text
    # a second run replaces the marked section instead of appending twice
    proc = pydense_cli("init-skill", cwd=tmp_path)
    assert proc.returncode == 0
    again = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert again == text


def test_init_skill_merges_existing_mcp_json(tmp_path: Path) -> None:
    vscode = tmp_path / ".vscode"
    vscode.mkdir()
    (vscode / "mcp.json").write_text(
        json.dumps({"servers": {"other": {"command": "x"}}}), encoding="utf-8"
    )
    cursor = tmp_path / ".cursor"
    cursor.mkdir()
    (cursor / "mcp.json").write_text("{not json", encoding="utf-8")
    proc = pydense_cli("init-skill", ".", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    config = json.loads((vscode / "mcp.json").read_text(encoding="utf-8"))
    assert set(config["servers"]) == {"other", "pydense"}
    assert config["servers"]["other"] == {"command": "x"}
    assert "  - .vscode/mcp.json: updated" in proc.stdout
    cursor_config = json.loads((cursor / "mcp.json").read_text(encoding="utf-8"))
    assert set(cursor_config["mcpServers"]) == {"pydense"}
    assert "  - .cursor/mcp.json: replaced (was not valid JSON)" in proc.stdout


# --- mcp / bench -------------------------------------------------------------------------------------


def test_mcp_subcommand_self_test(tmp_path: Path) -> None:
    proc = pydense_cli("mcp", "--self-test", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "self-test: OK" in proc.stdout


def test_mcp_subcommand_stdio_fallback_answers_ping(tmp_path: Path) -> None:
    proc = pydense_cli(
        "mcp", "--stdio-fallback", cwd=tmp_path, stdin='{"jsonrpc":"2.0","id":1,"method":"ping"}\n'
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip()) == {"jsonrpc": "2.0", "id": 1, "result": {}}


@pytest.mark.skipif(
    not (REPO_ROOT / "benchmarks" / "token_compression.py").exists(), reason="no benchmarks/"
)
def test_bench_help_does_not_crash_without_tiktoken_message(tmp_path: Path) -> None:
    proc = pydense_cli("bench", "--help", cwd=tmp_path)
    assert proc.returncode in (0, 1)


def test_bench_hint_names_the_repository(tmp_path: Path) -> None:
    # Make `from benchmarks import token_compression` fail the way it does in an installed wheel.
    proc = _python(
        "-c",
        "import sys; sys.modules['benchmarks'] = None\n"
        "from pydense.cli import main; sys.exit(main(['bench']))",
        cwd=tmp_path,
    )
    assert proc.returncode == 1
    assert "git clone https://github.com/iced-compiler/pydense" in proc.stderr
    assert "pip install -e '.[bench]'" in proc.stderr
