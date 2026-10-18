"""``pydense`` console script.

Exit codes: 0 success, 1 diagnostics or a failed run, 2 usage error.
"""

from __future__ import annotations

import argparse
import inspect
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from ._version import __version__
from .skill import AGENT_WORKFLOW, CHEATSHEET

__all__ = ["main"]

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

_MARK_BEGIN = "<!-- pydense:begin -->"
_MARK_END = "<!-- pydense:end -->"

_SKILL_FRONTMATTER = """---
name: pydense
description: Read and write PyDense (.dpy), lossless brace-blocked Python, via the MCP tools.
---

"""


def _read_source(path: str) -> str:
    try:
        if path == "-":
            return sys.stdin.read()
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise OSError(f"{path}: not valid UTF-8 ({exc.reason} at byte {exc.start})") from exc


def _display_name(path: str, fallback: str) -> str:
    return fallback if path == "-" else path


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return EXIT_ERROR


def _direction_hint(path: str, command: str) -> str:
    """A hint for ``pydense encode x.dpy`` / ``pydense decode x.py``, appended to the error."""
    suffix = Path(path).suffix
    if command == "encode" and suffix == ".dpy":
        return f"\nhint: {path} is already PyDense; did you mean pydense decode?"
    if command == "decode" and suffix == ".py":
        return f"\nhint: {path} is Python; did you mean pydense encode?"
    return ""


# ---------------------------------------------------------------------------
# sub-commands
# ---------------------------------------------------------------------------


def cmd_encode(args: argparse.Namespace) -> int:
    import pydense

    try:
        source = _read_source(args.file)
        text = pydense.encode(
            source,
            mode=args.mode,
            pretty=args.pretty,
            filename=_display_name(args.file, "<stdin>"),
        )
    except (OSError, SyntaxError) as exc:
        return _fail(f"error: {exc}" + _direction_hint(args.file, "encode"))
    if args.output:
        try:
            Path(args.output).write_text(text, encoding="utf-8")
        except OSError as exc:
            return _fail(f"error: cannot write {args.output}: {exc}")
    else:
        print(text)
    return EXIT_OK


def cmd_decode(args: argparse.Namespace) -> int:
    import pydense

    try:
        text = _read_source(args.file)
        source = pydense.decode(text, filename=_display_name(args.file, "<dpy>"))
    except (OSError, SyntaxError) as exc:
        return _fail(f"error: {exc}" + _direction_hint(args.file, "decode"))
    if args.output:
        try:
            Path(args.output).write_text(source, encoding="utf-8")
        except OSError as exc:
            return _fail(f"error: cannot write {args.output}: {exc}")
    else:
        sys.stdout.write(source)
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    import pydense

    try:
        text = _read_source(args.file)
    except OSError as exc:
        return _fail(f"error: {exc}")
    diagnostics = pydense.check(text, filename=_display_name(args.file, "<dpy>"))
    for diagnostic in diagnostics:
        print(diagnostic)
    has_error = any(d.severity == "error" for d in diagnostics)
    return EXIT_ERROR if has_error else EXIT_OK


def _execute(text: str, filename: str, env: dict | None = None) -> int:
    from .runtime import PyDenseRuntimeError, run

    try:
        run(text, env, filename=filename)
    except PyDenseRuntimeError as exc:
        return _fail(str(exc))
    except SyntaxError as exc:
        return _fail(f"error: {exc}")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    try:
        text = _read_source(args.file)
    except OSError as exc:
        return _fail(f"error: {exc}")
    filename = _display_name(args.file, "<stdin>")
    env = {"__name__": "__main__", "__file__": filename}
    sys.argv = [args.file, *args.args]
    return _execute(text, filename, env)


def cmd_inline(code: str) -> int:
    return _execute(code, "<dpy>")


def cmd_skill(args: argparse.Namespace) -> int:
    print(AGENT_WORKFLOW if args.workflow else CHEATSHEET, end="")
    return EXIT_OK


def _upsert_marked_section(path: Path, body: str) -> str:
    """Create ``path`` with ``body`` or append/replace its pydense-marked section; no overwrite."""
    section = f"{_MARK_BEGIN}\n{body.rstrip()}\n{_MARK_END}\n"
    if not path.exists():
        path.write_text(section, encoding="utf-8")
        return "created"
    existing = path.read_text(encoding="utf-8")
    begin, end = existing.find(_MARK_BEGIN), existing.find(_MARK_END)
    if begin != -1 and end != -1 and end > begin:
        updated = existing[:begin] + section + existing[end + len(_MARK_END) :].lstrip("\n")
        path.write_text(updated, encoding="utf-8")
        return "updated section"
    separator = "" if existing.endswith("\n") or not existing else "\n"
    path.write_text(existing + separator + "\n" + section, encoding="utf-8")
    return "appended section"


def _mcp_command() -> tuple[str, list[str], str]:
    """``(command, args, resolved)`` for launching the MCP server.

    The portable console script ``pydense-mcp`` when it is on ``PATH``; otherwise the running
    interpreter with ``-m pydense.mcp_server``. ``resolved`` is the absolute path for the hint.
    """
    found = shutil.which("pydense-mcp")
    if found:
        return "pydense-mcp", [], found
    return sys.executable, ["-m", "pydense.mcp_server"], sys.executable


def _mcp_server_entry(stdio_type: bool) -> dict:
    command, args, _ = _mcp_command()
    entry: dict = {"type": "stdio"} if stdio_type else {}
    entry.update({"command": command, "args": args, "env": {"PYTHONUNBUFFERED": "1"}})
    return entry


def _write_mcp_json(mcp_json: Path, root_key: str, stdio_type: bool) -> str:
    """Merge the ``pydense`` server into ``mcp_json`` (``servers`` for VS Code, ``mcpServers`` for
    Cursor); other servers in the file are kept."""
    mcp_json.parent.mkdir(parents=True, exist_ok=True)
    config: dict = {}
    status = "created"
    if mcp_json.exists():
        try:
            loaded = json.loads(mcp_json.read_text(encoding="utf-8"))
            config = loaded if isinstance(loaded, dict) else {}
            status = "updated"
        except ValueError:
            status = "replaced (was not valid JSON)"
    servers = config.setdefault(root_key, {})
    if not isinstance(servers, dict):
        servers = config[root_key] = {}
    servers["pydense"] = _mcp_server_entry(stdio_type)
    mcp_json.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return status


def _write_skill_md(path: Path) -> str:
    """Write SKILL.md unless one with different content exists (it is the user's, keep it)."""
    content = _SKILL_FRONTMATTER + AGENT_WORKFLOW
    if path.exists():
        if path.read_text(encoding="utf-8") == content:
            return "unchanged"
        return "kept (edited); delete it to regenerate"
    path.write_text(content, encoding="utf-8")
    return "created"


def cmd_init_skill(args: argparse.Namespace) -> int:
    target = Path(args.dir).expanduser().resolve()
    try:
        target.mkdir(parents=True, exist_ok=True)
        results = [
            ("SKILL.md", _write_skill_md(target / "SKILL.md")),
            ("CLAUDE.md", _upsert_marked_section(target / "CLAUDE.md", AGENT_WORKFLOW)),
            (".cursorrules", _upsert_marked_section(target / ".cursorrules", AGENT_WORKFLOW)),
            (".vscode/mcp.json", _write_mcp_json(target / ".vscode" / "mcp.json", "servers", True)),
            (
                ".cursor/mcp.json",
                _write_mcp_json(target / ".cursor" / "mcp.json", "mcpServers", False),
            ),
        ]
    except OSError as exc:
        return _fail(f"error: {exc}")
    print(f"Initialized the PyDense agent skill in {target}:")
    for name, status in results:
        print(f"  - {name}: {status}")
    command, cmd_args, resolved = _mcp_command()
    if command == "pydense-mcp":
        print(f"MCP server command: pydense-mcp (resolved to {resolved})")
    else:
        print(
            f"MCP server command: {' '.join([command, *cmd_args])} "
            "(pydense-mcp is not on PATH; the interpreter above is the one running pydense)"
        )
    print("Claude Code: claude mcp add pydense -- pydense-mcp")
    return EXIT_OK


def cmd_bench(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    if (repo_root / "benchmarks").is_dir() and str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from benchmarks import token_compression
    except ImportError as exc:
        print(
            "pydense bench needs the benchmarks/ directory of a source checkout and the "
            "'bench' extra:\n"
            "  git clone https://github.com/iced-compiler/pydense && cd pydense\n"
            "  pip install -e '.[bench]'   # tiktoken (+ python-minifier for the baseline)\n"
            f"({exc})",
            file=sys.stderr,
        )
        return EXIT_ERROR
    entry = getattr(token_compression, "main", None) or getattr(
        token_compression, "run_benchmarks", None
    )
    if entry is None:
        return _fail("error: benchmarks.token_compression has no main() or run_benchmarks()")
    # main(argv) gets the pass-through arguments; a zero-argument entry point is called bare.
    takes_argv = bool(inspect.signature(entry).parameters)
    result = entry(list(args.extra_args)) if takes_argv else entry()
    return int(result or 0)


def cmd_mcp(args: argparse.Namespace) -> int:
    from . import mcp_server

    return int(mcp_server.main(list(args.extra_args)) or 0)


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    from .emitter import Mode

    parser = argparse.ArgumentParser(
        prog="pydense",
        description="PyDense (.dpy): whitespace-free, brace-blocked Python with the same AST.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"pydense {__version__}")
    parser.add_argument("-c", "--command", metavar="CODE", help="execute inline .dpy code and exit")
    sub = parser.add_subparsers(dest="subcommand", metavar="COMMAND")

    p = sub.add_parser("encode", help="Python -> .dpy (FILE may be - for stdin)")
    p.add_argument("file", metavar="FILE.py")
    p.add_argument("-o", "--output", metavar="OUT.dpy")
    p.add_argument("--mode", choices=[m.value for m in Mode], default=Mode.FULL.value)
    p.add_argument("--pretty", action="store_true", help="space between a keyword and . or a quote")
    p.set_defaults(func=cmd_encode)

    p = sub.add_parser("decode", help=".dpy -> Python (FILE may be - for stdin)")
    p.add_argument("file", metavar="FILE.dpy")
    p.add_argument("-o", "--output", metavar="OUT.py")
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser(
        "check",
        help="print diagnostics for a .dpy file (FILE may be - for stdin); exit 1 on a syntax "
        "error",
    )
    p.add_argument("file", metavar="FILE.dpy")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("run", help="execute a .dpy file (FILE may be - for stdin)")
    p.add_argument("file", metavar="FILE.dpy")
    p.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed on sys.argv")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("skill", help="print the 418-token cheat sheet")
    p.add_argument("--workflow", action="store_true", help="also print the MCP agent workflow")
    p.set_defaults(func=cmd_skill)

    p = sub.add_parser(
        "init-skill",
        help="write SKILL.md, CLAUDE.md, .cursorrules, .vscode/mcp.json and .cursor/mcp.json "
        "into DIR",
    )
    p.add_argument("dir", nargs="?", default=".", metavar="DIR")
    p.set_defaults(func=cmd_init_skill)

    p = sub.add_parser(
        "bench",
        help="token benchmark (delegates to benchmarks/token_compression.py)",
        usage="pydense bench [--corpus stdlib|FILE...] (options are passed through)",
    )
    p.set_defaults(func=cmd_bench, passthrough=True)

    p = sub.add_parser(
        "mcp",
        help="start the MCP server (same as pydense-mcp)",
        usage="pydense mcp [--stdio-fallback] [--self-test] (options are passed through)",
    )
    p.set_defaults(func=cmd_mcp, passthrough=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    # bench/mcp forward every extra option to their delegate; argparse.REMAINDER cannot do that
    # when the first extra token starts with "--", hence parse_known_args.
    args, extras = parser.parse_known_args(argv)
    if getattr(args, "passthrough", False):
        args.extra_args = extras
    elif extras:
        parser.error(f"unrecognized arguments: {' '.join(extras)}")
    if args.command is not None:
        return cmd_inline(args.command)
    if args.subcommand is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
