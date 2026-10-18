#!/usr/bin/env python3
"""
PyDense CLI (`pydense`)
Command-line interface for running, compiling, decompiling, and initializing AI agent skills.
"""

from __future__ import annotations
import argparse
import ast
import json
import sys
from pathlib import Path

from pydense import PyDenseCompiler, PyDenseDecompiler, PyDenseRunner, run_verification_suite
from mcp_server import SKILL_CHEATSHEET

AGENT_WORKFLOW_PROMPT = f"""{SKILL_CHEATSHEET}
## Agent Workflow Directives
1. **Reading Code**: Prefer `read_file_as_pydense` over standard file reads on large `.py` modules to save ~50% input context tokens.
2. **Executing & Testing**: Use `execute_pydense` with compact `.pyd` syntax for rapid REPL verification.
3. **Writing Modules**: Use `write_pydense_module(file_path, pyd_code, output_format="py")` to emit token-efficient `.pyd` in tool calls while automatically saving clean PEP-8 `.py` to disk.
"""


def cmd_init_skill(target_dir: Path) -> None:
    """Writes SKILL.md, .cursorrules, CLAUDE.md, and .vscode/mcp.json into target_dir."""
    target_dir = target_dir.resolve()
    mcp_script = str((Path(__file__).resolve().parent / "mcp_server.py"))

    # 1. SKILL.md
    skill_path = target_dir / "SKILL.md"
    skill_path.write_text(AGENT_WORKFLOW_PROMPT, encoding="utf-8")

    # 2. .cursorrules (append or create)
    cursor_path = target_dir / ".cursorrules"
    cursor_path.write_text(AGENT_WORKFLOW_PROMPT, encoding="utf-8")

    # 3. CLAUDE.md (append or create)
    claude_path = target_dir / "CLAUDE.md"
    if not claude_path.exists():
        claude_path.write_text(AGENT_WORKFLOW_PROMPT, encoding="utf-8")

    # 4. .vscode/mcp.json
    vscode_dir = target_dir / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    mcp_json_path = vscode_dir / "mcp.json"
    mcp_config = {
        "mcpServers": {
            "pydense": {
                "command": sys.executable,
                "args": [mcp_script],
                "env": {"PYTHONUNBUFFERED": "1"},
            }
        }
    }
    mcp_json_path.write_text(json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8")

    print(f"Initialized PyDense Agent Skill in {target_dir}:")
    print(f"  - {skill_path.name}")
    print(f"  - {cursor_path.name}")
    print(f"  - {claude_path.name}")
    print(f"  - .vscode/{mcp_json_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pydense",
        description="PyDense (.pyd) Compiler, Decompiler & Agent Skill CLI",
    )
    parser.add_argument("-c", "--command", type=str, help="Execute inline PyDense (.pyd) code string")
    subparsers = parser.add_subparsers(dest="subcmd")

    # pydense run <file.pyd>
    p_run = subparsers.add_parser("run", help="Compile and execute a .pyd file directly")
    p_run.add_argument("file", type=Path, help="Path to .pyd file")

    # pydense compile <file.pyd> [-o file.py]
    p_comp = subparsers.add_parser("compile", help="Transpile .pyd file to standard Python (.py)")
    p_comp.add_argument("file", type=Path, help="Path to input .pyd file")
    p_comp.add_argument("-o", "--output", type=Path, help="Optional output .py file path")

    # pydense decompile <file.py> [-o file.pyd] [--strip-types]
    p_decomp = subparsers.add_parser("decompile", help="Compress standard Python (.py) into PyDense (.pyd)")
    p_decomp.add_argument("file", type=Path, help="Path to input .py file")
    p_decomp.add_argument("-o", "--output", type=Path, help="Optional output .pyd file path")
    p_decomp.add_argument("--strip-types", action="store_true", help="Omit type annotations for maximum compression")
    p_decomp.add_argument("--no-pos-args", action="store_true", help="Keep original parameter names instead of $0, $1")

    # pydense init-skill [dir]
    p_init = subparsers.add_parser("init-skill", help="Generate SKILL.md, .cursorrules, CLAUDE.md, and .vscode/mcp.json")
    p_init.add_argument("dir", nargs="?", type=Path, default=Path("."), help="Target workspace directory")

    # pydense test
    subparsers.add_parser("test", help="Run built-in compiler/decompiler self-test suite")

    args = parser.parse_args()

    if args.command:
        runner = PyDenseRunner()
        try:
            runner.execute(args.command)
        except RuntimeError as err:
            print(err, file=sys.stderr)
            sys.exit(1)
        return

    if args.subcmd == "run":
        code = args.file.read_text(encoding="utf-8")
        try:
            PyDenseRunner().execute(code)
        except RuntimeError as err:
            print(err, file=sys.stderr)
            sys.exit(1)

    elif args.subcmd == "compile":
        code = args.file.read_text(encoding="utf-8")
        tree = PyDenseCompiler().compile_to_ast(code, filename=str(args.file))
        py_out = ast.unparse(tree) + "\n"
        if args.output:
            args.output.write_text(py_out, encoding="utf-8")
        else:
            sys.stdout.write(py_out)

    elif args.subcmd == "decompile":
        code = args.file.read_text(encoding="utf-8")
        decompiler = PyDenseDecompiler(
            use_positional_args=not args.no_pos_args,
            preserve_types=not args.strip_types,
        )
        pyd_out = decompiler.decompile(code) + "\n"
        if args.output:
            args.output.write_text(pyd_out, encoding="utf-8")
        else:
            sys.stdout.write(pyd_out)

    elif args.subcmd == "init-skill":
        cmd_init_skill(args.dir)

    elif args.subcmd == "test":
        run_verification_suite()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()