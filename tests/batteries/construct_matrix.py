"""Construct matrix: one Python snippet per ``ast`` node type (SPEC §9) and per listed edge.

Item forms: ``src`` | ``(name, src)`` | ``(src, (3, 12))`` | ``(name, src, (3, 12))``.
"""

V311 = (3, 11)
V312 = (3, 12)
V313 = (3, 13)

SNIPPETS = [
    # ------------------------------------------------------------------ mod
    ("empty_module", ""),
    ("docstring_only_module", '"""Only a docstring."""\n'),
    ("module_docstring_then_code", '"""Doc."""\nimport os\nx = 1\n'),
    # ------------------------------------------------------------------ statements (28)
    ("FunctionDef", "def f(a, b=1):\n    return a + b\n"),
    ("FunctionDef_docstring_only", 'def f():\n    """only a docstring"""\n'),
    ("FunctionDef_docstring_then_body", 'def f():\n    """doc"""\n    return 1\n'),
    ("AsyncFunctionDef", "async def f(x):\n    await g(x)\n    return x\n"),
    ("ClassDef", "class A(B, C, metaclass=M, **kw):\n    x = 1\n"),
    ("ClassDef_no_bases", "class A:\n    pass\n"),
    ("ClassDef_docstring_only", 'class A:\n    """only a docstring"""\n'),
    (
        "ClassDef_nested",
        "class Outer:\n    class Inner:\n        class Deep:\n            def m(self):\n                return self\n        def n(self):\n            return Deep\n",
    ),
    ("Return_bare", "def f():\n    return\n"),
    ("Return_tuple", "def f():\n    return 1, 2\n"),
    ("Return_starred", "def f():\n    return *a, b\n"),
    ("Delete", "del a, b[0], c.d, (e), [f, g]\n"),
    ("Assign_chain", "a = b = c = 1\n"),
    ("Assign_tuple_targets", "a, b = b, a\n[p, q] = r\n(x, y), z = w\n"),
    ("TypeAlias", "type X = list[int]\n", V312),
    ("TypeAlias_params", "type Alias[T: int, *Ts, **P] = dict[T, P]\n", V312),
    ("TypeAlias_defaults_pep696", "type X[T = int, *Ts = *tuple[int], **P = [int]] = T\n", V313),
    ("TypeAlias_starred_default_only", "type X[*Ts=*tuple[int]]=tuple[*Ts]\n", V313),
    (
        "AugAssign_all_13",
        "x += 1\nx -= 1\nx *= 1\nx /= 1\nx //= 1\nx %= 1\nx **= 1\nx >>= 1\nx <<= 1\nx &= 1\nx |= 1\nx ^= 1\nx @= m\n",
    ),
    ("AugAssign_attr_sub_targets", "a.b += 1\na[0] -= 1\nself.x += 1\n"),
    (
        "AnnAssign_forms",
        "x: int\ny: int = 5\n(z): int\n(w): int = 6\na.b: str = 'a'\nc[0]: int\nd: 'Forward' = None\ne: tuple[int, ...] = ()\n",
    ),
    (
        "For_else",
        "for i in range(3):\n    if i:\n        continue\n    break\nelse:\n    done = True\n",
    ),
    (
        "For_targets",
        "for x in a, b:\n    pass\nfor x, (y, z) in pairs:\n    pass\nfor [x, y] in w:\n    pass\nfor *a, b in c:\n    pass\nfor x, in y:\n    pass\n",
    ),
    (
        "AsyncFor_else",
        "async def f():\n    async for x in aiter():\n        pass\n    else:\n        pass\n",
    ),
    ("While_else", "while x:\n    x -= 1\nelse:\n    pass\n"),
    (
        "If_elif_else",
        "if a:\n    x = 1\nelif b:\n    x = 2\nelif c:\n    x = 3\nelse:\n    x = 4\n",
    ),
    ("If_else_nested_if_not_elif", "if a:\n    pass\nelse:\n    if b:\n        pass\n    c()\n"),
    ("If_else_single_if_collapses", "if a:\n    pass\nelse:\n    if b:\n        pass\n"),
    ("With_multiple_items", "with open(p) as f, open(q) as g, lock:\n    data = f.read()\n"),
    ("With_tuple_target", "with a as (x, y), b as [p, q]:\n    pass\n"),
    (
        "With_parenthesised",
        "with (open(p) as f, open(q) as g):\n    pass\nwith (a, b):\n    pass\nwith (a):\n    pass\n",
    ),
    ("With_attr_sub_target", "with a as b.c, d as e[0]:\n    pass\n"),
    ("AsyncWith", "async def f():\n    async with lock as l, other() as (o1, o2):\n        pass\n"),
    (
        "Match_all_pattern_kinds",
        "match cmd:\n"
        "    case 1:\n        pass\n"
        "    case -1:\n        pass\n"
        "    case 1 + 2j:\n        pass\n"
        "    case -1 - 2j:\n        pass\n"
        "    case 0.5:\n        pass\n"
        "    case 'text':\n        pass\n"
        "    case b'bytes':\n        pass\n"
        "    case 'a' 'b':\n        pass\n"
        "    case Color.RED:\n        pass\n"
        "    case a.b.c:\n        pass\n"
        "    case None:\n        pass\n"
        "    case True:\n        pass\n"
        "    case False:\n        pass\n"
        "    case [a, b, *rest]:\n        pass\n"
        "    case (a, b):\n        pass\n"
        "    case ():\n        pass\n"
        "    case []:\n        pass\n"
        "    case [*_]:\n        pass\n"
        "    case (p,):\n        pass\n"
        "    case (p):\n        pass\n"
        "    case {'k': v, **rest}:\n        pass\n"
        "    case {}:\n        pass\n"
        "    case {1: x, 'y': [a, *b]}:\n        pass\n"
        "    case Point(x=0, y=0):\n        pass\n"
        "    case Point(1, 2, z=3):\n        pass\n"
        "    case str():\n        pass\n"
        "    case a.b.Cls(k=1):\n        pass\n"
        "    case x:\n        pass\n"
        "    case _:\n        pass\n",
    ),
    (
        "Match_as_or_guard",
        "match cmd:\n"
        "    case [a] as whole if a > 0:\n        pass\n"
        "    case (1 | 2) as z:\n        pass\n"
        "    case 1 | 2 | 3:\n        pass\n"
        "    case Point(x=0) | Point(y=0) | None:\n        pass\n"
        "    case str() as s:\n        pass\n"
        "    case 'a' | 'b' as s:\n        pass\n"
        "    case x if x in {1, 2}:\n        pass\n"
        "    case {'k': v} if v:\n        pass\n"
        "    case [[a, b], c] if a < b < c:\n        pass\n",
    ),
    (
        "Match_subjects",
        "match a, b:\n    case 1, 2:\n        pass\nmatch *a, b:\n    case _:\n        pass\nmatch (x):\n    case _:\n        pass\nmatch {1: 2}:\n    case _:\n        pass\nmatch -x:\n    case _:\n        pass\nmatch not x:\n    case _:\n        pass\nmatch x if y else z:\n    case _:\n        pass\nmatch lambda: 1:\n    case _:\n        pass\n",
    ),
    (
        "Match_soft_keyword_uses",
        "match = 1\nmatch(x)\nmatch[0] = 2\nmatch.y = 3\nmatch, y = 1, 2\nmatch: int = 1\nmatch += 1\nmatch(x).y\nprint(match, case, type)\ncase = 4\ntype = 5\ntype(x)\n",
    ),
    ("Match_nested_match_and_case_names", "match match:\n    case case:\n        pass\n"),
    ("Raise_forms", "raise\nraise E\nraise E('x') from exc\nraise E from None\n"),
    (
        "Try_full",
        "try:\n    risky()\nexcept (ValueError, TypeError) as e:\n    log(e)\n    raise\nexcept KeyError:\n    pass\nexcept:\n    pass\nelse:\n    ok = True\nfinally:\n    close()\n",
    ),
    ("Try_finally_only", "try:\n    pass\nfinally:\n    pass\n"),
    (
        "TryStar",
        "try:\n    f()\nexcept* OSError as eg:\n    pass\nexcept* (TypeError, KeyError):\n    pass\n",
        V311,
    ),
    ("Assert_forms", "assert x\nassert x > 0, 'msg'\nassert (x, y)\nassert x, (a, b)\n"),
    ("Import_forms", "import a\nimport a.b.c\nimport a.b as c, d\nimport os.path as osp, sys\n"),
    (
        "ImportFrom_forms",
        "from . import x\nfrom .. import y as z\nfrom ...a.b import c as d, e\nfrom .... import w\nfrom m import *\nfrom m import (a, b,)\nfrom __future__ import annotations\n",
    ),
    (
        "Global_Nonlocal",
        "def f():\n    global a, b\n    x = 0\n    def g():\n        nonlocal x\n        x = 1\n    return g\n",
    ),
    ("Global_in_class_and_module", "global g\nclass A:\n    global h\n    h = 1\n"),
    (
        "Expr_statements",
        "f()\nx\n'str'\nb'bytes'\n1.0\n.5\n1j\n...\nx.y\nx[0]\n-x\n~x\n+x\nnot x\n(yield)\nlambda: 1\na if b else c\n[x for x in y]\n{1, 2}\n{}\n{1: 2}\n(1, 2)\n()\na, b\na,\nx == y\n",
    ),
    ("Pass_Break_Continue", "for x in y:\n    pass\n    break\n    continue\n"),
    (
        "Pass_only_bodies",
        "def f():\n    pass\nclass A:\n    pass\nif x:\n    pass\nelse:\n    pass\nwhile x:\n    pass\nfor x in y:\n    pass\ntry:\n    pass\nexcept:\n    pass\nwith x:\n    pass\nwhile y:\n    pass\n    pass\n",
    ),
    # ------------------------------------------------------------------ expressions (27)
    (
        "BoolOp",
        "x = a and b and c\ny = a or b\nz = (a or b) and c\nw = a or (b and c)\nv = a and (b and c)\nu = (a or b) or c\n",
    ),
    (
        "NamedExpr",
        "if (n := len(a)) > 10:\n    print(n)\nwhile chunk := f.read(8):\n    pass\nif n := len(a):\n    pass\nys = [y for x in xs if (y := f(x))]\nprint((q := 1))\nf(x := 1)\nx = (y := 2)\n[z := 1, z ** 2]\n",
    ),
    (
        "BinOp_all_13",
        "x = a + b\nx = a - b\nx = a * b\nx = a @ b\nx = a / b\nx = a % b\nx = a ** b\nx = a << b\nx = a >> b\nx = a | b\nx = a ^ b\nx = a & b\nx = a // b\n",
    ),
    (
        "BinOp_associativity",
        "x = a - (b - c)\ny = (a - b) - c\nz = a / (b / c)\nw = 2 ** 3 ** 4\nv = (2 ** 3) ** 4\nu = a @ (b @ c)\nt = (a @ b) @ c\ns = a % b % c\n",
    ),
    (
        "UnaryOp_4",
        "a = -x\nb = +x\nc = ~x\nd = not x\ne = - -x\nf = -(-x)\ng = ~-x\nh = not not x\ni = not -x\n",
    ),
    (
        "Lambda_defaults_star",
        "f = lambda a, b=1, /, c=2, *d, e, f=3, **g: a\ng = lambda *, k: k\nh = lambda *a: a\ni = lambda **k: k\nj = lambda: 0\nk = lambda x=(1 if c else 2): x\nl = lambda a, /: a\nm = lambda x=lambda: 1: x\nn = lambda: lambda: 1\n",
    ),
    (
        "IfExp",
        "x = a if c else b\ny = a if c else (d if e else f)\nz = (a if c else b) if d else e\nw = a if (b if c else d) else e\nv = (lambda: 1) if c else (lambda: 2)\nu = lambda: a if c else b\n",
    ),
    ("Dict", "d = {}\ne = {k: v, **m, 'b': 1}\nf = {**a}\ng = {a: {b: {c: {}}}}\nh = {1: 2,}\n"),
    ("Set", "s = {1}\nt = {1, 2, 3}\nu = {*a, *b}\nv = {*()}\nw = {1,}\n"),
    (
        "ListComp",
        "a = [x for x in y]\nb = [x * 2 for x in it if x > 0 if x < 9]\nc = [x for x in y for z in x if z]\nd = [(a, b) for a, b in c]\ne = [x async for x in aiter() if await x]\nf = [[x for x in y] for y in z]\n",
    ),
    (
        "SetComp",
        "a = {x for x in y}\nb = {x for x in y if x for z in x}\nc = {x async for x in y}\n",
    ),
    (
        "DictComp",
        "a = {k: v for k, v in d.items() if v is not None}\nb = {k: v for k in a for v in b}\nc = {k: v async for k, v in z}\n",
    ),
    (
        "GeneratorExp",
        "a = (x for x in y)\nb = (x for x in y for z in x if z)\nc = sum(x * x for x in xs)\nd = f((x for x in y), 1)\ne = (await x for x in y)\nf = (x async for x in aiter())\n",
    ),
    (
        "Await",
        "async def f():\n    await x\n    y = await g() + 1\n    z = (await g()) ** 2\n    w = await g() ** 2\n    v = -await g()\n    return await (await x)\n",
    ),
    (
        "Yield_YieldFrom",
        "def g():\n    yield\n    yield 1\n    yield 1, 2\n    yield *a, b\n    x = yield\n    y = yield 2\n    z = yield from other()\n    yield from other()\n    f((yield 3))\n    print((yield x).y)\n    return (yield)\n",
    ),
    (
        "Compare_all_10",
        "a = x == y\na = x != y\na = x < y\na = x <= y\na = x > y\na = x >= y\na = x is y\na = x is not y\na = x in y\na = x not in y\n",
    ),
    (
        "Compare_chained",
        "ok = 0 < x <= 10 != y is not None\nb = a not in b is not c in d\nc = (a, b) == (c, d)\nd = not a == b\ne = (not a) == b\n",
    ),
    (
        "Call",
        "f()\nf(a, b)\nf(a, *b, k=1, **kw)\nf(*a, *b, **c, **d)\nf(a=1, *b)\nf(**{'a': 1})\nf(x for x in y)\nf(a)(b)[c].d\nf(x, y := 1)\nprint(*a, sep='', end='')\n",
    ),
    (
        "JoinedStr_basic",
        "a = f'{x}'\nb = f'{x!r}'\nc = f'{x!s:^5}'\nd = f'{x!a}'\ne = f'{x:>{w}.{p}f}'\ng = f'{{}}'\nh = f'{{x}}{y}'\ni = f''\nj = f'{x:?<10}'\nk = f'{x:%Y-%m-%d}'\nl = f'{x:,}'\nm = f'{3.14:.2f}'\nn = f'{x:}'\no = f'{x!r:}'\np = f'{a}{b}' 'c' f'{d}'\nq = f'{a[1:2]}'\nr = f'{f(1, 2)}'\ns = f'{d[\"k\"]}'\nt = f\"{d['k']}\"\nu = f'{x:{y}}'\nv = f'{x:{y}{z}}'\nw = f'{x:{\"a\"}>10}'\n",
    ),
    (
        "JoinedStr_debug_equals",
        "a = f'{x=}'\nb = f'{x = }'\nc = f'{x=!r}'\nd = f'{x=:>10}'\ne = f'{x = !s:^5}'\n",
    ),
    (
        "JoinedStr_nested_other_quotes",
        "a = f\"{f'{x}'}\"\nb = f'{f\"{x}\"}'\nc = f\"{'nested'} {x if c else y} {(lambda: 1)}\"\nd = f'{(lambda: 1)()}'\ne = f'{ {1: 2}[1] }'\nf2 = f\"{'a' 'b'}\"\n",
    ),
    (
        "JoinedStr_triple_and_prefixes",
        "a = f'''multi\n{line}\n'''\nb = rf'\\d{x}'\nc = fr'\\d{x}'\nd = F'{x}'\ne = f'漢{x}字'\nf2 = f'a' 'b'\ng = 'a' f'{b}'\n",
    ),
    (
        "JoinedStr_self_fields",
        "class A:\n    def f(self):\n        return f'{self.x} {self.x!r:>10} {self.x:{self.w}} {self.name}: {self.a if self.c else self.b}'\n",
    ),
    (
        "JoinedStr_await_yield",
        "async def f():\n    return f'{await x}'\ndef g():\n    return f'{yield}'\n",
    ),
    (
        "JoinedStr_pep701_same_quotes",
        "a = f\"{d[\"k\"]}\"\nb = f'{d['k']}'\nc = f'{f'{x}'}'\n",
        V312,
    ),
    (
        "JoinedStr_pep701_newline_backslash_comment",
        "a = f'{x\n}'\nb = f'{\"\\n\"}'\n",
        V312,
    ),
    (
        "Constant_ints",
        "a = 0\nb = 1_000_000\nc = 0x1F\nd = 0o17\ne = 0b101\nf = 10 ** 100\ng = 12345678901234567890\n",
    ),
    (
        "Constant_floats",
        "a = 1.0\nb = 0.5\nc = 0.0\nd = 100.0\ne = -0.5\nf = 1e-05\ng = 1e-5\nh = 1.5e+300\ni = 1e16\nj = 1E5\nk = 1.e5\nl = .5e-3\nm = 1_0.0_1\nn = 123456789.123456789\no = 5e-324\np = 1.7976931348623157e308\nq = 1e400\nr = -1e400\ns = -0.0\n",
    ),
    (
        "Constant_complex",
        "a = 1j\nb = 1.5J\nc = .5j\nd = 1e3j\ne = 0j\nf = -0j\ng = 1 + 2j\nh = 1 - 0j\ni = 1e400j\n",
    ),
    (
        "Constant_strings",
        "a = 'it\\'s'\nb = \"say \\\"hi\\\"\"\nc = '''tri'ple'''\nd = \"\"\"tri\"ple\"\"\"\ne = 'line\\nbreak'\nf = r'\\d+'\ng = 'tab\\there'\nh = '\\\\'\ni = ''\nj = '\\0'\nk = '\\N{BULLET}\\u2022'\nl = 'é漢字🎉'\nm = '\\ud800'\nn = '#'\no = '{'\np = '}'\nq = ';'\nr = 'a?b:c'\ns = '\\\\u{0:04x}'.format(n)\nt = '%d' % x\n",
    ),
    ("Constant_implicit_concat", "x = 'a' 'b'\ny = ('long '\n     'string')\nz = b'a' b'b'\n"),
    ("Constant_multiline_string", 'x = """\nmulti\nline\n"""\n'),
    (
        "Constant_bytes",
        "a = b'bytes'\nb = b'\\x00\\xff'\nc = rb'raw\\d'\nd = Rb'x'\ne = BR'y'\nf = b''\n",
    ),
    ("Constant_u_prefix", "a = u'uni'\nb = U'x'\n"),
    (
        "Constant_singletons_ellipsis",
        "a = None, True, False\nb = ...\nc = Ellipsis\nd = x[..., 1]\ne = f(x=...)\ng = not ...\nh = -...\ndef i(a=..., *, b=...): ...\n",
    ),
    (
        "Attribute",
        "a = x.y.z\nb = (1).real\nc = (1.5).real\nd = 1.0.real\ne = 1 .real\nf = 'x'.upper()\ng = [1].pop()\nh = {}.get(1)\ni = (1,).count(1)\nj = ....__class__\nk = (...).x\nl = f(a).b[c].d()\nm = 1j.imag\n",
    ),
    (
        "Subscript_slices",
        "a[1:2]\na[::2]\na[1:]\na[:2]\na[:]\na[::]\na[1:2:3]\na[1::]\na[:1:]\na[1, 2]\na[1:2, 3]\na[x, y:z]\na[:, :]\na[..., 1]\na[()]\na[(1, 2)]\na[1,]\na[b:c, d:e]\na[1:2, ::3, ...]\na[(1 if c else 2):3]\na[(lambda: 1):2]\na[b := c]\na[:-1]\na[::-1]\n",
    ),
    ("Subscript_starred", "a[*idx]\na[*idx, 1]\na[*b, c:d]\na[*idx] = 1\n", V311),
    (
        "Starred_everywhere",
        "a, *b = c\n*a, b = c\n[*x, *y]\nf(*a, **k)\nfirst, *rest = [0, *vals, 9]\n{**a, 'k': 1, **b}\nx = *a, b\ny = (*a, *b)\nz = {*a, *b}\nfor *a, b in c:\n    pass\n[*a] = b\n(*a,) = b\n*a, = b\nprint(*a, sep='')\n",
    ),
    ("Name_contexts", "x = y\ndel z\nfor q in r:\n    pass\nimport os\n"),
    (
        "List_Tuple",
        "a = ()\nb = (1,)\nc = 1,\nd = (1, 2)\ne = []\nf = [1]\ng = [(), (1,)]\nh = (a, b)[0]\ni = f((a, b), c)\nj = print((a, b))\nk = x[1, 2]\nl = (((a, b)))\nm = (a)\n",
    ),
    # ------------------------------------------------------------------ parameters
    (
        "posonly_kwonly",
        "def f(a, b, /, c, d=1, *, e, f=2, **k):\n    pass\ndef g(a, /):\n    pass\ndef h(*, a):\n    pass\ndef i(*args: int, **kw: str) -> None:\n    pass\ndef j(a=1, /, b=2):\n    pass\ndef k(a, b, /, *, c):\n    pass\ndef l(a, b=1, /, c=2, *d, e, f=3, **g) -> None:\n    pass\n",
    ),
    (
        "star_annotations_pep646",
        "def f(*args: *Ts):\n    pass\ndef g(*args: *tuple[int, ...], **kw: int) -> None:\n    pass\n",
        V311,
    ),
    (
        "type_params_def_class",
        "def f[T: (int, str), *Ts, **P](xs: list[T], *args: *Ts, **kw: P.kwargs) -> T:\n    return xs[0]\nclass Box[T](Generic[T]):\n    def get[U](self, default: U = None) -> T | U:\n        return self.item\nclass A[T: int, *Ts, **P](Base, metaclass=Meta):\n    pass\n",
        V312,
    ),
    (
        "type_params_defaults_pep696",
        "def f[T = int, *Ts = *tuple[int, ...], **P = [int]](x: T) -> T:\n    return x\nclass A[T = int, *Ts = *tuple[int, ...], **P = [int]](Base, metaclass=M, **kw):\n    pass\n",
        V313,
    ),
    (
        "annotations_complex",
        "x: tuple[int, ...] = ()\ny: 'Forward' = None\nz: list[dict[str, int]] | None\nw: Callable[[int], str]\ndef f(a: int = 1, *, b: str = 'x', **k: float) -> dict[str, 'Forward']:\n    return {}\nasync def g() -> AsyncIterator[int]:\n    yield 1\n",
    ),
    # ------------------------------------------------------------------ decorators
    (
        "decorator_chains",
        "@a\n@b.c(1)\n@d[0].e\n@f.g[h](i)(j)\n@app.route('/x', methods=['GET', 'POST'])\ndef fn():\n    pass\n@dataclass(frozen=True)\n@total_ordering\nclass Q:\n    x: int\n    y: int = 0\n",
    ),
    (
        "decorator_matmul",
        "@(a @ b)\ndef f():\n    pass\n@a @ b\ndef g():\n    pass\n@a.b @ c\ndef h():\n    pass\n@a[b @ c]\ndef i():\n    pass\n@a(b @ c)\ndef j():\n    pass\n",
    ),
    (
        "decorator_non_chain",
        "@(f or g)\ndef h():\n    pass\n@lambda f: f\ndef j():\n    pass\n@a if c else b\ndef k():\n    pass\n@not a\ndef l():\n    pass\n@a == b\ndef m():\n    pass\n@-a\ndef n():\n    pass\n@'s'.join\ndef o():\n    pass\n@x[1:2]\ndef p():\n    pass\n@a()()\ndef q():\n    pass\n@self.x\ndef r():\n    pass\n@a.b\nasync def s():\n    pass\n",
    ),
    (
        "decorator_in_class",
        "class A:\n    @self.reg\n    def f(self):\n        pass\n    @x.setter\n    def x(self, v):\n        self._x = v\n    @functools.wraps(f)\n    def __init__(self, a):\n        self.a = a\n",
    ),
    # ------------------------------------------------------------------ receiver rule (§7)
    (
        "methods_receiver_rule",
        "class A(Base, metaclass=Meta):\n"
        "    x: int = 0\n"
        "    y: int\n"
        "    def __init__(self, a, b=1):\n        self.a = a\n"
        "    def plain(self):\n        return self\n"
        "    def no_params():\n        pass\n"
        "    def other_name(this, x):\n        return this.x\n"
        "    def self_then_cls(self, cls):\n        return cls\n"
        "    def __new__(cls, *args, **kw):\n        return super().__new__(cls)\n"
        "    def __init_subclass__(cls, **kw):\n        pass\n"
        "    def posonly(self, a, /, b, *, c=1, **kw):\n        return a\n"
        "    def posonly_self(self, /, x):\n        return x\n"
        "    def posonly_only(self, /):\n        return 1\n"
        "    def annotated_self(self: 'A', x: int) -> 'A':\n        return self\n"
        "    def defaulted(self=None):\n        return self\n"
        "    def varargs_only(*args):\n        return args\n"
        "    def kwonly_only(*, x):\n        return x\n"
        "    def kwargs_only(**kw):\n        return kw\n"
        "    def kwonly_self(*, self):\n        return self\n"
        "    def self_then_self_kw(self, *, cls=1):\n        return cls\n"
        "    def x_then_self(x, self):\n        return x\n"
        "    async def am(self, x):\n        await x\n"
        "    async def am2(x):\n        pass\n",
    ),
    (
        "methods_generic_pep695",
        "class A:\n    def f[T](self, x: T) -> T:\n        return x\n    def g[T](x: T) -> T:\n        return x\n    def __init__[T](self, x: T):\n        pass\n",
        V312,
    ),
    (
        "methods_decorated",
        "import abc\n"
        "class A:\n"
        "    @staticmethod\n    def s(x):\n        return x\n"
        "    @staticmethod\n    def s2():\n        return 1\n"
        "    @staticmethod\n    def s3(self):\n        return self\n"
        "    @classmethod\n    def c(cls, x):\n        return cls(x)\n"
        "    @classmethod\n    def c2(klass):\n        return klass\n"
        "    @classmethod\n    def c3(self):\n        return self\n"
        "    @classmethod\n    def c4(cls, self):\n        return cls\n"
        "    @abc.abstractmethod\n    def abstract(self):\n        pass\n"
        "    @builtins.staticmethod\n    def bs(x):\n        return x\n"
        "    @builtins.classmethod\n    def bc(cls):\n        return cls\n"
        "    @staticmethod\n    @cache\n    def sc(x):\n        return x\n"
        "    @cache\n    @staticmethod\n    def cs(x):\n        return x\n"
        "    @property\n    @abstractmethod\n    def p(self):\n        return self._p\n"
        "    @p.setter\n    def p(self, v):\n        self._p = v\n"
        "    @functools.wraps(g)\n    def __init__(self, x):\n        pass\n",
    ),
    (
        "metaclass_methods",
        "class Meta(type):\n    def __new__(mcs, name, bases, ns):\n        return super().__new__(mcs, name, bases, ns)\n    def __call__(cls, *a, **kw):\n        return super().__call__(*a, **kw)\n    def __init__(cls, name, bases, ns):\n        pass\n    def register(cls, kind, *, override=False):\n        cls._reg[kind] = cls\n        return cls\n",
    ),
    (
        "methods_nested_scopes",
        "class A:\n"
        "    def m(self, x):\n"
        "        def inner(y):\n            return self.a + y\n"
        "        lam = lambda z=1, *a, k, **kw: self.a + z\n"
        "        class Inner:\n            def im(self):\n                return self\n            def ih(x):\n                return x\n"
        "        def n():\n            class B:\n                def o(self):\n                    pass\n                def p(x):\n                    pass\n"
        "        return inner\n"
        "    if TYPE_CHECKING:\n        def conditional(self):\n            return 1\n    else:\n        def conditional(x):\n            return 2\n"
        "    try:\n        def t(self):\n            pass\n    except E:\n        def t(this):\n            pass\n    finally:\n        def u(self):\n            pass\n"
        "    with ctx():\n        def w(self):\n            pass\n"
        "    for i in r:\n        def fo(self):\n            pass\n"
        "    while c:\n        def wh(self):\n            pass\n"
        "    match x:\n        case 1:\n            def ma(self):\n                pass\n"
        "    f = lambda self: self.x\n"
        "    g = lambda cls: cls\n"
        "    h = self.y\n",
    ),
    (
        "self_outside_methods",
        "def f(self, x):\n    return self.x + x\ndef __init__(self, a):\n    self.a = a\nx = self.y\ndel self.x\nfor self.x in y:\n    pass\nwith a as self.x:\n    pass\nself.x: int = 1\nself.x += 1\n(self).x = 1\nself[0].x = 1\nself().x = 1\nx = [self.a for self.a in b]\nimport self\nglobal self\nf = lambda self: self.x\n",
    ),
    (
        "self_complex_targets",
        "class A:\n    def f(self):\n        return self.x.y.z(self.w)[self.v]\n    def g(self):\n        return (self, self.x)\n    def h(self):\n        return {self.a: self.b for self.c in self.d}\n    def i(self):\n        return -self.x in self.s\n    def j(self, x=self.y):\n        return x\n",
    ),
    # ------------------------------------------------------------------ misc edges
    (
        "unicode_identifiers",
        "π = 3.14159\n変数 = 1\nñ = 'ñ'\ndef naïve(ß):\n    return ß\nclass Ωmega:\n    def mét(self):\n        return self.π\n",
    ),
    ("line_continuation", "x = 1 + \\\n    2\nif a and \\\n   b:\n    pass\n"),
    (
        "multiline_brackets",
        "r = f(1,\n      2,\n      k=3)\nd = {\n    'a': 1,\n    'b': 2,\n}\nx = (foo()\n     .bar()\n     .baz())\ny = [\n    1,\n    2,\n]\nz = (1\n     + 2)\n",
    ),
    ("semicolons_in_python", "x = 1; y = 2\nif x: a = 1; b = 2\ndef f():\n    return;\n"),
    (
        "comments_and_type_comments",
        "x = 1  # type: int\n# full line comment with { } ; : ? \\\ndef f(a):  # type: (int) -> int\n    return a\n",
    ),
    (
        "keyword_glue_forms",
        "def f():\n    return'x'\n    return.5\n    if.5: pass\n    x = 1 if y else 2\n    return[1]\n    return{1}\n    return(1)\n    return -1\n    return not x\n    return f'x'\n    return b'x'\n    return lambda: 1\n",
    ),
    (
        "string_keyword_adjacency",
        "if x == '':\n    y = 'a'\nelif y in 'abc' and z:\n    print('x', end='')\nw = 'a' if c else 'b'\nv = ['a', 'b']\nu = {'a': 'b'}\nt = f('a')('b')['c']\ns = a == '' and b\n",
    ),
    (
        "float_keyword_adjacency",
        "x = 1.0 if c else 2.0\ny = 1.0 in z\nw = 1.0 is z\nv = 1.0 not in z\nu = 1.0 and z\nt = not 1.0\ns = 1.0 == e\nr = 1.0 - .5 - -.5\nq = 1.0 - -1.0\n",
    ),
    (
        "display_in_headers",
        "if x in {1, 2}:\n    pass\nif x == {1}:\n    go()\nwhile {}:\n    pass\nfor k in {}:\n    pass\nif {**d}:\n    pass\nif f({1, 2}) and [{3}]:\n    pass\nif (lambda: {1: 2})():\n    pass\nif {x for x in y}:\n    pass\nif {x: 1 for x in y}:\n    pass\nwith {1: 2} as d:\n    pass\nif x in ({1, 2}):\n    pass\n",
    ),
    (
        "display_statements",
        "{1: 2}\n{1, 2}\n{}\n{**a}\n{*a}\nif a:\n    pass\n{1: 2}\n[1][0]\nx = {}\n[0]\nif a:\n    pass\nelse:\n    {1: 2}\n",
    ),
    (
        "deep_nesting",
        "def f():\n    for i in range(3):\n        if i:\n            while True:\n                try:\n                    with a:\n                        break\n                finally:\n                    pass\n        else:\n            continue\n    return {1: {2: {3: {}}}}\n",
    ),
    ("huge_expression", "x = " + " + ".join(f"a{i}" for i in range(200)) + "\n"),
    ("deep_parentheses", "x = " + "(" * 50 + "1" + ")" * 50 + "\n"),
    (
        "conditional_import",
        "try:\n    import ujson as json\nexcept ImportError:\n    import json\n",
    ),
    (
        "not_statement_after_blocks",
        "try:\n    pass\nexcept E:\n    pass\nnot x\nif a:\n    b()\nnot c()\ntry:\n    pass\nfinally:\n    pass\n~x\n-x\n",
    ),
    (
        "docstring_oddities",
        "def f():\n    'doc' 'cat'\ndef g():\n    b'notdoc'\ndef h():\n    f'notdoc'\ndef i():\n    'not a docstring?'\n    'second string'\ndef j():\n    x = 1\n    'late string'\nclass A:\n    '''doc'''\n    x = 1\n'module level str not first'\n",
    ),
    (
        "docstrings_with_special_chars",
        'def f():\n    """Doc with ; and { } and # and \\\\ and \'quotes\' and ?:."""\n    return 1\n',
    ),
    (
        "async_everything",
        "async def f():\n    async with a as b, c:\n        pass\n    async for x in y:\n        pass\n    else:\n        pass\n    r = [x async for x in aiter() if await x]\n    s = {k: v async for k, v in z}\n    t = (await x for x in y)\n    for x in await g():\n        y = [a async for a in x]\n    return await (await x)\n",
    ),
    (
        "class_in_function",
        "def f():\n    class A:\n        def m(self):\n            def g(self):\n                return self\n            return g\n    return A\n",
    ),
    (
        "methods_named_like_keywords",
        "class A:\n    def match(self):\n        pass\n    def case(self):\n        pass\n    def type(self):\n        pass\n    def print(self):\n        pass\nx.match.case.type = 1\nmatch.case = 2\n",
    ),
    ("dunder_names", "__debug__\n_ = 1\nprint(_, __, ___)\nawait_ = 1\nyield_ = 2\nelif_ = 3\n"),
    ("ellipsis_bodies", "def f(): ...\nclass A: ...\nx = ...\nif x: ...\n"),
    (
        "walrus_everywhere",
        "x = (y := f(x))\ny = [z := 1, z ** 2]\nz = f(y := 1)\nw = f(x, y := 1)\nif (n := len(a)) > 10:\n    pass\nwhile chunk := f.read(10):\n    pass\nv = x[a := 1]\nu = x[(a := 1):b]\nt = f'{(x := 5)}'\n",
    ),
    (
        "ternary_contexts",
        "x = a if c else b\nd = {k: (v if c else w), (a if c else b): 1}\nf(a if c else b, k=a if c else b)\nl = [a if c else b for a in q]\ns = x[a if c else b]\nt = (a if c else b)[0]\nu = (a if c else b).x\nv = lambda: a if c else b\nw = a if (b if c else d) else e\ny = s[1:-1 if n > 2 else None]\nz = s[(a if c else b):e]\nq = s[a:(b if c else d)]\nr = s[::x if c else y]\np = -(a if b else c)\no = (a if b else c) + d\nn2 = (a if b else c), d\nm = a, (b if c else d)\nk2 = a ** (b if c else d)\nj = y if c else z, 1\n",
    ),
    (
        "lambda_contexts",
        "a = s[lambda: 1:2]\nb = {lambda: 1: 2}\nc = f(lambda x=lambda: 1: x)\nd = s[(lambda: 1):2]\ne = {(lambda: a): b}\nf2 = [lambda: x for x in y]\ng = (lambda: a, lambda: b)\nh = lambda: (yield)\ni = lambda a, b: (a, b)\nj = lambda a, b: a, b\nk = (lambda a: lambda b: a + b)(1)(2)\n",
    ),
    (
        "precedence_regressions",
        "x = (a or b) and c\ny = a or (b and c)\nz = (a and b) + 1\nw = (-a) ** 2\nv = -a ** 2\nu = a ** -b\nt = (a ** b) ** c\ns = a ** b ** c\nr = [x for x in y if x if x > 1]\nq = (a if b else c) + 1\np = -(-x)\no = a - -b\nn = a + (+b)\nm = not a and not (b or c)\nl = (a + b) * c\nk = a + b * c\nj = not (a == b)\ni = (not a) == b\nh = ~a & b\ng = (a | b) & c\nf2 = a << b >> c\ne = a & b | c ^ d\n",
    ),
]
