#!/usr/bin/env python3
"""
Corpus fidelity & compression harness.

Round-trips every top-level statement of a corpus of real Python files through a
PyDense backend (Python -> .dpy -> Python) and reports:

  * fidelity: % of statements whose round-tripped AST equals the original AST
  * failure buckets with concrete examples (decompile error / compile error / mismatch)
  * token compression (tiktoken o200k_base + cl100k_base when available)
  * throughput (statements/sec, ms per KB)

Usage:
    python benchmarks/corpus_fidelity.py                      # stdlib corpus, new backend
    python benchmarks/corpus_fidelity.py --backend legacy     # the v0.2 pydense.py transpiler
    python benchmarks/corpus_fidelity.py --files a.py b.py    # explicit files
    python benchmarks/corpus_fidelity.py --json out.json      # machine-readable report
    python benchmarks/corpus_fidelity.py --mode stripped      # full | nodoc | stripped (SPEC s.11)
    python benchmarks/corpus_fidelity.py --fail-under 100     # exit 1 below the threshold (CI gate)

The reference AST is adjusted per mode exactly as SPEC section 11 describes: FULL compares against
``ast.parse(src)`` unchanged; NODOC drops the docstring Expr of every Module/ClassDef/FunctionDef on
both sides; STRIPPED also drops parameter/return annotations and turns ``x: T = v`` into ``x = v``.
The legacy v0.2 backend has no docstring mode: it is always compared docstring-stripped, and
``--mode stripped`` maps to its ``preserve_types=False`` flag.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import sysconfig
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------------------- backends

MODES = ("full", "nodoc", "stripped")


@dataclass
class Backend:
    name: str
    to_pyd: Callable[[str, str], str]  # (python_source, mode) -> dpy text
    to_py_ast: Callable[[str], ast.Module]  # dpy text -> ast.Module
    strip_docstrings_always: bool = False  # legacy backend cannot keep docstrings


def load_backend(name: str) -> Backend:
    if name == "legacy":
        import importlib.util

        legacy_path = ROOT / "legacy" / "pydense_v02.py"
        if not legacy_path.exists():
            legacy_path = ROOT / "pydense.py"  # pre-refactor layout
        spec = importlib.util.spec_from_file_location("pydense_legacy", legacy_path)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        sys.modules[spec.name] = mod  # dataclasses needs the module registered
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        def to_pyd(src: str, mode: str) -> str:
            preserve_types = mode != "stripped"
            return mod.PyDenseDecompiler(
                use_positional_args=True, preserve_types=preserve_types
            ).decompile(src)

        def to_py_ast(pyd: str) -> ast.Module:
            return mod.PyDenseCompiler().compile_to_ast(pyd)

        return Backend("legacy-v0.2", to_pyd, to_py_ast, strip_docstrings_always=True)

    try:
        import pydense  # the package
    except ImportError as exc:  # pragma: no cover - depends on checkout state
        sys.exit(
            f"corpus_fidelity: cannot import the pydense package ({exc}); "
            "run `pip install -e .` first"
        )

    def to_pyd(src: str, mode: str) -> str:
        return pydense.encode(src, mode=mode)

    def to_py_ast(pyd: str) -> ast.Module:
        return pydense.parse(pyd)

    return Backend(f"pydense-{getattr(pydense, '__version__', '?')}", to_pyd, to_py_ast)


# --------------------------------------------------------------------------- corpus

DEFAULT_STDLIB_FILES = [
    "textwrap.py",
    "dataclasses.py",
    "functools.py",
    "json/encoder.py",
    "json/decoder.py",
    "argparse.py",
    "collections/__init__.py",
    "heapq.py",
    "bisect.py",
    "shlex.py",
    "statistics.py",
    "fractions.py",
    "string.py",
    "difflib.py",
    "pprint.py",
    "contextlib.py",
    "abc.py",
    "enum.py",
    "typing.py",
    "pathlib/__init__.py",
    "pathlib/_local.py",
    "asyncio/queues.py",
    "asyncio/locks.py",
    "asyncio/tasks.py",
    "csv.py",
    "configparser.py",
    "logging/__init__.py",
    "copy.py",
    "operator.py",
    "glob.py",
    "fnmatch.py",
    "tomllib/_parser.py",
    "http/cookies.py",
    "email/utils.py",
    "urllib/parse.py",
    "random.py",
    "inspect.py",
    "ast.py",
    "re/_parser.py",
    "re/_compiler.py",
    "zipfile/__init__.py",
    "tarfile.py",
    "queue.py",
    "threading.py",
    "selectors.py",
    "socketserver.py",
    "subprocess.py",
    "shutil.py",
    "tempfile.py",
    "uuid.py",
    "base64.py",
    "hmac.py",
    "numbers.py",
    "calendar.py",
    "_pydatetime.py",
    "_pydecimal.py",
    "ipaddress.py",
    "graphlib.py",
    "gettext.py",
    "optparse.py",
    "traceback.py",
    "linecache.py",
    "tokenize.py",
    "dis.py",
    "pickle.py",
    "codecs.py",
    "_pyio.py",
    "types.py",
    "weakref.py",
    "reprlib.py",
    "warnings.py",
    "platform.py",
    "runpy.py",
    "pkgutil.py",
    "importlib/util.py",
    "timeit.py",
    "pstats.py",
    "doctest.py",
    "unittest/case.py",
    "unittest/mock.py",
    "unittest/loader.py",
    "html/parser.py",
    "xml/etree/ElementTree.py",
    "xml/dom/minidom.py",
    "smtplib.py",
    "ftplib.py",
    "imaplib.py",
    "socket.py",
    "ssl.py",
    "mimetypes.py",
    "wsgiref/simple_server.py",
    "wsgiref/handlers.py",
    "http/server.py",
    "http/client.py",
    "urllib/request.py",
    "xmlrpc/client.py",
    "xmlrpc/server.py",
    "concurrent/futures/_base.py",
    "concurrent/futures/thread.py",
    "concurrent/futures/process.py",
    "multiprocessing/pool.py",
    "asyncio/base_events.py",
    "asyncio/events.py",
    "asyncio/futures.py",
    "asyncio/streams.py",
    "asyncio/subprocess.py",
    "asyncio/runners.py",
    "asyncio/taskgroups.py",
    "asyncio/timeouts.py",
]


def default_corpus() -> list[Path]:
    stdlib = Path(sysconfig.get_paths()["stdlib"])
    return [stdlib / f for f in DEFAULT_STDLIB_FILES if (stdlib / f).exists()]


# --------------------------------------------------------------------------- normalisation


class _Normalizer(ast.NodeTransformer):
    """Removes information PyDense is allowed to drop so that AST comparison is fair."""

    def __init__(self, strip_types: bool, strip_docstrings: bool) -> None:
        self.strip_types = strip_types
        self.strip_docstrings = strip_docstrings

    def _strip_body_docstring(self, body: list[ast.stmt]) -> list[ast.stmt]:
        if (
            self.strip_docstrings
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:] or [ast.Pass()]
        return body

    def visit_Module(self, node: ast.Module) -> ast.AST:
        node.type_ignores = []
        node.body = self._strip_body_docstring(node.body)
        self.generic_visit(node)
        return node

    def _visit_def(self, node):
        node.body = self._strip_body_docstring(node.body)
        if self.strip_types:
            node.returns = None
        node.type_comment = None
        self.generic_visit(node)
        return node

    visit_FunctionDef = _visit_def
    visit_AsyncFunctionDef = _visit_def

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        node.body = self._strip_body_docstring(node.body)
        self.generic_visit(node)
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        if self.strip_types:
            node.annotation = None
        node.type_comment = None
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST | None:
        if self.strip_types:
            if node.value is None:
                return None
            return ast.Assign(
                targets=[node.target], value=self.visit(node.value), type_comment=None
            )
        self.generic_visit(node)
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        node.type_comment = None
        self.generic_visit(node)
        return node

    def visit_For(self, node: ast.For) -> ast.AST:
        node.type_comment = None
        self.generic_visit(node)
        return node

    visit_AsyncFor = visit_For

    def visit_With(self, node: ast.With) -> ast.AST:
        node.type_comment = None
        self.generic_visit(node)
        return node

    visit_AsyncWith = visit_With

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        node.kind = None  # u'' prefix
        return node


def normalized_dump(tree: ast.Module, strip_types: bool, strip_docstrings: bool = True) -> str:
    tree = _Normalizer(strip_types, strip_docstrings).visit(tree)
    ast.fix_missing_locations(tree)
    return ast.dump(tree, include_attributes=False)


# --------------------------------------------------------------------------- tokenizers


def token_counters() -> dict[str, Callable[[str], int]]:
    try:
        import tiktoken
    except ImportError:
        return {}
    encs = {}
    for name in ("o200k_base", "cl100k_base"):
        try:
            enc = tiktoken.get_encoding(name)
            encs[name] = (lambda e: lambda s: len(e.encode(s, disallowed_special=())))(enc)
        except Exception:
            pass
    return encs


# --------------------------------------------------------------------------- report


@dataclass
class Report:
    backend: str
    files: int = 0
    statements: int = 0
    ok: int = 0
    decompile_errors: int = 0
    compile_errors: int = 0
    mismatches: int = 0
    py_bytes: int = 0
    pyd_bytes: int = 0
    tokens: dict[str, dict[str, int]] = field(default_factory=dict)
    decompile_seconds: float = 0.0
    compile_seconds: float = 0.0
    examples: dict[str, list[dict]] = field(
        default_factory=lambda: {"decompile": [], "compile": [], "mismatch": []}
    )

    @property
    def fidelity(self) -> float:
        return 100.0 * self.ok / self.statements if self.statements else 0.0

    def summary(self) -> str:
        lines = [
            f"Backend: {self.backend}",
            f"Files: {self.files}   Statements: {self.statements}",
            f"Fidelity: {self.fidelity:.2f}%   ok={self.ok} decompile_err={self.decompile_errors} "
            f"compile_err={self.compile_errors} mismatch={self.mismatches}",
            f"Bytes: {self.py_bytes} -> {self.pyd_bytes} "
            f"({(1 - self.pyd_bytes / max(self.py_bytes, 1)) * 100:.1f}% smaller)",
        ]
        for enc, d in self.tokens.items():
            red = (1 - d["pyd"] / max(d["py"], 1)) * 100
            lines.append(
                f"Tokens[{enc}]: {d['py']} -> {d['pyd']} ({red:.1f}% reduction vs ast.unparse "
                "with docstrings; see token_compression.py for per-mode baselines)"
            )
        kb = self.py_bytes / 1024 or 1
        lines.append(
            f"Speed: decompile {self.decompile_seconds * 1000 / kb:.2f} ms/KB, "
            f"compile {self.compile_seconds * 1000 / kb:.2f} ms/KB"
        )
        return "\n".join(lines)


def run(
    backend: Backend,
    files: Iterable[Path],
    mode: str,
    max_examples: int = 25,
    verbose: bool = False,
) -> Report:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    strip_types = mode == "stripped"
    strip_docstrings = mode != "full" or backend.strip_docstrings_always
    rep = Report(backend=f"{backend.name} [{mode}]")
    counters = token_counters()
    for enc in counters:
        rep.tokens[enc] = {"py": 0, "pyd": 0}

    for path in files:
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        rep.files += 1
        for stmt in tree.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue  # module docstring
            rep.statements += 1
            py = ast.unparse(ast.Module(body=[stmt], type_ignores=[]))

            t0 = time.perf_counter()
            try:
                pyd = backend.to_pyd(py, mode)
            except Exception as exc:  # noqa: BLE001
                rep.decompile_errors += 1
                if len(rep.examples["decompile"]) < max_examples:
                    rep.examples["decompile"].append(
                        {
                            "file": str(path),
                            "error": f"{type(exc).__name__}: {exc}"[:300],
                            "py": py[:600],
                        }
                    )
                continue
            rep.decompile_seconds += time.perf_counter() - t0

            t0 = time.perf_counter()
            try:
                back = backend.to_py_ast(pyd)
            except Exception as exc:  # noqa: BLE001
                rep.compile_errors += 1
                if len(rep.examples["compile"]) < max_examples:
                    rep.examples["compile"].append(
                        {
                            "file": str(path),
                            "error": f"{type(exc).__name__}: {exc}"[:300],
                            "py": py[:600],
                            "pyd": pyd[:600],
                        }
                    )
                continue
            rep.compile_seconds += time.perf_counter() - t0

            a = normalized_dump(ast.parse(py), strip_types, strip_docstrings)
            try:
                b = normalized_dump(back, strip_types, strip_docstrings)
            except Exception as exc:  # noqa: BLE001
                b = f"<unnormalizable: {exc}>"
            if a == b:
                rep.ok += 1
            else:
                rep.mismatches += 1
                if len(rep.examples["mismatch"]) < max_examples:
                    try:
                        back_src = ast.unparse(back)
                    except Exception:  # noqa: BLE001
                        back_src = "<unparse failed>"
                    rep.examples["mismatch"].append(
                        {
                            "file": str(path),
                            "py": py[:600],
                            "pyd": pyd[:600],
                            "back": back_src[:600],
                        }
                    )

            rep.py_bytes += len(py.encode())
            rep.pyd_bytes += len(pyd.encode())
            for enc, count in counters.items():
                rep.tokens[enc]["py"] += count(py)
                rep.tokens[enc]["pyd"] += count(pyd)
        if verbose:
            print(f"  {path.name}: {rep.fidelity:.1f}% so far", file=sys.stderr)
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--backend", default="pydense", choices=["pydense", "legacy"])
    ap.add_argument("--files", nargs="*", type=Path, help="explicit files (default: stdlib corpus)")
    ap.add_argument("--file-list", type=Path, help="text file with one path per line")
    ap.add_argument(
        "--mode", default="full", choices=MODES, help="pydense.encode mode (default: full)"
    )
    ap.add_argument(
        "--fail-under", type=float, metavar="PCT", help="exit 1 if fidelity is below PCT"
    )
    ap.add_argument("--json", type=Path, help="write full JSON report here")
    ap.add_argument("--examples", type=int, default=8, help="how many failure examples to print")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    files: list[Path]
    if args.files:
        files = args.files
    elif args.file_list:
        files = [
            Path(line.strip()) for line in args.file_list.read_text().splitlines() if line.strip()
        ]
    else:
        files = default_corpus()

    backend = load_backend(args.backend)
    rep = run(backend, files, args.mode, verbose=args.verbose)
    print(rep.summary())
    for bucket, items in rep.examples.items():
        if not items:
            continue
        print(f"\n--- {bucket} examples ({len(items)} shown) ---")
        for ex in items[: args.examples]:
            print(f"[{os.path.basename(ex['file'])}]")
            if "error" in ex:
                print("  ERR :", ex["error"])
            print("  PY  :", ex["py"].replace("\n", "\n        ")[:400])
            if "pyd" in ex:
                print("  PYD :", ex["pyd"][:400])
            if "back" in ex:
                print("  BACK:", ex["back"].replace("\n", "\n        ")[:400])
    if args.json:
        args.json.write_text(
            json.dumps(rep.__dict__ | {"fidelity": rep.fidelity}, indent=1, default=str)
        )
        print(f"\nJSON report written to {args.json}")
    if args.fail_under is not None and rep.fidelity < args.fail_under:
        print(f"\nFAIL: fidelity {rep.fidelity:.2f}% < {args.fail_under}%", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
