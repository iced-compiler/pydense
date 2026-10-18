"""Canonical form: the SPEC §14 Rosetta stone as exact text, the three workload listings, and
idempotence ``encode(decode(encode(x))) == encode(x)`` over every battery (SPEC §10, §17.4)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from _util import (
    MODES,
    PY,
    SAMPLES_DIR,
    has_docstring_anywhere,
    load_batteries,
    plain_dump,
    reference_dump,
    skip_unsupported,
    snippet_params,
)

V311 = (3, 11)
V312 = (3, 12)

# (id, python, canonical dpy in NODOC mode[, min version]) — every row of SPEC §14.
# Rows the SPEC marks "(in class)" are wrapped in ``class A:`` on both sides.
ROSETTA: list[tuple] = [
    ("assign", "x = 1\na = b = c", "x=1\na=b=c"),
    ("annassign", "x: int = 5\nx: int\n(x): int", "x:int=5\nx:int\n(x):int"),
    ("call_and_dict", "f(a, b)\n{k: v}", "f(a,b)\n{k:v}"),
    (
        "if_elif_else",
        "if a:\n    x = 1\nelif b:\n    x = 2\nelse:\n    x = 3",
        "if a{\nx=1}elif b{\nx=2}else{\nx=3}",
    ),
    # SPEC §14 prints ``if v<0{continue}`` on one line; §5.4/§10.1 (and every workload listing) put a
    # newline after a non-empty block's ``{``, so the canonical form derived from §10 is asserted here.
    (
        "for_else",
        "for i, v in enumerate(xs):\n    if v < 0: continue\n    total += v\nelse:\n    done = True",
        "for i,v in enumerate(xs){\nif v<0{\ncontinue}\ntotal+=v}else{\ndone=True}",
    ),
    (
        "while_walrus",
        "while chunk := f.read(8):\n    buf.append(chunk)",
        "while chunk:=f.read(8){\nbuf.append(chunk)}",
    ),
    (
        "try_full",
        "try:\n    risky()\nexcept (ValueError, TypeError) as e:\n    log(e)\n    raise\nelse:\n    ok = True\nfinally:\n    close()",
        "try{\nrisky()}except(ValueError,TypeError)as e{\nlog(e)\nraise}else{\nok=True}finally{\nclose()}",
    ),
    ("try_star", "try: ...\nexcept* OSError as eg: pass", "try{\n...}except*OSError as eg{}", V311),
    (
        "with_items",
        "with open(p) as f, lock:\n    data = f.read()",
        "with open(p)as f,lock{\ndata=f.read()}",
    ),
    (
        "class_methods",
        "class A:\n    def __init__(self, a, b=1):\n        self.a = a; self.b = b\n    def total(self):\n        return self.a + self.b",
        "class A{\ndef __init__(a,b=1){\n.a=a\n.b=b}\ndef total(){\nreturn.a+.b}}",
    ),
    (
        "classmethod",
        "class A:\n    @classmethod\n    def make(cls, x): return cls(x)",
        "class A{\n@classmethod def make(x){\nreturn cls(x)}}",
    ),
    (
        "staticmethod",
        "class A:\n    @staticmethod\n    def s(x): return x",
        "class A{\n@staticmethod def s(x){\nreturn x}}",
    ),
    (
        "property_abstractmethod",
        "class A:\n    @property\n    @abstractmethod\n    def p(self): return self._p",
        "class A{\n@property@abstractmethod def p(){\nreturn._p}}",
    ),
    ("new_cls", "class A:\n    def __new__(cls, *a): ...", "class A{\ndef __new__(cls,*a){\n...}}"),
    (
        "def_bang",
        "class A:\n    def f(this, x): return this.x",
        "class A{\ndef!f(this,x){\nreturn this.x}}",
    ),
    (
        "full_signature",
        "def f(a, b=1, /, c=2, *d, e, f=3, **g) -> None: pass",
        "def f(a,b=1,/,c=2,*d,e,f=3,**g)->None{}",
    ),
    (
        "async_everything",
        "async def main():\n    async with sess as s:\n        async for x in s.stream():\n            await handle(x)",
        "async def main(){\nasync with sess as s{\nasync for x in s.stream(){\nawait handle(x)}}}",
    ),
    (
        "generator",
        "def gen():\n    yield 1; yield from other(); x = yield; return x",
        "def gen(){\nyield 1\nyield from other()\nx=yield\nreturn x}",
    ),
    ("raise_from", 'raise ValueError("bad") from exc', "raise ValueError('bad')from exc"),
    (
        "simple_statements",
        'assert x > 0, "msg"; del a[0], b.c; global g; nonlocal n',
        "assert x>0,'msg'\ndel a[0],b.c\nglobal g\nnonlocal n",
    ),
    (
        "imports",
        "import numpy as np\nfrom ..pkg.mod import thing as t, other\nfrom . import x",
        "import numpy as np\nfrom ..pkg.mod import thing as t,other\nfrom . import x",
    ),
    (
        "match",
        'match cmd.split():\n    case [action]: go(action)\n    case Point(x=0, y=0) | Point(x=1): origin()\n    case {"k": v, **rest}: use(v)\n'
        '    case [first, *others] if len(others) > 1: many()\n    case str() as s: text(s)\n    case 1 | -2 | 1+2j | "s" | None: lit()\n    case _: pass',
        "match cmd.split(){\ncase[action]{\ngo(action)}\ncase Point(x=0,y=0)|Point(x=1){\norigin()}\ncase {'k':v,**rest}{\nuse(v)}\n"
        "case[first,*others]if len(others)>1{\nmany()}\ncase str()as s{\ntext(s)}\ncase 1|-2|1+2j|'s'|None{\nlit()}\ncase _{}}",
    ),
    (
        "type_alias",
        "type Alias[T: int, *Ts, **P] = dict[T, P]",
        "type Alias[T:int,*Ts,**P]=dict[T,P]",
        V312,
    ),
    (
        "generic_class",
        "class Box[T](Generic[T]):\n    def get[U](self, default: U = None) -> T | U: return self.item",
        "class Box[T](Generic[T]){\ndef get[U](default:U=None)->T|U{\nreturn.item}}",
        V312,
    ),
    ("ternary", "y = a if c else b\ny = a if c else (d if e else f)", "y=c?a:b\ny=c?a:e?d:f"),
    ("lambda", "f(lambda: 1, key=lambda x: x[1])", "f(lambda:1,key=lambda x:x[1])"),
    (
        "comprehensions",
        "y = [x * 2 for x in it if x > 0 if x < 9]\n{k: v for k, v in d.items() if v is not None}\n(x async for x in aiter())",
        "y=[x*2 for x in it if x>0 if x<9]\n{k:v for k,v in d.items()if v is not None}\n(x async for x in aiter())",
    ),
    (
        "call_and_subscripts",
        "f(*a, *b, **c, k=1)\na[1:2], a[::2], a[1:2, 3], a[...], a[*idx]",
        "f(*a,*b,**c,k=1)\na[1:2],a[::2],a[1:2,3],a[...],a[*idx]",
        V311,
    ),
    (
        "displays",
        "(), (1,), [], {}, {1}, {*()}, {**a, 'b': 1}",
        "(),(1,),[],{},{1},{*()},{**a,'b':1}",
    ),
    (
        "numbers",
        "1j, 0x1F, 1_000_000, 1e-5, 0.5, 100.0, -0.5, 1.0 .real",
        "1j,31,1000000,1e-05,.5,100.,-.5,(1.).real",
    ),
    ("strings", 'b"\\x00", rb"raw", u"uni", "a" "b"', "b'\\x00',b'raw',u'uni','ab'"),
    (
        "fstrings",
        'f"{x!r:>{w}.{p}f} {d[\'k\']} {y=} {{lit}}"\nf"{self.name}: {a if c else b}"',
        "f\"{x!r:>{w}.{p}f} {d['k']} y={y!r} {{lit}}\"\nf'{.name}: {(c?a:b)}'",
    ),
    (
        "precedence",
        "y = not a and not (b or c)\n(a or b) and c\n(-a) ** 2\n-a ** 2\na < b <= c != d\na not in b is not c",
        "y=not a and not(b or c)\n(a or b)and c\n(-a)**2\n-a**2\na<b<=c!=d\na not in b is not c",
    ),
    (
        "set_in_header",
        "if x in {1, 2}: pass\nif x == {1}: go()",
        "if x in {1,2}{}\nif x=={1}{\ngo()}",
    ),
    (
        "ternary_parenthesised",
        "s[1:-1 if n > 2 else None]\n{(a if c else b): v}",
        "s[1:(n>2?-1:None)]\n{(c?a:b):v}",
    ),
]

WORKLOAD_1 = """import math
class RunningStats{
def __init__(span:int=20,min_samples:int=5){
.alpha:float=2./(span+1.)
.min_samples:int=min_samples
.mean:float=0.
.var:float=0.
.count:int=0}
def update(value:float)->tuple[float,float]{
.count+=1
if.count==1{
.mean=value
return.mean,0.}
delta=value-.mean
.mean+=.alpha*delta
.var=(1.-.alpha)*(.var+.alpha*delta**2)
deviation=.count>=.min_samples?math.sqrt(.var):0.
return.mean,deviation}}"""

WORKLOAD_1_FULL = WORKLOAD_1.replace(
    "class RunningStats{\n",
    'class RunningStats{\n"""Tracks an exponential moving average and variance over a stream of readings."""\n',
)

WORKLOAD_4 = """import asyncio
import json
from pathlib import Path
async def load_manifests(paths:list[str],min_size:float=1000.)->dict[str,float]{
merged:dict[str,float]={}
for raw_path in paths{
try{
await asyncio.sleep(0.)
with open(Path(raw_path))as handle{
payload=json.load(handle)}
filtered={name:size for name,size in payload.items()if size is not None and size>=min_size}
merged={**merged,**filtered}}except Exception as err{
print(f'Skipped {raw_path}: {err}')
continue}}
return merged}"""

WORKLOAD_5 = """def with_multiplier(scale:float=1.){
def decorator(func){
def wrapper(*args,**kwargs){
return func(*args,**kwargs)*scale}
return wrapper}
return decorator}
@with_multiplier(100.)def score_pipeline(base_scores:list[float],*bonus_lists:list[float],floor:float=0.,**weights:float)->float{
combined=[*base_scores]
for blist in bonus_lists{
combined=[*combined,*blist]}
clamped=[x>floor?x:floor for x in combined]
w_sum=weights?sum(weights.values()):1.
return clamped?sum(clamped)/len(clamped)*w_sum:0.}"""


def _rosetta_params():
    out = []
    for row in ROSETTA:
        rid, py, dpy = row[:3]
        ver = row[3] if len(row) > 3 else (3, 10)
        marks = [pytest.mark.skipif(PY < ver, reason=f"needs Python {ver[0]}.{ver[1]}+")]
        out.append(pytest.param(py, dpy, id=rid, marks=marks))
    return out


@pytest.mark.parametrize("py,dpy", _rosetta_params())
def test_rosetta_exact_text(py, dpy, pydense_mod) -> None:
    assert pydense_mod.encode(py, mode="nodoc") == dpy


@pytest.mark.parametrize("py,dpy", _rosetta_params())
def test_rosetta_dpy_parses_to_python_ast(py, dpy, pydense_mod) -> None:
    assert plain_dump(pydense_mod.parse(dpy)) == plain_dump(ast.parse(py))


@pytest.mark.parametrize("py,dpy", _rosetta_params())
def test_rosetta_is_fixed_point(py, dpy, pydense_mod) -> None:
    assert pydense_mod.encode(pydense_mod.decode(dpy), mode="nodoc") == dpy


def _sample(n: int) -> str:
    return (SAMPLES_DIR / f"s{n}.py").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "sample,mode,expected",
    [
        pytest.param(1, "nodoc", WORKLOAD_1, id="workload1-nodoc"),
        pytest.param(1, "full", WORKLOAD_1_FULL, id="workload1-full"),
        pytest.param(4, "nodoc", WORKLOAD_4, id="workload4-nodoc"),
        pytest.param(4, "full", WORKLOAD_4, id="workload4-full-has-no-docstrings"),
        pytest.param(5, "nodoc", WORKLOAD_5, id="workload5-nodoc"),
        pytest.param(5, "full", WORKLOAD_5, id="workload5-full-has-no-docstrings"),
    ],
)
def test_workload_listings(sample, mode, expected, pydense_mod) -> None:
    assert pydense_mod.encode(_sample(sample), mode=mode) == expected


@pytest.mark.parametrize("sample", [1, 4, 5])
def test_workload_listings_parse_back(sample, pydense_mod) -> None:
    text = {1: WORKLOAD_1, 4: WORKLOAD_4, 5: WORKLOAD_5}[sample]
    assert plain_dump(pydense_mod.parse(text)) == reference_dump(_sample(sample), "nodoc")


SNIPPETS = load_batteries()


@pytest.mark.parametrize("snippet", snippet_params(SNIPPETS))
def test_idempotence_all_modes(snippet, pydense_mod) -> None:
    """encode(decode(encode(x, m))) == encode(x, m) for every mode (SPEC §17.4).

    The only tolerated exception: when a lossy mode drops a docstring and the *next* statement is a
    string, that string sits in docstring position in the re-encoded text and is written with
    triple quotes (docstring style, as ast.unparse does); the AST is still identical and is asserted."""
    skip_unsupported(snippet)
    for mode in MODES:
        once = pydense_mod.encode(snippet.src, mode=mode)
        back = pydense_mod.parse(once)
        twice = pydense_mod.encode(pydense_mod.decode(once))
        again = pydense_mod.encode(back)
        if mode != "full" and has_docstring_anywhere(back):
            assert plain_dump(pydense_mod.parse(twice)) == plain_dump(back), f"mode={mode}"
            assert plain_dump(pydense_mod.parse(again)) == plain_dump(back), f"mode={mode}"
            continue
        assert twice == once, f"mode={mode}\nonce ={once!r}\ntwice={twice!r}"
        assert again == once, f"mode={mode} (via parse)\nonce ={once!r}\nagain={again!r}"


def test_samples_present() -> None:
    assert sorted(p.name for p in Path(SAMPLES_DIR).glob("s*.py")) == [
        f"s{i}.py" for i in range(1, 8)
    ]
