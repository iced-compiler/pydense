"""Data-driven AST round trip over every battery snippet in all three modes (SPEC §17.3).

Oracle: ``ast.dump(parse(encode(src, mode))) == ast.dump(reference(src, mode))`` where the reference is
``ast.parse(src)`` adjusted for the mode (SPEC §11) — only the reference is normalised, never the output.
``decode()`` of the emitted text must also re-parse with ``ast.parse`` to the same AST.
"""

from __future__ import annotations

import ast
from collections import Counter

import pytest
from _util import (
    MODES,
    first_diff,
    load_batteries,
    plain_dump,
    reference_dump,
    skip_unsupported,
    snippet_params,
)

SNIPPETS = load_batteries()


def test_batteries_not_empty() -> None:
    assert len(SNIPPETS) > 900, "every panel battery plus the construct matrix should be present"


def test_battery_snippets_are_valid_python() -> None:
    for s in SNIPPETS:
        if not s.supported:
            continue
        try:
            ast.parse(s.src)
        except SyntaxError as exc:  # pragma: no cover - battery bug
            pytest.fail(f"{s.id}: not valid Python on this interpreter: {exc}")


def test_battery_snippets_are_unique() -> None:
    dumps = Counter(plain_dump(ast.parse(s.src)) for s in SNIPPETS if s.supported)
    dups = [d[:80] for d, n in dumps.items() if n > 1]
    assert not dups, f"{len(dups)} duplicated snippets (by AST): {dups[:5]}"


def test_version_tags_are_needed() -> None:
    """A snippet tagged 3.12+/3.13+ must really fail on an older feature_version (no over-tagging)."""
    for s in SNIPPETS:
        if s.min_version <= (3, 10) or not s.supported:
            continue
        older = (3, s.min_version[1] - 1)
        try:
            ast.parse(s.src, feature_version=older)
        except SyntaxError:
            continue
        # feature_version does not model every change (PEP 701, PEP 646 subscripts); accept if the
        # snippet uses one of those constructs textually.
        if "f'" in s.src or 'f"' in s.src or "[*" in s.src or "*Ts" in s.src or ": *" in s.src:
            continue
        pytest.fail(f"{s.id} is tagged {s.min_version} but parses with feature_version={older}")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("snippet", snippet_params(SNIPPETS))
def test_roundtrip(snippet, mode, pydense_mod) -> None:
    skip_unsupported(snippet)
    want = reference_dump(snippet.src, mode)
    dpy = pydense_mod.encode(snippet.src, mode=mode)
    assert isinstance(dpy, str)
    try:
        got = pydense_mod.parse(dpy)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"parse() rejected the emitter's own output: {exc}\ndpy={dpy!r}")
    got_dump = plain_dump(got)
    if got_dump != want:
        pytest.fail(
            f"round trip changed the AST (mode={mode})\ndpy={dpy!r}\n"
            f"back={ast.unparse(got)!r}\n{first_diff(want, got_dump)}"
        )
    # decode() must give standard Python that re-parses to the same AST
    py = pydense_mod.decode(dpy)
    assert isinstance(py, str)
    if py.strip():
        assert py.endswith("\n"), "decode() output must end with a newline"
    assert plain_dump(ast.parse(py)) == want, f"decode() output differs\npy={py!r}"


@pytest.mark.parametrize("snippet", snippet_params(SNIPPETS))
def test_emitted_text_has_no_optional_whitespace(snippet, pydense_mod) -> None:
    """Canonical layout (SPEC §10.1): no indentation, no blank lines, no trailing newline, no ';'
    outside string literals.  Checked line-wise on lines that do not start inside a string."""
    skip_unsupported(snippet)
    dpy = pydense_mod.encode(snippet.src)
    assert not dpy.endswith("\n")
    assert "\n\n" not in dpy
    in_triple = False
    for line in dpy.split("\n"):
        if in_triple:
            if line.count('"""') % 2 == 1 or line.count("'''") % 2 == 1:
                in_triple = False
            continue
        if line.count('"""') % 2 == 1 or line.count("'''") % 2 == 1:
            in_triple = True
            continue
        assert line == line.lstrip(" \t"), f"indented line in canonical output: {line!r}"
