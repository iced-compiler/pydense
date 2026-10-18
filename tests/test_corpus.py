"""Whole-file stdlib round trip (SPEC §17.3): 12 files in FULL and NODOC by default;
``PYDENSE_FULL_CORPUS=1`` extends the run to every stdlib module with a per-file timeout."""

from __future__ import annotations

import ast
import os
import signal
import sysconfig
from contextlib import contextmanager
from pathlib import Path

import pytest
from _util import first_diff, has_docstring_anywhere, plain_dump, reference_dump

STDLIB = Path(sysconfig.get_paths()["stdlib"])

# each entry lists fallbacks for layouts that moved between Python versions
DEFAULT_FILES = [
    ("textwrap.py",),
    ("json/encoder.py",),
    ("dataclasses.py",),
    ("functools.py",),
    ("argparse.py",),
    ("enum.py",),
    ("statistics.py",),
    ("asyncio/tasks.py",),
    ("typing.py",),
    ("pathlib/_local.py", "pathlib/__init__.py", "pathlib.py"),
    ("http/client.py",),
    ("unittest/case.py",),
]

FULL_CORPUS = os.environ.get("PYDENSE_FULL_CORPUS") == "1"
PER_FILE_TIMEOUT = float(os.environ.get("PYDENSE_CORPUS_TIMEOUT", "10"))


def _resolve(candidates: tuple[str, ...]) -> Path | None:
    for c in candidates:
        p = STDLIB / c
        if p.exists():
            return p
    return None


def _default_params():
    out = []
    for cands in DEFAULT_FILES:
        p = _resolve(cands)
        if p is None:
            out.append(
                pytest.param(None, id=cands[0], marks=pytest.mark.skip(reason="not in this stdlib"))
            )
        else:
            out.append(pytest.param(p, id=cands[0]))
    return out


def _full_corpus_params():
    if not FULL_CORPUS:  # one skipped row instead of walking the stdlib at collection time
        return [pytest.param(None, id="stdlib", marks=pytest.mark.slow)]
    skip_dirs = {
        "site-packages",
        "test",
        "tests",
        "idlelib",
        "lib2to3",
        "__pycache__",
        "turtledemo",
    }
    files = []
    for p in sorted(STDLIB.rglob("*.py")):
        rel = p.relative_to(STDLIB)
        if any(part in skip_dirs for part in rel.parts):
            continue
        files.append(pytest.param(p, id=str(rel), marks=pytest.mark.slow))
    return files


@contextmanager
def _time_limit(seconds: float, what: str):
    if not hasattr(signal, "SIGALRM") or seconds <= 0:
        yield
        return

    def handler(signum, frame):  # noqa: ARG001
        raise TimeoutError(f"{what} exceeded {seconds}s")

    old = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _read(path: Path) -> str | None:
    try:
        src = path.read_text(encoding="utf-8")
        ast.parse(src)
    except (SyntaxError, UnicodeDecodeError, OSError, ValueError):
        return None
    return src


def _roundtrip_file(pydense_mod, path: Path, mode: str, timeout: float) -> None:
    src = _read(path)
    if src is None:
        pytest.skip(f"{path.name} is not parseable Python on this interpreter")
    with _time_limit(timeout, f"encode+parse of {path.name}"):
        dpy = pydense_mod.encode(src, mode=mode)
        back = pydense_mod.parse(dpy, filename=str(path))
    want = reference_dump(src, mode)
    got = plain_dump(back)
    if got != want:
        pytest.fail(f"{path}: AST mismatch in {mode}\n{first_diff(want, got)}")


@pytest.mark.parametrize("mode", ["full", "nodoc"])
@pytest.mark.parametrize("path", _default_params())
def test_stdlib_subset_roundtrip(pydense_mod, path, mode) -> None:
    _roundtrip_file(pydense_mod, path, mode, timeout=60.0)


@pytest.mark.parametrize("path", _default_params())
def test_stdlib_subset_idempotent_nodoc(pydense_mod, path) -> None:
    src = _read(path)
    if src is None:
        pytest.skip("not parseable here")
    full = pydense_mod.encode(src)
    assert pydense_mod.encode(pydense_mod.parse(full)) == full, (
        f"{path.name}: FULL is not a fixed point"
    )
    once = pydense_mod.encode(src, mode="nodoc")
    back = pydense_mod.parse(once)
    again = pydense_mod.encode(back)
    if has_docstring_anywhere(back):  # a string statement moved into docstring position
        assert plain_dump(pydense_mod.parse(again)) == plain_dump(back)
    else:
        assert again == once, f"{path.name}: NODOC text is not a fixed point"


@pytest.mark.parametrize("path", _default_params())
def test_stdlib_subset_decodes_to_python(pydense_mod, path) -> None:
    src = _read(path)
    if src is None:
        pytest.skip("not parseable here")
    py = pydense_mod.decode(pydense_mod.encode(src))
    assert plain_dump(ast.parse(py)) == reference_dump(src, "full")


@pytest.mark.skipif(not FULL_CORPUS, reason="set PYDENSE_FULL_CORPUS=1")
@pytest.mark.parametrize("mode", ["full", "nodoc"])
@pytest.mark.parametrize("path", _full_corpus_params())
def test_full_stdlib_roundtrip(pydense_mod, path, mode) -> None:
    _roundtrip_file(pydense_mod, path, mode, timeout=PER_FILE_TIMEOUT)
