#!/usr/bin/env python3
"""
PyDense token-compression and parse-latency benchmark.

Reproduces docs/SPEC.md section 12.1 (the 7-sample headline table) and, with ``--corpus stdlib``,
the stdlib row of section 12.5. Every count is an exact tiktoken count (o200k_base, cl100k_base).

Columns, and the baseline each percentage is measured against (SPEC section 12, "honest numbers"):

  * py_doc    - ``ast.unparse(ast.parse(src))`` with docstrings.        Baseline for FULL.
  * py_nodoc  - the same with docstrings removed.                    Baseline for NODOC, STRIPPED.
  * minifier  - python-minifier whitespace-only (lossless, one-way), if importable.  vs py_doc.
  * FULL      - PyDense, exact AST bijection (annotations + docstrings kept).         vs py_doc.
  * NODOC     - PyDense, docstrings dropped.                                          vs py_nodoc.
  * STRIPPED  - PyDense, docstrings and annotations dropped (lossy).                  vs py_nodoc
                (and vs py_doc, labelled lossy, in the totals).

The 5 ``BENCHMARK_WORKLOADS`` strings are the README workloads and are referenced by the tests (two
of their lines exceed 100 columns, hence the E501 per-file ignore in pyproject.toml). Samples 6, 7
are ``textwrap.TextWrapper._wrap_chunks`` and ``json.encoder.py_encode_basestring_ascii`` +
``json.encoder.JSONEncoder.default``, extracted from the running interpreter's stdlib with ``ast``
as module-level functions (so sample 6 has no implicit receiver, exactly as in SPEC section 12.1).

Usage:
    python benchmarks/token_compression.py                 # 7 samples, Markdown tables
    python benchmarks/token_compression.py --json out.json # machine-readable report as well
    python benchmarks/token_compression.py --corpus stdlib # the corpus_fidelity.py stdlib corpus
    python benchmarks/token_compression.py --dump DIR      # also write sN.{full,nodoc,stripped}.dpy
    python benchmarks/token_compression.py --files a.py b.py

pydense and tiktoken are imported lazily so ``BENCHMARK_WORKLOADS`` imports without them.
"""

from __future__ import annotations

import argparse
import ast
import copy
import importlib.util
import json
import json.encoder
import os
import sys
import sysconfig
import textwrap
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODES = ("full", "nodoc", "stripped")

# ============================================================================
# 1. WORKLOADS (the 5 strings below are referenced by tests; keep them verbatim)
# ============================================================================

BENCHMARK_WORKLOADS: dict[str, str] = {
    "1. Streaming statistics tracker": '''
import math

class RunningStats:
    """Tracks an exponential moving average and variance over a stream of readings."""
    def __init__(self, span: int = 20, min_samples: int = 5):
        self.alpha: float = 2.0 / (span + 1.0)
        self.min_samples: int = min_samples
        self.mean: float = 0.0
        self.var: float = 0.0
        self.count: int = 0

    def update(self, value: float) -> tuple[float, float]:
        self.count += 1
        if self.count == 1:
            self.mean = value
            return self.mean, 0.0
        delta = value - self.mean
        self.mean += self.alpha * delta
        self.var = (1.0 - self.alpha) * (self.var + self.alpha * (delta ** 2))
        deviation = math.sqrt(self.var) if self.count >= self.min_samples else 0.0
        return self.mean, deviation
'''.strip(),
    "2. Smoothed inverse-variance weights": '''
import numpy as np
import pandas as pd

def inverse_variance_weights(features: pd.DataFrame, smoothing: float = 0.15) -> np.ndarray:
    """Blends the sample covariance with an identity prior and returns normalized inverse-variance weights."""
    if features.empty or len(features) < 3:
        raise ValueError("Need at least 3 rows of features")
    sample_cov = features.cov().values
    n_features = sample_cov.shape[0]
    prior = np.eye(n_features) * (np.trace(sample_cov) / n_features)
    blended = (1.0 - smoothing) * sample_cov + smoothing * prior
    scales = np.sqrt(np.diag(blended))
    raw_weights = [1.0 / s if s > 0.0 else 0.0 for s in scales]
    total = sum(raw_weights)
    return np.array([w / total for w in raw_weights]) if total > 0.0 else np.ones(n_features) / n_features
'''.strip(),
    "3. Retry plan with exponential backoff": """
import math
from dataclasses import dataclass

@dataclass(frozen=True)
class RetryPlan:
    delay: float
    remaining_budget: float
    attempts_left: int
    jitter: float

def plan_retry(
    attempt: int,
    elapsed: float,
    base: float = 0.5,
    factor: float = 2.0,
    cap: float = 30.0,
    budget: float = 120.0,
) -> RetryPlan:
    delay = min(cap, base * (factor ** attempt))
    jitter = delay * 0.1 * math.log(1.0 + attempt)
    remaining = budget - elapsed - delay
    attempts_left = int(math.log(cap / base, factor)) - attempt
    return RetryPlan(delay + jitter, remaining, max(attempts_left, 0), jitter)
""".strip(),
    "4. Async manifest loader with error recovery": """
import asyncio
import json
from pathlib import Path

async def load_manifests(paths: list[str], min_size: float = 1000.0) -> dict[str, float]:
    merged: dict[str, float] = {}
    for raw_path in paths:
        try:
            await asyncio.sleep(0.0)
            with open(Path(raw_path)) as handle:
                payload = json.load(handle)
            filtered = {
                name: size for name, size in payload.items()
                if size is not None and size >= min_size
            }
            merged = {**merged, **filtered}
        except Exception as err:
            print(f"Skipped {raw_path}: {err}")
            continue
    return merged
""".strip(),
    "5. Decorator factory and argument unpacking": """
def with_multiplier(scale: float = 1.0):
    def decorator(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs) * scale
        return wrapper
    return decorator

@with_multiplier(100.0)
def score_pipeline(base_scores: list[float], *bonus_lists: list[float], floor: float = 0.0, **weights: float) -> float:
    combined = [*base_scores]
    for blist in bonus_lists:
        combined = [*combined, *blist]
    clamped = [x if x > floor else floor for x in combined]
    w_sum = sum(weights.values()) if weights else 1.0
    return (sum(clamped) / len(clamped)) * w_sum if clamped else 0.0
""".strip(),
}

STDLIB_SAMPLES: dict[str, tuple[str, list[str]]] = {
    # name -> (module __file__ owner, qualified function names to extract, in order)
    "6. textwrap.TextWrapper._wrap_chunks": (textwrap.__file__, ["TextWrapper._wrap_chunks"]),
    "7. json.encoder py_encode_basestring_ascii + JSONEncoder.default": (
        json.encoder.__file__,
        ["py_encode_basestring_ascii", "JSONEncoder.default"],
    ),
}


def extract_functions(module_path: str, wanted: Sequence[str]) -> str:
    """``ast.unparse`` text of the named functions/methods of a module, as module-level defs."""
    tree = ast.parse(Path(module_path).read_text(encoding="utf-8"))
    found: list[tuple[int, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                    qual = f"{node.name}.{sub.name}"
                    if qual in wanted:
                        found.append((wanted.index(qual), sub))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name in wanted:
            found.append((wanted.index(node.name), node))
    found.sort(key=lambda t: t[0])
    missing = set(wanted) - {wanted[i] for i, _ in found}
    if missing:
        raise LookupError(f"{module_path}: could not find {sorted(missing)}")
    return ast.unparse(ast.Module(body=[n for _, n in found], type_ignores=[]))  # type: ignore[misc]


def sample_sources() -> dict[str, str]:
    """The 7 SPEC section 12.1 samples: 5 README workloads + 2 stdlib extracts, unparsed."""
    samples = {name: ast.unparse(ast.parse(src)) for name, src in BENCHMARK_WORKLOADS.items()}
    for name, (path, wanted) in STDLIB_SAMPLES.items():
        samples[name] = extract_functions(path, wanted)
    return samples


# ============================================================================
# 2. BASELINES
# ============================================================================


class _DocstringStripper(ast.NodeTransformer):
    """Drop the docstring Expr of Module/ClassDef/FunctionDef/AsyncFunctionDef (SPEC section 11)."""

    @staticmethod
    def _strip(body: list[ast.stmt], is_module: bool) -> list[ast.stmt]:
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
            if not body and not is_module:
                body = [ast.Pass()]
        return body

    def visit_Module(self, node: ast.Module) -> ast.AST:
        node.body = self._strip(node.body, is_module=True)
        self.generic_visit(node)
        return node

    def _visit_def(self, node: Any) -> ast.AST:
        node.body = self._strip(node.body, is_module=False)
        self.generic_visit(node)
        return node

    visit_FunctionDef = _visit_def
    visit_AsyncFunctionDef = _visit_def
    visit_ClassDef = _visit_def


def strip_docstrings(tree: ast.Module) -> ast.Module:
    out = _DocstringStripper().visit(copy.deepcopy(tree))
    ast.fix_missing_locations(out)
    return out


def minifier_whitespace_only() -> Callable[[str], str] | None:
    """python-minifier with every transform disabled: comments and optional whitespace only."""
    try:
        import python_minifier as pm
    except ImportError:
        return None

    def minify(src: str) -> str:
        return pm.minify(
            src,
            rename_locals=False,
            rename_globals=False,
            remove_literal_statements=False,
            remove_annotations=False,
            hoist_literals=False,
            combine_imports=False,
            remove_pass=False,
            remove_object_base=False,
            convert_posargs_to_args=False,
            remove_explicit_return_none=False,
            remove_builtin_exception_brackets=False,
            constant_folding=False,
            remove_debug=False,
            remove_asserts=False,
        )

    return minify


# ============================================================================
# 3. TOKENIZERS AND THE PYDENSE PACKAGE (lazy, with clear failure messages)
# ============================================================================


def token_counters() -> dict[str, Callable[[str], int]]:
    try:
        import tiktoken
    except ImportError:
        sys.exit(
            "token_compression: tiktoken is not installed; every number in SPEC section 12\n"
            "an exact tiktoken count, so this benchmark refuses to approximate.\n"
            "Install it with: pip install -e '.[bench]'"
        )
    counters: dict[str, Callable[[str], int]] = {}
    for name in ("o200k_base", "cl100k_base"):
        enc = tiktoken.get_encoding(name)
        counters[name] = (lambda e: lambda s: len(e.encode(s, disallowed_special=())))(enc)
    return counters


def load_pydense() -> Any:
    try:
        import pydense
    except ImportError as exc:
        sys.exit(
            f"token_compression: cannot import the pydense package ({exc}).\n"
            "Run `pip install -e .` from the repository root "
            "(or check that pydense/__init__.py exists)."
        )
    for attr in ("encode", "parse"):
        if not hasattr(pydense, attr):
            sys.exit(
                f"token_compression: pydense.{attr} is missing; "
                "the core package is not complete yet."
            )
    return pydense


# ============================================================================
# 4. MEASUREMENT
# ============================================================================


@dataclass
class SampleResult:
    name: str
    tokens: dict[str, dict[str, int]]  # encoding -> column -> count
    encode_ms: dict[str, float]  # mode -> ms
    parse_ms: dict[str, float]  # mode -> ms
    ast_ok: dict[str, bool]  # mode -> round-trip equals the mode-adjusted reference
    texts: dict[str, str] = field(default_factory=dict)  # column -> text (omitted from JSON)

    def pct(self, enc: str, col: str, base: str) -> float:
        b = self.tokens[enc][base]
        return (self.tokens[enc][col] / b - 1.0) * 100.0 if b else 0.0


def _ann_stripped(tree: ast.Module) -> ast.Module:
    """STRIPPED reference: no docstrings, no param/return annotations, ``x: T = v`` -> ``x = v``."""

    class Strip(ast.NodeTransformer):
        def _visit_def(self, node: Any) -> ast.AST:
            node.returns = None
            self.generic_visit(node)
            return node

        visit_FunctionDef = _visit_def
        visit_AsyncFunctionDef = _visit_def

        def visit_arg(self, node: ast.arg) -> ast.AST:
            node.annotation = None
            return node

        def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
            if node.value is None:
                return node  # bare ``x: T`` is kept (SPEC section 11)
            return ast.copy_location(
                ast.Assign(targets=[node.target], value=self.visit(node.value), type_comment=None),
                node,
            )

    out = Strip().visit(strip_docstrings(tree))
    ast.fix_missing_locations(out)
    return out


def reference_dump(tree: ast.Module, mode: str) -> str:
    if mode == "full":
        ref = tree
    elif mode == "nodoc":
        ref = strip_docstrings(tree)
    else:
        ref = _ann_stripped(tree)
    return ast.dump(ref, include_attributes=False)


def measure_sample(
    name: str,
    src: str,
    pydense: Any,
    counters: dict[str, Callable[[str], int]],
    minify: Callable[[str], str] | None,
    repeats: int = 5,
) -> SampleResult:
    tree = ast.parse(src)
    py_doc = ast.unparse(tree)
    py_nodoc = ast.unparse(strip_docstrings(tree))
    texts = {"py_doc": py_doc, "py_nodoc": py_nodoc}
    if minify is not None:
        try:
            texts["minifier"] = minify(py_doc)
        except Exception as exc:  # noqa: BLE001 - third-party tool; report, do not abort
            print(f"  python-minifier failed on {name}: {exc}", file=sys.stderr)

    encode_ms: dict[str, float] = {}
    parse_ms: dict[str, float] = {}
    ast_ok: dict[str, bool] = {}
    for mode in MODES:
        best_enc = float("inf")
        dense = ""
        for _ in range(repeats):
            t0 = time.perf_counter()
            dense = pydense.encode(py_doc, mode=mode)
            best_enc = min(best_enc, time.perf_counter() - t0)
        best_parse = float("inf")
        back: ast.Module | None = None
        for _ in range(repeats):
            t0 = time.perf_counter()
            back = pydense.parse(dense)
            best_parse = min(best_parse, time.perf_counter() - t0)
        texts[mode] = dense
        encode_ms[mode] = best_enc * 1000.0
        parse_ms[mode] = best_parse * 1000.0
        ast_ok[mode] = back is not None and ast.dump(
            back, include_attributes=False
        ) == reference_dump(tree, mode)

    tokens = {
        enc: {col: count(text) for col, text in texts.items()} for enc, count in counters.items()
    }
    return SampleResult(name, tokens, encode_ms, parse_ms, ast_ok, texts)


def totals(results: Sequence[SampleResult]) -> SampleResult:
    encs = results[0].tokens.keys() if results else []
    tokens: dict[str, dict[str, int]] = {}
    for enc in encs:
        cols = [c for c in results[0].tokens[enc] if all(c in r.tokens[enc] for r in results)]
        tokens[enc] = {c: sum(r.tokens[enc][c] for r in results) for c in cols}
    encode_ms = {m: sum(r.encode_ms[m] for r in results) for m in MODES}
    parse_ms = {m: sum(r.parse_ms[m] for r in results) for m in MODES}
    ast_ok = {m: all(r.ast_ok[m] for r in results) for m in MODES}
    return SampleResult("TOTAL", tokens, encode_ms, parse_ms, ast_ok)


# ============================================================================
# 5. REPORTING
# ============================================================================


def _fmt(n: int, pct: float | None = None, bold: bool = False) -> str:
    cell = f"{n:,}" if pct is None else f"{n:,} ({pct:+.2f}%)"
    return f"**{cell}**" if bold else cell


def markdown_tables(results: Sequence[SampleResult], total: SampleResult, per_sample: bool) -> str:
    has_min = "minifier" in total.tokens.get("o200k_base", {})
    out: list[str] = []
    for enc in total.tokens:
        out.append(f"### {enc}")
        out.append("")
        header = ["sample", "py_doc", "py_nodoc"]
        if has_min:
            header.append("minifier (vs py_doc)")
        header += [
            "FULL (vs py_doc)",
            "NODOC (vs py_nodoc)",
            "STRIPPED (vs py_nodoc, lossy)",
            "parse ms (FULL)",
        ]
        out.append("| " + " | ".join(header) + " |")
        out.append("|" + "---|" * len(header))
        rows = list(results) if per_sample else []
        rows.append(total)
        for r in rows:
            is_total = r is total
            cells = [
                f"**{r.name}**" if is_total else r.name,
                _fmt(r.tokens[enc]["py_doc"], bold=is_total),
                _fmt(r.tokens[enc]["py_nodoc"], bold=is_total),
            ]
            if has_min:
                if "minifier" in r.tokens[enc]:
                    cells.append(
                        _fmt(r.tokens[enc]["minifier"], r.pct(enc, "minifier", "py_doc"), is_total)
                    )
                else:
                    cells.append("n/a")
            cells.append(_fmt(r.tokens[enc]["full"], r.pct(enc, "full", "py_doc"), is_total))
            cells.append(_fmt(r.tokens[enc]["nodoc"], r.pct(enc, "nodoc", "py_nodoc"), is_total))
            cells.append(
                _fmt(r.tokens[enc]["stripped"], r.pct(enc, "stripped", "py_nodoc"), is_total)
            )
            cells.append(f"{r.parse_ms['full']:.2f}")
            out.append("| " + " | ".join(cells) + " |")
        out.append("")
    # Baseline notes (SPEC section 12.1: say which baseline each percentage is against).
    enc0 = "o200k_base" if "o200k_base" in total.tokens else next(iter(total.tokens))
    o = total.tokens[enc0]
    doc_share = (1.0 - o["py_nodoc"] / o["py_doc"]) * 100.0 if o["py_doc"] else 0.0
    out.append(
        "Baselines: FULL is measured against `ast.unparse` with docstrings; NODOC and STRIPPED"
    )
    out.append(
        "against `ast.unparse` with docstrings removed. Against the with-docstring baseline NODOC"
    )
    out.append(
        f"would read {total.pct(enc0, 'nodoc', 'py_doc'):+.2f}% and STRIPPED "
        f"{total.pct(enc0, 'stripped', 'py_doc'):+.2f}% ({enc0}), but {doc_share:.1f} points of "
        "that is docstring removal, not notation. STRIPPED is lossy."
    )
    if has_min:
        out.append(
            "python-minifier is run whitespace-only (lossless, one-way) on the same `ast.unparse` "
            "text."
        )
    else:
        out.append("python-minifier column omitted: `pip install python-minifier` to include it.")
    fid = ", ".join(f"{m}={'ok' if total.ast_ok[m] else 'MISMATCH'}" for m in MODES)
    out.append(f"AST round-trip against the mode-adjusted reference: {fid}.")
    out.append(
        "Latency (best of 5, sum over samples): encode "
        + " / ".join(f"{m} {total.encode_ms[m]:.1f} ms" for m in MODES)
        + "; parse "
        + " / ".join(f"{m} {total.parse_ms[m]:.1f} ms" for m in MODES)
        + "."
    )
    return "\n".join(out)


def to_json(
    results: Sequence[SampleResult], total: SampleResult, meta: dict[str, Any]
) -> dict[str, Any]:
    def strip(r: SampleResult) -> dict[str, Any]:
        d = asdict(r)
        d.pop("texts", None)
        return d

    return {"meta": meta, "samples": [strip(r) for r in results], "total": strip(total)}


# ============================================================================
# 6. CORPUS
# ============================================================================


def stdlib_corpus() -> list[Path]:
    spec = importlib.util.spec_from_file_location(
        "corpus_fidelity", Path(__file__).with_name("corpus_fidelity.py")
    )
    if spec is None or spec.loader is None:
        sys.exit("token_compression: benchmarks/corpus_fidelity.py not found")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = (
        mod  # dataclasses with postponed annotations need the module registered
    )
    spec.loader.exec_module(mod)
    return list(mod.default_corpus())


def read_sources(paths: Iterable[Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in paths:
        try:
            src = p.read_text(encoding="utf-8")
            ast.parse(src)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            print(f"  skipping {p}: {exc}", file=sys.stderr)
            continue
        key = str(p)
        for root in (sysconfig.get_paths()["stdlib"], str(Path.cwd())):
            if key.startswith(root + os.sep):
                key = key[len(root) + 1 :]
                break
        out[key] = src  # keyed by path so that e.g. http/client.py and xmlrpc/client.py both count
    return out


# ============================================================================
# 7. MAIN
# ============================================================================


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--corpus", choices=["stdlib"], help="measure the corpus_fidelity.py stdlib corpus instead"
    )
    ap.add_argument(
        "--files", nargs="*", type=Path, help="explicit Python files instead of the 7 samples"
    )
    ap.add_argument("--json", type=Path, help="write a machine-readable report here")
    ap.add_argument(
        "--dump", type=Path, help="write sN.{full,nodoc,stripped}.dpy and sN.py into this directory"
    )
    ap.add_argument(
        "--per-file", action="store_true", help="with --corpus/--files: one row per file"
    )
    ap.add_argument(
        "--repeats", type=int, default=5, help="timing repeats per measurement (best of N)"
    )
    args = ap.parse_args(argv)

    pydense = load_pydense()
    counters = token_counters()
    minify = minifier_whitespace_only()

    if args.corpus:
        sources = read_sources(stdlib_corpus())
        label, per_sample = "stdlib corpus", args.per_file
    elif args.files:
        sources = read_sources(args.files)
        label, per_sample = "files", True
    else:
        sources = sample_sources()
        label, per_sample = "7 samples (SPEC section 12.1)", True

    results: list[SampleResult] = []
    t_start = time.perf_counter()
    for name, src in sources.items():
        try:
            results.append(
                measure_sample(name, src, pydense, counters, minify, repeats=args.repeats)
            )
        except Exception as exc:  # noqa: BLE001 - keep going, report at the end
            print(f"  FAILED {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
    wall = time.perf_counter() - t_start
    if not results:
        sys.exit("token_compression: nothing measured")
    total = totals(results)

    version = getattr(pydense, "__version__", "?")
    print(
        f"## PyDense {version} token compression - {label}, {len(results)} measured, "
        f"{wall:.1f} s wall\n"
    )
    print(markdown_tables(results, total, per_sample))

    if args.dump:
        args.dump.mkdir(parents=True, exist_ok=True)
        for i, r in enumerate(results, 1):
            (args.dump / f"s{i}.py").write_text(r.texts["py_doc"] + "\n", encoding="utf-8")
            for mode in MODES:
                (args.dump / f"s{i}.{mode}.dpy").write_text(r.texts[mode], encoding="utf-8")
        print(f"\nSamples written to {args.dump}")

    if args.json:
        meta = {
            "pydense": version,
            "python": sys.version.split()[0],
            "label": label,
            "minifier": minify is not None,
            "wall_seconds": wall,
        }
        args.json.write_text(json.dumps(to_json(results, total, meta), indent=1), encoding="utf-8")
        print(f"\nJSON report written to {args.json}")

    return 0 if all(total.ast_ok.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
