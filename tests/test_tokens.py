"""Token regression on the 7 reference samples (SPEC §12.1): LOSSLESS-NODOC o200k total 1281 and
FULL 1585 at the time of writing; asserted with slack (<= 1300 / <= 1600).  Skipped without tiktoken
(or when its encodings cannot be loaded, e.g. offline)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from _util import SAMPLES_DIR, _Normalizer

tiktoken = pytest.importorskip("tiktoken")

NODOC_BUDGET = 1300
FULL_BUDGET = 1600
NODOC_BUDGET_CL100K = 1280
FULL_BUDGET_CL100K = 1580


def _encoding(name: str):
    try:
        return tiktoken.get_encoding(name)
    except Exception as exc:  # noqa: BLE001 - network / cache problems
        pytest.skip(f"tiktoken encoding {name} unavailable: {exc}")


@pytest.fixture(scope="module")
def o200k():
    return _encoding("o200k_base")


@pytest.fixture(scope="module")
def cl100k():
    return _encoding("cl100k_base")


def _count(enc, text: str) -> int:
    return len(enc.encode(text, disallowed_special=()))


def _samples() -> list[str]:
    paths = sorted(Path(SAMPLES_DIR).glob("s*.py"))
    assert len(paths) == 7, paths
    return [p.read_text(encoding="utf-8") for p in paths]


def _strip_docstrings(src: str) -> str:
    """Python text of the NODOC reference (SPEC §11) for the ast.unparse baseline."""
    tree = _Normalizer(strip_types=False, strip_docstrings=True).visit(ast.parse(src))
    return ast.unparse(ast.fix_missing_locations(tree))


def test_lossless_nodoc_total_o200k(pydense_mod, o200k) -> None:
    total = sum(_count(o200k, pydense_mod.encode(s, mode="nodoc")) for s in _samples())
    baseline = sum(_count(o200k, _strip_docstrings(s)) for s in _samples())
    assert total <= NODOC_BUDGET, f"LOSSLESS-NODOC o200k total {total} > {NODOC_BUDGET}"
    assert total < baseline, f"no reduction: {total} vs ast.unparse baseline {baseline}"
    assert (baseline - total) / baseline >= 0.15, (
        f"reduction {(baseline - total) / baseline:.1%} below 15%"
    )


def test_full_total_o200k(pydense_mod, o200k) -> None:
    total = sum(_count(o200k, pydense_mod.encode(s, mode="full")) for s in _samples())
    baseline = sum(_count(o200k, ast.unparse(ast.parse(s))) for s in _samples())
    assert total <= FULL_BUDGET, f"FULL o200k total {total} > {FULL_BUDGET}"
    assert total < baseline


def test_stripped_is_not_larger_than_nodoc_o200k(pydense_mod, o200k) -> None:
    nodoc = sum(_count(o200k, pydense_mod.encode(s, mode="nodoc")) for s in _samples())
    stripped = sum(_count(o200k, pydense_mod.encode(s, mode="stripped")) for s in _samples())
    assert stripped <= nodoc


def test_totals_cl100k(pydense_mod, cl100k) -> None:
    nodoc = sum(_count(cl100k, pydense_mod.encode(s, mode="nodoc")) for s in _samples())
    full = sum(_count(cl100k, pydense_mod.encode(s, mode="full")) for s in _samples())
    assert nodoc <= NODOC_BUDGET_CL100K, nodoc
    assert full <= FULL_BUDGET_CL100K, full


def test_pretty_costs_little(pydense_mod, o200k) -> None:
    plain = sum(_count(o200k, pydense_mod.encode(s, mode="nodoc")) for s in _samples())
    pretty = sum(
        _count(o200k, pydense_mod.encode(s, mode="nodoc", pretty=True)) for s in _samples()
    )
    assert plain <= pretty <= plain + 25, (plain, pretty)


def test_cheatsheet_budget(pydense_mod, o200k) -> None:
    assert _count(o200k, pydense_mod.CHEATSHEET) <= 450
