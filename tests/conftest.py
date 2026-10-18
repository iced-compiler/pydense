"""pytest configuration: repo root on sys.path, shared fixtures, version gating."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
for p in (str(ROOT), str(TESTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _util import (  # noqa: E402
    MODES,
    PY,
    Snippet,
    load_batteries,
    normalized_dump,
    plain_dump,
    reference_dump,
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: whole-stdlib corpus run (PYDENSE_FULL_CORPUS=1)")


@pytest.fixture(scope="session")
def pydense_mod():
    import pydense

    return pydense


@pytest.fixture(scope="session")
def encode(pydense_mod):
    return pydense_mod.encode


@pytest.fixture(scope="session")
def parse(pydense_mod):
    return pydense_mod.parse


@pytest.fixture(scope="session")
def decode(pydense_mod):
    return pydense_mod.decode


@pytest.fixture(scope="session")
def all_snippets() -> list[Snippet]:
    return load_batteries()


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return TESTS_DIR / "samples"


@pytest.fixture
def roundtrip(pydense_mod):
    """roundtrip(src, mode) -> asserts parse(encode(src, mode)) == mode-adjusted reference."""

    def _rt(src: str, mode: str = "full") -> str:
        dpy = pydense_mod.encode(src, mode=mode)
        got = pydense_mod.parse(dpy)
        want = reference_dump(src, mode)
        assert plain_dump(got) == want, f"mode={mode}\ndpy={dpy!r}\nback={ast.unparse(got)!r}"
        return dpy

    return _rt


__all__ = ["MODES", "PY", "normalized_dump", "plain_dump", "reference_dump"]
