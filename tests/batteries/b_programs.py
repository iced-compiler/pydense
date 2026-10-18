"""PyDense-B bijection battery: 54 small programs (Python side)."""

V311 = (3, 11)
V312 = (3, 12)
V313 = (3, 13)

SNIPPETS = [
    (
        "match",
        "match cmd:\n    case 'go':\n        run()\n    case [a, b] if a > b:\n        f(a)\n    case {'k': v, **rest}:\n        g(v)\n    case Point(x=0, y=0) | None:\n        pass\n    case (1 | 2) as z:\n        pass\n    case _:\n        pass\n",
    ),
    (
        "match_call_subject",
        "match (x):\n    case 1:\n        pass\nmatch(x)\nmatch = 3\nmatch.y = 2\nmatch[0] = 1\n",
    ),
    (
        "walrus",
        "if (n := len(a)) > 10:\n    print(n)\nwhile (chunk := f.read(10)):\n    pass\ny = [z for x in xs if (z := g(x))]\nprint((q := 1))\n",
    ),
    (
        "except_star",
        "try:\n    f()\nexcept* ValueError as e:\n    g(e)\nexcept* (TypeError, KeyError):\n    pass\n",
        V311,
    ),
    (
        "type_params",
        "def f[T: int, *Ts, **P](x: T) -> T:\n    return x\nclass A[T]:\n    pass\ntype X = list[int]\ntype Y[K] = dict[K, int]\n",
        V312,
    ),
    ("type_soft_kw", "type(x)\ntype = 3\nx = type\n"),
    (
        "global_nonlocal",
        "def f():\n    global a, b\n    def g():\n        nonlocal c\n        c = 1\n    c = 0\n",
    ),
    ("assert_del", "assert x, 'msg'\nassert y\ndel a[0], b.c, d\n"),
    (
        "decorators",
        "@a\n@b.c(1)\n@d[0].e\n@(f or g)\ndef h():\n    pass\n@dataclass(frozen=True)\nclass Q:\n    x: int\n    y: int = 0\n",
    ),
    (
        "async",
        "async def f():\n    await g()\n    async for x in y:\n        pass\n    async with a as b, c:\n        pass\n    return [x async for x in aiter() if await x]\n    z = await a + 1\n    w = await (a + 1)\n",
    ),
    (
        "yield",
        "def g():\n    yield\n    yield 1\n    yield 1, 2\n    x = yield\n    y = yield 2\n    yield from other()\n    z = yield from other()\n    f((yield 3))\n",
    ),
    (
        "raise_from",
        "try:\n    pass\nexcept E as e:\n    raise V('x') from e\nraise\nraise X from None\n",
    ),
    (
        "with_multi",
        "with a as b, c as d:\n    pass\nwith open(p) as (x, y):\n    pass\nwith lock:\n    pass\n",
    ),
    (
        "for_else_while_else_try_else",
        "for x in y:\n    pass\nelse:\n    z()\nwhile c:\n    break\nelse:\n    w()\ntry:\n    a()\nexcept E:\n    b()\nelse:\n    c()\nfinally:\n    d()\n",
    ),
    (
        "chained_cmp",
        "if 0 < x <= 10 != y is not None:\n    pass\nif a not in b and c is not d and e in f:\n    pass\n",
    ),
    (
        "posonly_kwonly",
        "def f(a, b, /, c, d=1, *, e, f=2, **k):\n    pass\ndef g(a, /):\n    pass\ndef h(*, a):\n    pass\ndef i(*args: int, **kw: str) -> None:\n    pass\n",
    ),
    (
        "fstrings",
        "x = f'{a} {b!r} {c:.2f} {d!s:>{w}} {{lit}} {self.x} {e[1:2]} {f(1, 2)}'\ny = f\"{'nested'} {x if c else y} {(lambda: 1)}\"\nz = f'''{a}\nmulti'''\nw = f'{d[\"k\"]}'\n",
    ),
    (
        "fstring_ternary_lambda_self",
        "class A:\n    def f(self):\n        return f'{self.x if self.c else self.y}:{self.z!r:>10}'\n",
    ),
    (
        "bytes_complex_ellipsis",
        "a = b'xyz'\nb = 1j\nc = 2.5j\nd = ...\ne = x[..., 1]\nf = rb'\\d'\ng = u'abc'\n",
    ),
    (
        "starred",
        "a, *b = c\n[*x, *y]\nf(*a, **k)\nprint(*a, sep='')\nfirst, *rest = [0, *vals, 9]\n{**a, 'k': 1, **b}\n",
    ),
    (
        "slices",
        "a[1:2]\na[::2]\na[1:]\na[:2]\na[:]\na[1:2:3]\na[1:2, 3]\na[x, y:z]\na[(1 if c else 2):3]\na[lambda: 1]\na[(lambda: 1):2]\na[*b]\n",
        V311,
    ),
    (
        "lambda_defaults",
        "f = lambda a, b=1, *c, d, e=2, **k: a + b\ng = lambda: 0\nh = lambda x=(1 if c else 2): x\ni = lambda *, k: k\nj = lambda a, /, b: a\n",
    ),
    (
        "prec1",
        "x = (a or b) and c\ny = a or (b and c)\nz = (a and b) + 1\nw = (-a) ** 2\nv = -a ** 2\nu = (a + b) * c\nt = a + b * c\ns = (a if b else c) if d else e\nr = a if b else (c if d else e)\nq = not (a == b)\np = (not a) == b\n",
    ),
    (
        "prec2",
        "x = [x for x in y if x if x > 1]\ny = (a, b) == (c, d)\nz = a < b == c\nw = 2 ** -1\nv = (2 ** 3) ** 4\nu = 2 ** 3 ** 4\nt = (yield)\n",
    ),
    ("nested_lambda", "def f(a):\n    return lambda b: a + b\n"),
    (
        "self_rules",
        "class A:\n    def __init__(self, x):\n        self.x = x\n    @staticmethod\n    def s(a, b):\n        return a + b\n    @classmethod\n    def c(cls, a):\n        return cls(a)\n    def __new__(cls, *a):\n        return super().__new__(cls)\n    def weird(this, x):\n        return this\n    def noargs():\n        pass\n    def annotated(self: 'A', x):\n        return x\n    def two(self, cls):\n        return cls\n    def inner(self):\n        def helper(a):\n            return self.x + a\n        return helper\n    class Inner:\n        def m(self):\n            return self\n    f = lambda self: self\n    def posonly(self, x, /, y):\n        pass\n    def posonly2(self, /, y):\n        pass\n    def defaulted(self=None):\n        pass\n",
    ),
    (
        "lexer_cases",
        "a = 1j\nb = '%d' % x\nx <<= 2\nx ^= 2\nx @= y\nx >>= 1\nx //= 2\nx **= 2\nc = (1).bit_length()\nd = ()\ne = (1,)\nfrom . import x\nfrom .. import y\nfrom .a.b import c as d, e\nimport a.b.c as d, e\ng = await_ + 1\nh = a not in b\ni = 0.5\nj = 1.0\nk = 1e-5\nl = 1_000\nm = 0xFF\nn = 'a' 'b'\no = x[1:].y\np = 1 .real\n",
    ),
    (
        "float_canon",
        "a = 0.0\nb = 1.0\nc = 10.5\nd = 0.15\ne = 1e100\nf = 1e-05\ng = -1.0\nh = 100.0\ni = 0.0001\nj = 123456789.0\n",
    ),
    (
        "ternary_contexts",
        "x = a if c else b\nd = {k: (v if c else w), (a if c else b): 1}\nf(a if c else b, k=a if c else b)\nreturn_ = [a if c else b for a in q]\ns = x[a if c else b]\nt = (a if c else b)[0]\nu = (a if c else b).x\nv = lambda: a if c else b\nw = a if (b if c else d) else e\n",
    ),
    (
        "dict_set_block_ambiguity",
        "if x in {1, 2}:\n    pass\nfor k in {}:\n    pass\nwhile {1}:\n    pass\nd = {}\ns = {1}\ne = {**d}\nif f({}):\n    pass\ndef f() -> dict:\n    return {}\n",
    ),
    (
        "pass_blocks",
        "class A:\n    pass\ndef f():\n    pass\nif x:\n    pass\nelse:\n    pass\ntry:\n    pass\nexcept:\n    pass\nwhile x:\n    pass\n    pass\n",
    ),
    (
        "docstrings",
        "'''module doc'''\nclass A:\n    '''class doc'''\n    def f(self):\n        '''fn doc'''\n        return 1\n    def g(self):\n        '''only doc'''\n",
    ),
    (
        "strings_quotes",
        "a = 'it\\'s'\nb = \"say \\\"hi\\\"\"\nc = '''tri'''\nd = 'line\\nbreak'\ne = r'\\d+'\nf = 'tab\\there'\ng = '\\\\u{0:04x}'.format(n)\n",
    ),
    ("annassign", "x: int\ny: int = 5\nz.a: int = 1\n(w): int = 2\nq: tuple = 1, 2\n"),
    (
        "tuples",
        "x = 1, 2\ny = (1, 2)\nz = ()\nfor a, b in c, d:\n    pass\nreturn_ = (a, b)\nprint((a, b))\nf((a, b), c)\nw = *a, b\nx[1, 2] = 3\ndel (a, b)\n",
    ),
    ("import_star_paren", "from a import *\nfrom b import (c, d as e)\n"),
    ("unary", "a = -b\nc = ~d\ne = +f\ng = not h\ni = - -j\nk = -(-l)\nm = a - -b\nn = a + +b\n"),
    (
        "comprehension_variants",
        "a = [x for x in y]\nb = {x for x in y}\nc = {k: v for k, v in y}\nd = (x for x in y)\ne = [x for x in y for z in x if z]\nf = sum(x for x in y)\ng = f(x for x in y)\nh = [(x, y) for x, y in z]\ni = [x for x in (1, 2)]\n",
    ),
    ("class_kwargs", "class A(B, metaclass=M, **kw):\n    pass\nclass C(*bases):\n    pass\n"),
    (
        "keyword_string_adjacency",
        "if x == '':\n    return 'a'\nelif y in 'abc' and z:\n    print('x', end='')\nreturn f'{x}'\n",
    ),
    (
        "deep_nesting",
        "def f():\n    for i in range(3):\n        if i:\n            while True:\n                try:\n                    with a:\n                        break\n                finally:\n                    pass\n        else:\n            continue\n",
    ),
    ("set_ops", "a = x | y\nb = x ^ y\nc = x & y\nd = x << 1 >> 2\ne = ~x | y & z ^ w\n"),
    (
        "pow_assoc",
        "a = 2 ** 3 ** 2\nb = (-2) ** 2\nc = -2 ** 2\nd = (a ** b) ** c\ne = a ** (b ** c)\nf = (await x) ** 2\n",
    ),
    (
        "long_cond",
        "if self.max_lines is None or len(lines) + 1 < self.max_lines or ((not chunks or (self.drop_whitespace and len(chunks) == 1 and (not chunks[0].strip()))) and cur_len <= width):\n    pass\n",
    ),
    (
        "global_stmt_in_class",
        "class A:\n    x = 1\n    y: int = 2\n    z: int\n    def f(self):\n        return self.x\n",
    ),
    (
        "walrus_in_comp_if_and_call",
        "ys = [y for x in xs if (y := f(x)) is not None]\nfoo(x := 1)\n",
    ),
    (
        "string_keyword_adjacency2",
        "x = 'a' if c else 'b'\ny = ['a', 'b']\nz = {'a': 'b'}\nw = f('a')('b')['c']\n",
    ),
    (
        "attribute_on_literals",
        "a = (1).real\nb = 1.5.real\nc = 'x'.upper()\nd = [1].pop()\ne = {}.get(1)\nf = (1,).count(1)\n",
    ),
    ("star_annotations", "def f(*args: *Ts):\n    pass\n", V311),
    (
        "nested_fstring_quotes",
        "x = f'{d[\"a\"]}'\ny = f\"{f'{z}'}\"\nw = f'{x!r}'\nv = f'{x:{y}}'\nu = f'{x:>{w}.{p}f}'\nt = f'{a}{b}'\ns = f'{{}}'\n",
    ),
    ("only_doc", "'''doc'''\n"),
    ("semicolon_tolerance", "x=1;y=2\n"),
]
