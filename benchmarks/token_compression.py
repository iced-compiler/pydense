#!/usr/bin/env python3
"""
PyDense Token Compression & Transpilation Latency Benchmark Suite
Outputs a GitHub README-ready Markdown table comparing Python vs. PyDense (.pyd).
"""

from __future__ import annotations
import re
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

# Ensure parent directory is importable when running as `python benchmarks/token_compression.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydense import PyDenseCompiler, PyDenseDecompiler

# ============================================================================
# 1. TOKENIZER LOADER (tiktoken + Deterministic Subword Fallback)
# ============================================================================

def get_token_counters() -> Tuple[Callable[[str], int], Callable[[str], int], str]:
    """Returns (o200k_counter, cl100k_counter, backend_label)."""
    try:
        import tiktoken

        enc_o200k = tiktoken.get_encoding("o200k_base")
        enc_cl100k = tiktoken.get_encoding("cl100k_base")
        return (
            lambda s: len(enc_o200k.encode(s)),
            lambda s: len(enc_cl100k.encode(s)),
            "tiktoken (exact BPE)",
        )
    except ImportError:
        # Fallback BPE subword approximation when tiktoken is not installed
        bpe_pat = re.compile(r"    |\n|[A-Za-z_]\w*|\d+(?:\.\d+)?|==|!=|<=|>=|->|\*\*|//|[^\s\w]")
        return (
            lambda s: len(bpe_pat.findall(s)),
            lambda s: int(len(bpe_pat.findall(s)) * 1.03),
            "regex-bpe-approx (install `tiktoken` for exact counts)",
        )


# ============================================================================
# 2. BENCHMARK WORKLOAD SUITE
# ============================================================================

BENCHMARK_WORKLOADS: Dict[str, str] = {
    "1. Rolling EWMA & Volatility Tracker": '''
import math

class RollingRiskTracker:
    """Tracks exponential moving average and variance over a price stream."""
    def __init__(self, span: int = 20, min_periods: int = 5):
        self.alpha: float = 2.0 / (span + 1.0)
        self.min_p: int = min_periods
        self.mean: float = 0.0
        self.var: float = 0.0
        self.count: int = 0

    def update(self, price: float) -> tuple[float, float]:
        self.count += 1
        if self.count == 1:
            self.mean = price
            return self.mean, 0.0
        delta = price - self.mean
        self.mean += self.alpha * delta
        self.var = (1.0 - self.alpha) * (self.var + self.alpha * (delta ** 2))
        vol = math.sqrt(self.var) if self.count >= self.min_p else 0.0
        return self.mean, vol
'''.strip(),

    "2. Covariance Shrinkage & Inv-Vol Weights": '''
import numpy as np
import pandas as pd

def shrunk_inv_vol_weights(returns_df: pd.DataFrame, shrinkage: float = 0.15) -> np.ndarray:
    """Computes shrinkage covariance matrix and normalized inverse-volatility weights."""
    if returns_df.empty or len(returns_df) < 3:
        raise ValueError("Insufficient return observations")
    sample_cov = returns_df.cov().values
    n_assets = sample_cov.shape[0]
    prior = np.eye(n_assets) * (np.trace(sample_cov) / n_assets)
    shrunk = (1.0 - shrinkage) * sample_cov + shrinkage * prior
    vols = np.sqrt(np.diag(shrunk))
    raw_weights = [1.0 / v if v > 0.0 else 0.0 for v in vols]
    weight_sum = sum(raw_weights)
    return np.array([w / weight_sum for w in raw_weights]) if weight_sum > 0.0 else np.ones(n_assets) / n_assets
'''.strip(),

    "3. Avellaneda-Stoikov Quote Calculator": '''
import math
from dataclasses import dataclass

@dataclass(frozen=True)
class MarketQuote:
    bid_price: float
    ask_price: float
    reservation_price: float
    half_spread: float

def compute_optimal_quotes(
    mid_price: float,
    inventory: float,
    gamma: float = 0.1,
    volatility: float = 0.02,
    horizon: float = 1.0,
    kappa: float = 1.5,
) -> MarketQuote:
    variance = (volatility ** 2) * horizon
    res_price = mid_price - (inventory * gamma * variance)
    spread = gamma * variance + (2.0 / gamma) * math.log(1.0 + (gamma / kappa))
    half = spread / 2.0
    return MarketQuote(res_price - half, res_price + half, res_price, half)
'''.strip(),

    "4. Async Batch Fetcher & Error Recovery": '''
import asyncio
import json
from pathlib import Path

async def process_snapshots(paths: list[str], min_liquidity: float = 1000.0) -> dict[str, float]:
    valid_books: dict[str, float] = {}
    for raw_path in paths:
        try:
            await asyncio.sleep(0.0)
            with open(Path(raw_path)) as handle:
                payload = json.load(handle)
            filtered = {
                sym: val for sym, val in payload.items()
                if val is not None and val >= min_liquidity
            }
            valid_books = {**valid_books, **filtered}
        except Exception as err:
            print(f"Skipped {raw_path}: {err}")
            continue
    return valid_books
'''.strip(),

    "5. Decorator Retry & Config Unpacker": '''
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
'''.strip(),
}


# ============================================================================
# 3. BENCHMARK RUNNER
# ============================================================================

def run_benchmarks() -> None:
    count_o200k, count_cl100k, backend_name = get_token_counters()
    compiler = PyDenseCompiler()
    decomp_typed = PyDenseDecompiler(use_positional_args=True, preserve_types=True)
    decomp_stripped = PyDenseDecompiler(use_positional_args=True, preserve_types=False)

    print(f"Tokenizer Backend: {backend_name}\n")
    print("| Workload | Python Tokens (`o200k`) | PyDense Typed (`.pyd`) | PyDense Stripped (`.pyd`) | Token Reduction | AST Compile Time |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: |")

    tot_py_o200k = 0
    tot_pyd_typed_o200k = 0
    tot_pyd_strip_o200k = 0
    tot_py_cl100k = 0
    tot_pyd_strip_cl100k = 0
    latencies_ms: List[float] = []

    for name, py_src in BENCHMARK_WORKLOADS.items():
        pyd_typed = decomp_typed.decompile(py_src)
        pyd_strip = decomp_stripped.decompile(py_src)

        # Verify AST round-trip compilation and measure latency
        t0 = time.perf_counter()
        tree = compiler.compile_to_ast(pyd_typed)
        _ = compile(tree, "<bench>", "exec")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        py_tok = count_o200k(py_src)
        typed_tok = count_o200k(pyd_typed)
        strip_tok = count_o200k(pyd_strip)

        tot_py_o200k += py_tok
        tot_pyd_typed_o200k += typed_tok
        tot_pyd_strip_o200k += strip_tok

        tot_py_cl100k += count_cl100k(py_src)
        tot_pyd_strip_cl100k += count_cl100k(pyd_strip)

        typed_save = (1.0 - typed_tok / py_tok) * 100.0
        strip_save = (1.0 - strip_tok / py_tok) * 100.0

        print(
            f"| **{name}** | {py_tok} | {typed_tok} (-{typed_save:.1f}%) | "
            f"**{strip_tok}** | **-{strip_save:.1f}%** | {elapsed_ms:.2f} ms |"
        )

    overall_typed_save = (1.0 - tot_pyd_typed_o200k / tot_py_o200k) * 100.0
    overall_strip_save = (1.0 - tot_pyd_strip_o200k / tot_py_o200k) * 100.0
    overall_cl100k_save = (1.0 - tot_pyd_strip_cl100k / tot_py_cl100k) * 100.0
    avg_lat = sum(latencies_ms) / len(latencies_ms)

    print(
        f"| **TOTAL / AVERAGE** | **{tot_py_o200k}** | **{tot_pyd_typed_o200k} (-{overall_typed_save:.1f}%)** | "
        f"**{tot_pyd_strip_o200k}** | **-{overall_strip_save:.1f}%** | **{avg_lat:.2f} ms** |"
    )
    print(f"\nSecondary Tokenizer Check (`cl100k_base`): {tot_py_cl100k} -> {tot_pyd_strip_cl100k} tokens (-{overall_cl100k_save:.1f}% reduction)")


if __name__ == "__main__":
    run_benchmarks()