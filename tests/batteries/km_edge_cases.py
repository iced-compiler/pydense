"""Dense Python (keyword-minimal) edge-case battery, Python side (7 construct groups)."""

V311 = (3, 11)
V312 = (3, 12)
V313 = (3, 13)

SNIPPETS = [
    (
        "self_rules",
        '\nclass A(Base, metaclass=Meta):\n    x: int = 0\n    y: int\n    def __init__(self, a, b=1):\n        self.a = a\n    def plain(self):\n        return self\n    def no_params():\n        pass\n    def other_name(this, x):\n        return this.x\n    def self_then_cls(self, cls):\n        return cls\n    def __new__(cls, *args, **kw):\n        return super().__new__(cls)\n    def posonly(self, a, /, b, *, c=1, **kw):\n        return a\n    def annotated_self(self: "A", x: int) -> "A":\n        return self\n    def varargs_only(*args):\n        return args\n    @staticmethod\n    def s(x):\n        return x\n    @staticmethod\n    def s2():\n        return 1\n    @classmethod\n    def c(cls, x):\n        return cls(x)\n    @classmethod\n    def c2(klass):\n        return klass\n    @classmethod\n    def c3(self):\n        return self\n    @property\n    @abstractmethod\n    def p(self):\n        return self._p\n    @p.setter\n    def p(self, v):\n        self._p = v\n    async def am(self, x):\n        await x\n        async for i in self.aiter():\n            pass\n        async with self.lock as l, other() as (o1, o2):\n            pass\n    def nested(self, x):\n        def inner(y):\n            return self.a + y\n        lam = lambda z=1, *a, k, **kw: self.a + z\n        class Inner:\n            def m(self):\n                return self\n        return inner\n    if True:\n        def conditional(self):\n            return 1\n',
    ),
    (
        "statements",
        '\nimport os.path as osp, sys\nfrom . import sibling\nfrom ..pkg.mod import (a as b, c)\nfrom __future__ import annotations\nglobal g1, g2\ndef f():\n    nonlocal n\n    assert x > 0, "msg"\n    del a[0], b.c, d\n    raise ValueError("x") from exc\n    raise\n    return\n    return 1, 2\n    yield\n    yield 1, 2\n    yield from gen()\n    x = yield\n    y = yield from g\n    z = (yield)\n    print((yield x))\n    pass\n    a = b = c = 1, 2\n    a, *b = c\n    [p, q] = r\n    (x): int\n    x: int\n    x: int = 5\n    a[1:2, ::3, ...] = v\n    a[*idx] = 1\n    s += 1; s -= 1; s *= 1; s /= 1; s //= 1; s %= 1; s **= 1; s >>= 1; s <<= 1; s &= 1; s |= 1; s ^= 1; s @= m\n    type Alias[T: int, *Ts, **P] = dict[T, P]\n    if (n := len(a)) > 10:\n        pass\n    while chunk := f.read(10):\n        pass\n',
        V312,
    ),
    (
        "control_flow",
        "\nfor i in range(3):\n    if i == 0:\n        continue\n    elif i == 1:\n        break\n    elif i:\n        pass\n    else:\n        x = 1\nelse:\n    done = True\nwhile x:\n    x -= 1\nelse:\n    pass\ntry:\n    pass\nexcept (ValueError, TypeError) as e:\n    raise\nexcept KeyError:\n    pass\nexcept:\n    pass\nelse:\n    ok = True\nfinally:\n    cleanup()\ntry:\n    pass\nexcept* OSError as eg:\n    pass\nexcept* ValueError:\n    pass\ntry:\n    pass\nfinally:\n    pass\nwith open(p) as f, open(q) as g:\n    pass\nwith (open(p) as f, open(q)):\n    pass\nwith ctx:\n    pass\nfor x in a, b:\n    pass\nfor x, (y, z) in pairs:\n    pass\nfor x in {1, 2}:\n    pass\nif x in {1: 2}:\n    pass\nwhile {a for a in b}:\n    pass\nif {**d}:\n    pass\nif f({1, 2}) and [{3}]:\n    pass\nif (lambda: {1: 2})():\n    pass\n",
        V311,
    ),
    (
        "match",
        '\nmatch command.split():\n    case [action]:\n        pass\n    case [action, obj]:\n        pass\n    case Point(x=0, y=0) | Point(x=1):\n        pass\n    case {"x": x, "y": y, **rest}:\n        pass\n    case {"key": _}:\n        pass\n    case [Point(x=0, y=0), *others] if len(others) > 1:\n        pass\n    case str() as s:\n        pass\n    case 1 | 2 | -3 | 1 + 2j | -1 - 2j | 0.5 | "s" | b"b" | None | True | False:\n        pass\n    case Color.RED:\n        pass\n    case (a, b):\n        pass\n    case ():\n        pass\n    case (p):\n        pass\n    case _:\n        pass\nmatch = 1\nmatch(x)\nmatch[0] = 2\ntype = 3\ntype(x)\ncase = 4\n',
    ),
    (
        "expressions",
        "\nx = a if c else b\nx = a if c else (d if e else f)\nx = (a if c else b) if d else e\nx = {k: (a if c else b) for k in d}\nx = {(a if c else b): v}\nx = s[a if c else b]\nx = s[(a if c else b):e]\nx = s[a:(b if c else d)]\nx = (lambda: 1) if c else (lambda: 2)\nx = lambda: a if c else b\nx = lambda a, b=1, /, c=2, *d, e, f=3, **g: 0\nx = lambda *, k: k\nx = lambda *a: a\nf(lambda: 1, key=lambda x: x[1])\ny = not a and not (b or c)\ny = (a or b) and c\ny = a or (b and c)\ny = (a and b) + 1\ny = (-a) ** 2\ny = -a ** 2\ny = a ** -b\ny = 2 ** 3 ** 4\ny = (2 ** 3) ** 4\ny = -(a + b)\ny = ~a\ny = a < b <= c != d == e > f >= g\ny = a in b not in c is d is not e\ny = (yield)\ny = await z\ny = (await z) ** 2\ny = await z ** 2\ny = [x for x in y if x if x > 1]\ny = [x * 2 for x in it if x > 0 for z in x]\ny = [x async for x in aiter() if x]\ny = {x for x in y}\ny = {k: v for k, v in d.items() if v is not None and v >= m}\ny = (x for x in y)\nf(x for x in y)\nf(*a, *b, **c, **d, k=1)\nf(a)(b)[c].d\ny = a[1:2], a[::2], a[:], a[1:], a[:2], a[1:2:3], a[1, 2], a[1:2, 3], a[...], a[()], a[(1, 2)]\ny = (), (1,), (1, 2), [], [1], {}, {1}, {1: 2}, {**a, 'b': 1}, {*a, *b}, set()\ny = {*()}\ny = *a, b\ny = [*a, *b]\ny = 1j, 1.5j, 0x1F, 0o17, 0b101, 1_000_000, 1e-5, 1.5e10, 1E5, 0.5, 100.0, 0.0, -0.5, 1.0 .real if False else 2\ny = (1).real, (1.5).real, (1.0).real\ny = b\"bytes\\x00\", rb\"raw\", u\"uni\", \"a\" \"b\", 'q\"uo\"te', \"it's\", '''triple\nline''', 'esc\\n\\t\\\\'\ny = ...\ny = Ellipsis\ny = None, True, False\ny = f\"{x!r:>{w}.{p}f} {y=} {z = } {{lit}} {d['k']} {f'{nested}'} {a if c else b} {lambda_ or 1} {x:%Y-%m-%d} {(lambda: 1)()}\"\ny = f\"{x:{'>' if c else '<'}10}\"\ny = f'''multi\n{line}'''\ny = (self.a + self.b) * self.c\ny = self\ny = self.a.b.c().d[1]\ny = x.match.case.type\n",
    ),
    (
        "typing",
        '\nfrom typing import TypeVar, Generic\nT = TypeVar("T")\nclass Box[T](Generic[T]):\n    def __init__(self, item: T) -> None:\n        self.item: T = item\n    def get[U](self, default: U = None) -> T | U:\n        return self.item\ndef first[T: (int, str), *Ts, **P](xs: list[T], *args: *Ts, **kw: P.kwargs) -> T:\n    return xs[0]\ndef kwonly(a, *, b: int = 1, **kw: str) -> dict[str, "Forward"]:\n    return {}\ndef posonly(a, b=2, /, c=3, *d, e, f=6, **g) -> None: ...\nasync def agen() -> AsyncIterator[int]:\n    yield 1\n@decorator\n@decorator.with_args(1, k=2)\n@(a @ b)\n@functools.wraps(f)\nclass C:\n    """Doc."""\n    def __init__(self):\n        """Init doc."""\n        self.x = 1\n    def only_doc(self):\n        """Only a docstring."""\n    def ellipsis_body(self): ...\n',
        V312,
    ),
]
