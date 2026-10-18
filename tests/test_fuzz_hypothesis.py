"""Random Python round-trips with hypothesmith (optional dependency; skipped when missing)."""

from __future__ import annotations

import ast
import warnings

import pytest

import pydense

hypothesmith = pytest.importorskip("hypothesmith", exc_type=ImportError)
hypothesis = pytest.importorskip("hypothesis", exc_type=ImportError)

from hypothesis import HealthCheck, given, settings  # noqa: E402


@settings(max_examples=150, deadline=None, suppress_health_check=list(HealthCheck), database=None)
@given(hypothesmith.from_grammar(start="file_input") | hypothesmith.from_node())
def test_random_python_round_trips(src: str) -> None:
    try:
        tree = ast.parse(src)
        with warnings.catch_warnings():
            # generated programs routinely contain `is 1`, `"\d"` and the like
            warnings.simplefilter("ignore", SyntaxWarning)
            compile(tree, "<fuzz>", "exec")
    except Exception:  # noqa: BLE001 - Python itself rejects the sample
        return
    dense = pydense.encode(src)
    back = pydense.parse(dense)
    assert ast.dump(back) == ast.dump(tree), dense
    assert pydense.encode(ast.unparse(back)) == dense
