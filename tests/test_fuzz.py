"""Spec-legal layout perturbation fuzzer (dependency-free; the hypothesmith round-trip fuzzer lives in
``test_fuzz_hypothesis.py``).

The fuzzer takes canonical ``.dpy`` output for real stdlib modules and inserts whitespace,
blank lines, indentation, comments, ``;`` separators and newlines in the places docs/SPEC.md
section 6.6 declares insignificant, then checks the AST is unchanged.
"""

from __future__ import annotations

import ast
import random
import sysconfig
import zlib
from pathlib import Path

import pytest

import pydense
from pydense.lexer import HARD_KEYWORDS, tokenize

KW_CONT = {"else", "elif", "except", "finally", "case"}
# After these a NEWLINE is significant (the statement ends), so the fuzzer must not add one there.
NL_SENSITIVE_PREV = {
    "return",
    "raise",
    "yield",
    "del",
    "global",
    "nonlocal",
    "assert",
    "pass",
    "break",
    "continue",
}

STDLIB = sysconfig.get_paths()["stdlib"]
FILES = [
    "textwrap.py",
    "json/encoder.py",
    "dataclasses.py",
    "statistics.py",
    "enum.py",
    "heapq.py",
    "shlex.py",
]


def _mutate(d: str, rng: random.Random) -> str:
    toks = [t for t in tokenize(d) if t.kind != "EOF"]
    out: list[str] = []
    pos = 0
    for i, t in enumerate(toks):
        gap = d[pos : t.pos]
        pos = t.end
        r = rng.random()
        prev = toks[i - 1] if i else None
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if t.kind == "NEWLINE":
            if r < 0.2:
                out.append("\n\n")
            elif r < 0.4:
                out.append("\n    ")
            elif r < 0.5:
                out.append("   \n")
            elif r < 0.6:
                out.append(" # trailing comment\n")
            elif (
                r < 0.7
                and prev is not None
                and prev.value not in ("}", "{")
                and nxt
                and nxt.value != "}"
            ):
                out.append(";")
            else:
                out.append("\n")
            continue
        text = d[t.pos : t.end]
        # A newline before a block '{' is free only after a complete header expression; after an
        # operator or keyword (`in`, `return`, `=`) the newline ends the expression (SPEC 6.6).
        header_end = prev is not None and (
            (prev.kind == "NAME" and prev.value not in HARD_KEYWORDS)
            or prev.kind in ("NUMBER", "STRING")
            or prev.value in (")", "]", "else", "try", "finally")
        )
        if t.kind == "OP" and t.value == "}" and r < 0.3:
            out.append(gap + "\n" + " " * rng.randint(0, 4))  # newline before '}' is always free
        elif t.kind == "OP" and t.value == "{" and r < 0.3 and header_end:
            out.append(gap + "\n" + " " * rng.randint(0, 4))  # newline before a block '{'
        elif t.kind == "NAME" and t.value in KW_CONT and r < 0.3:
            out.append(gap + "\n")
        elif r < 0.2:
            out.append(gap + " ")
        else:
            out.append(gap)
        out.append(text)
        if (
            t.kind == "OP"
            and t.value == "{"
            and rng.random() < 0.1
            and nxt is not None
            and nxt.kind == "NEWLINE"
        ):
            out.append(" # opening a block\n")
        if (
            t.kind == "OP"
            and t.value == "}"
            and rng.random() < 0.15
            and (nxt is None or nxt.kind == "NEWLINE")
        ):
            out.append(";")
    return "".join(out)


@pytest.mark.parametrize("rel", FILES)
def test_layout_perturbations_keep_ast(rel: str) -> None:
    path = Path(STDLIB, rel)
    if not path.exists():
        pytest.skip(f"{rel} not in this stdlib")
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    dense = pydense.encode(src)
    # crc32 (not hash()) so a failure is reproducible regardless of PYTHONHASHSEED
    seed = zlib.crc32(rel.encode())
    rng = random.Random(seed)
    for i in range(4):
        mutated = _mutate(dense, rng)
        back = pydense.parse(mutated)
        assert ast.dump(back) == ast.dump(tree), f"{rel}: seed={seed} mutation #{i}"
