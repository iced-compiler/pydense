"""Judge 1 adversarial bijection battery (Python side)."""

V311 = (3, 11)
V312 = (3, 12)
V313 = (3, 13)

SNIPPETS = [
    ("self_nonstd_name", "class A:\n    def f(this, x):\n        return this.x\n"),
    ("self_noargs_method", "class A:\n    def f():\n        return 1\n"),
    ("self_only_varargs", "class A:\n    def f(*args, **kw):\n        return args\n"),
    ("self_kwonly_self", "class A:\n    def f(*, self):\n        return self\n"),
    ("self_default", "class A:\n    def f(self=None):\n        return self\n"),
    ("self_annotated", "class A:\n    def f(self: 'A', x: int) -> 'A':\n        return self\n"),
    ("self_posonly", "class A:\n    def f(self, /, x):\n        return x\n"),
    ("self_posonly_only", "class A:\n    def f(self, /):\n        return 1\n"),
    ("self_then_cls", "class A:\n    def register(self, cls):\n        return cls\n"),
    ("self_then_self_kw", "class A:\n    def f(self, *, cls=1):\n        return cls\n"),
    (
        "cls_no_decorator",
        "class A:\n    def __new__(cls, *a):\n        return object.__new__(cls)\n    def __init_subclass__(cls, **kw):\n        pass\n",
    ),
    (
        "classmethod_dotted",
        "import abc\nclass A:\n    @abc.abstractmethod\n    def f(self):\n        pass\n    @classmethod\n    def g(cls):\n        pass\n    @staticmethod\n    def h(x):\n        pass\n    @builtins.staticmethod\n    def i(x):\n        pass\n",
    ),
    (
        "classmethod_wrong_name",
        "class A:\n    @classmethod\n    def g(klass, x):\n        return klass\n",
    ),
    (
        "staticmethod_self_named",
        "class A:\n    @staticmethod\n    def s(self):\n        return self\n",
    ),
    (
        "nested_def_in_method",
        "class A:\n    def m(self):\n        def inner(y):\n            return y\n        class B:\n            def n(self):\n                return 2\n        return inner\n",
    ),
    (
        "method_in_if",
        "class A:\n    if X:\n        def f(self):\n            return 1\n    else:\n        def f(self):\n            return 2\n    try:\n        def g(self):\n            pass\n    except E:\n        pass\n",
    ),
    ("lambda_self", "f = lambda self: self.x\nclass A:\n    g = lambda self: self.y\n"),
    ("module_self_fn", "def f(self, x):\n    return self.x + x\n"),
    (
        "property_setter",
        "class A:\n    @property\n    def x(self):\n        return self._x\n    @x.setter\n    def x(self, v):\n        self._x = v\n",
    ),
    (
        "decorated_init",
        "class A:\n    @functools.wraps(f)\n    def __init__(self, a):\n        self.a = a\n",
    ),
    ("init_no_self", "class A:\n    def __init__(this):\n        this.a = 1\n"),
    ("init_classless", "def __init__(self, a):\n    self.a = a\n"),
    ("matmul_decorator", "@(a @ b)\ndef f():\n    pass\n@a @ b\ndef g():\n    pass\n"),
    (
        "exotic_decorator",
        "@(f or g)\ndef h():\n    pass\n@x[0].y(1)(2)\ndef i():\n    pass\n@lambda f: f\ndef j():\n    pass\n",
    ),
    (
        "ternary_chain",
        "a = x if c else y if d else z\nb = (x if c else y) if d else z\nc2 = x if (c if d else e) else y\nd2 = (lambda: 1) if c else (lambda: 2)\n",
    ),
    (
        "ternary_in_slice",
        "a = s[x if c else y:z]\nb = s[(x if c else y):]\nc2 = s[::x if c else y]\nd = {(x if c else y): v}\ne = {k: (x if c else y)}\n",
    ),
    (
        "ternary_fstring",
        "a = f'{x if c else y}'\nb = f'{(x if c else y)!r:>10}'\nc2 = f'{x:{w if c else 5}}'\n",
    ),
    ("lambda_in_slice", "a = s[lambda: 1:2]\nb = {lambda: 1: 2}\nc2 = f(lambda x=lambda: 1: x)\n"),
    (
        "lambda_full",
        "f = lambda a, b=1, /, c=2, *d, e, f=3, **g: a\ng = lambda *, k: k\nh = lambda: (yield)\n",
    ),
    (
        "set_in_header",
        "if x in {1, 2}:\n    pass\nwhile {1}:\n    break\nfor x in {1, 2}:\n    pass\nwith {1}:\n    pass\nif {k: v for k, v in d}:\n    pass\nmatch {1: 2}:\n    case {1: x}:\n        pass\n",
    ),
    ("dict_stmt_start", "{1: 2}\n{1, 2}\n{}\n{**a}\n{*a}\n"),
    (
        "walrus_header",
        "if (n := len(a)) > 10:\n    pass\nwhile chunk := f.read(10):\n    pass\n[y := f(x), y**2]\nf(x := 1)\nprint((x := 5))\n",
    ),
    ("unary_stmt", "~x\n-x\nnot x\n+x\n"),
    ("not_after_try", "try:\n    pass\nexcept E:\n    pass\nnot x\n"),
    (
        "not_in_vs_bang",
        "a = not isinstance(x, int)\nb = not x != y\nc = not not x\nd = (not x) == y\ne = not (x == y)\n",
    ),
    (
        "precedence",
        "a = (a or b) and c\nb = (a and b) + 1\nc2 = (-a) ** 2\nd = -a ** 2\ne = a ** -b\nf2 = (a ** b) ** c\ng = a ** b ** c\nh = [x for x in y if x if x > 1]\ni = (a if b else c) + 1\nj = -(-x)\nk = a - -b\nl = a + (+b)\nm = (yield)\n",
    ),
    ("compare_chain", "a = 0 < x <= 10 != y is not None\nb = a not in b is not c in d\n"),
    (
        "yield_forms",
        "def g():\n    x = yield\n    y = yield 1\n    z = yield 1, 2\n    w = yield from other()\n    print((yield))\n    yield\n    return (yield 1)\n    await_ = 1\n",
    ),
    (
        "async_all",
        "async def f():\n    async with a as b, c:\n        pass\n    async for x in y:\n        pass\n    else:\n        pass\n    r = [x async for x in aiter() if await x]\n    s = {k: v async for k, v in z}\n    t = (await x for x in y)\n    return await (await x)\n    await x ** 2\n",
    ),
    (
        "with_forms",
        "with a as b, c as d:\n    pass\nwith (a as b, c as d):\n    pass\nwith (a, b):\n    pass\nwith a as (b, c):\n    pass\nwith a as b[0], c as d.e:\n    pass\nwith (yield):\n    pass\n",
    ),
    (
        "except_forms",
        "try:\n    pass\nexcept (A, B) as e:\n    pass\nexcept C:\n    pass\nexcept:\n    pass\nelse:\n    pass\nfinally:\n    pass\ntry:\n    pass\nexcept* OSError as eg:\n    pass\nexcept* (A, B):\n    pass\ntry:\n    pass\nfinally:\n    pass\n",
        V311,
    ),
    (
        "loops_else",
        "for x in a, b:\n    pass\nelse:\n    pass\nwhile x:\n    pass\nelse:\n    pass\nfor x, *y in z:\n    continue\nfor (a, b), c in z:\n    break\nfor x in *a, b:\n    pass\n",
    ),
    (
        "imports",
        "import a.b.c as d, e\nfrom . import x\nfrom .. import y as z\nfrom ...a.b import (c, d as e,)\nfrom m import *\nfrom .... import w\n",
    ),
    (
        "assign_forms",
        "a = b = c\na, b = c\n[a, b] = c\n(a, b), c = d\na, *b = c\n*a, b = c\nx: int\n(x): int\nx: int = 5\n(x): int = 5\nself.x: int = 5\na[0]: int = 1\nx += 1\nx **= 2\nx @= m\nx >>= 1\nx //= 2\n",
    ),
    (
        "del_global",
        "del a, b[0], c.d, (e), [f]\ndel (a, b)\ndef f():\n    global a, b\n    def g():\n        nonlocal a\n",
    ),
    (
        "assert_raise",
        "assert x\nassert x, 'm'\nassert (x, y)\nraise\nraise E\nraise E from None\nraise E('x') from e\n",
    ),
    (
        "match_all",
        "match cmd:\n    case [action]:\n        pass\n    case [first, *rest] if len(rest) > 1:\n        pass\n    case Point(x=0, y=0) | Point(x=1):\n        pass\n    case {'k': v, **rest}:\n        pass\n    case {}:\n        pass\n    case str() as s:\n        pass\n    case 1 | -2 | 1 + 2j | -1 - 2j | 's' 't' | None | True | b'x':\n        pass\n    case Color.RED | a.b.c:\n        pass\n    case (x, y):\n        pass\n    case (x):\n        pass\n    case (x,):\n        pass\n    case [*_]:\n        pass\n    case [a, [b, *c], {'d': e}]:\n        pass\n    case Cls(a, b, k=1) if a:\n        pass\n    case _:\n        pass\n",
    ),
    (
        "match_soft",
        "match = 1\nmatch(x)\nmatch[0] = 1\nmatch.y = 2\nmatch x, y:\n    case a, b:\n        pass\nmatch -x:\n    case _:\n        pass\ncase = type = 3\ntype(x)\ntype X = int\ntype Y[T: int, *Ts, **P] = dict[T, P]\ntype Z[T = int, *Ts = *tuple[int], **P = [int]] = T\n",
        V313,
    ),
    (
        "typeparams",
        "def f[T: (int, str), *Ts, **P](x: T, *a: *Ts) -> T:\n    pass\nclass A[T = int, *Ts = *tuple[int, ...], **P = [int]](Base, metaclass=M, **kw):\n    pass\n",
        V313,
    ),
    (
        "fstrings",
        "a = f'{x!r:>{w}.{p}f} {d[\"k\"]} {y=} {{lit}} {z = }'\nb = f\"{'a' 'b'}\"\nc2 = f'{f\"{x}\"}'\nd = f'''{\n x\n}'''\ne = rf'\\d{x}'\nf2 = f'{x:{\"a\"}>10}'\ng = f'{\"{\"}'\nh = f'{x!s}{y!a}'\ni = f'{(lambda: 1)}'\nj = f'{x:}'\nk = f'{x:%Y-%m-%d}'\nl = f''\nm = f'{3.14:.2f}'\nn = f'{a[1:2]}'\no2 = f'{ {1: 2}[1] }'\np2 = f\"{'\\n'}\"\n",
        V312,
    ),
    (
        "strings_bytes",
        "a = b'\\x00\\xff'\nb = rb'raw\\d'\nc2 = u'uni'\nd = 'a' 'b'\ne = '\\N{BULLET}\\u2022\\t\\\\'\nf2 = '''tri\nple'''\ng = \"it's\"\nh = 'say \"hi\"'\ni = 'both \\' \"'\nj = '\\0'\nk = 'é漢字🎉'\nl = b''\nm = ''\n",
    ),
    (
        "numbers",
        "a = 1j, 0x1F, 1_000_000, 1e-5, 0.5, 100.0, -0.5, 1.5e10, .5j, 1e5j, 0o17, 0b101, 1e400, 1_0.5_0\nb = (1).real, 1.0 .real, 1j.imag, (-1).bit_length(), 1e3.hex()\nc2 = 10 ** 400\nd = 0.1 + 0.2\ne = 1 .__add__(2)\nf2 = 2.5e-324\ng = 1.7976931348623157e308\n",
    ),
    (
        "calls_subs",
        "f(*a, *b, **c, k=1, **d)\nf(x for x in y)\nf((x for x in y), 1)\na[1:2], a[::2], a[1:2, 3], a[...], a[*idx], a[*idx, 1], a[()], a[(1,)], a[1,], a[(1, 2)]\na[b:c, d:e]\nf()()[0].x\n",
        V311,
    ),
    (
        "displays",
        "a = (), (1,), [], {}, {1}, {*()}, {**a, 'b': 1}, [*a, *b], (*a, b), {*a, *b}\nb = {k: v for k, v in d.items() if v is not None}\nc2 = [[x for x in y] for y in z]\nd = (x for x in y for z in x if z)\ne = {x async for x in y}\n",
    ),
    (
        "return_tuples",
        "def f():\n    return a, b\n    return *a, b\n    return (a, b)\n    return ()\n    return (a,)\n    return\n    return a if b else c\n    return lambda: 1\n    return not x\n    return -x\n    return .5\n    return 'x'\n    return f'x'\n    return b'x'\n    return [x]\n    return (yield)\n    return await x\n",
    ),
    (
        "pass_blocks",
        "def f():\n    pass\nclass A:\n    pass\nclass B:\n    pass\n    pass\ndef g():\n    'doc'\ndef h():\n    'doc'\n    pass\nif x:\n    pass\nelse:\n    pass\nfor x in y:\n    pass\nwhile x:\n    pass\ntry:\n    pass\nexcept:\n    pass\nwith x:\n    pass\nclass C:\n    x: int\nclass D:\n    ...\n",
    ),
    (
        "docstring_odd",
        'def f():\n    """doc"""\n    return 1\ndef g():\n    \'doc\' \'cat\'\ndef h():\n    b\'notdoc\'\ndef i():\n    f\'notdoc\'\nclass A:\n    """doc"""\n    x = 1\n\'module level str not first\'\n',
    ),
    ("module_docstring", '"""Module doc."""\nimport os\n'),
    (
        "unicode_names",
        "def naïve(ß): return ß\nπ = 3\nclass Ωmega:\n    def mét(self): return self.π\n",
    ),
    (
        "keyword_glue",
        "def f():\n    return'x'\n    return.5\n    if.5: pass\n    x = 1 if y else 2\n    return[1]\n    return{1}\n    return(1)\n",
    ),
    (
        "deeply_nested",
        "def f():\n    if a:\n        if b:\n            if c:\n                if d:\n                    return {1: {2: {3: {}}}}\n",
    ),
    (
        "elif_vs_nested",
        "if a:\n    pass\nelif b:\n    pass\nelse:\n    if c:\n        pass\nif a:\n    pass\nelse:\n    if c:\n        pass\n    x = 1\n",
    ),
    (
        "attr_on_literal",
        "a = (1).real\nb = 'x'.upper()\nc2 = [1].pop()\nd = {}.get(1)\ne = ....__class__\nf2 = (...).x\n",
    ),
    ("starred_target_misc", "for *a, b in c: pass\n[*a] = b\n(*a,) = b\n"),
    ("global_in_class", "class A:\n    global g\n    g = 1\n"),
    ("semicolon_py", "x = 1; y = 2\nif x: a = 1; b = 2\n"),
    (
        "class_bodies",
        "class A(B, C, metaclass=M):\n    x = 1\n    def f(self): pass\n    class Inner:\n        def g(self): pass\n    @dataclass\n    class D:\n        a: int\n        b: str = 'x'\n",
    ),
    ("ellipsis_body", "def f(): ...\nclass A: ...\nx = ...\n"),
    (
        "nested_fstring_quotes",
        "a = f'{x[\"k\"]}' if 0 else f\"{x['k']}\"\nb = f'{\"\\'\"}'\n",
        V312,
    ),
    ("await_in_fstring", "async def f():\n    return f'{await x}'\n"),
    ("lambda_default_ternary", "f = lambda x=1 if c else 2: x\n"),
    ("set_vs_dict_comp_header", "if {x for x in y}:\n    pass\nif {x: 1 for x in y}:\n    pass\n"),
    ("class_kw_only", "class A(metaclass=M): pass\nclass B(*bases): pass\nclass C(**kw): pass\n"),
    ("nonascii_strings_in_fstring", "a = f'漢{x}字'\n"),
    ("backslash_in_string", "a = 'back\\\\slash'\nb = r'\\n'\nc2 = '\\\\'\n"),
    ("percent_format", "a = '%d' % x\nb = '%s %s' % (a, b)\n"),
    ("conditional_import", "try:\n    import a\nexcept ImportError:\n    a = None\n"),
    ("decorator_class", "@dataclass(frozen=True)\n@total_ordering\nclass A:\n    x: int\n"),
    ("many_decorators", "@a\n@b.c\n@d(1)\n@e[0]\ndef f(): pass\n"),
    (
        "ann_complex",
        "x: tuple[int, ...] = ()\ny: 'Forward' = None\nz: list[dict[str, int]] | None\nw: Callable[[int], str]\n",
    ),
    ("star_annotation", "def f(*args: *Ts, **kw: int) -> None: pass\n", V311),
    (
        "if_exp_in_comp",
        "a = [x if x else y for x in z]\nb = [x for x in z if (x if y else z)]\nc2 = [x for x in (a if b else c)]\n",
    ),
    ("comp_in_header_if", "if [x for x in y if x]:\n    pass\n"),
    ("else_dict_start", "if a:\n    pass\nelse:\n    {1: 2}\n"),
    ("dict_after_block", "if a:\n    pass\n{1: 2}\n[1][0]\n"),
    ("tuple_subscript_stmt", "x = {}\n[0]\n"),
    ("chained_method_lines", "x = (foo()\n     .bar()\n     .baz())\n"),
    ("assert_tuple_paren", "assert (x), (y)\n"),
    ("negative_zero", "a = -0.0\nb = 0.0\nc2 = -0\nd = 0.\n"),
    ("complex_zero", "a = 0j\nb = -0j\nc2 = 1 - 0j\nd = complex(1, 2)\n"),
    (
        "float_repr_edge",
        "a = 1e16\nb = 1e+16\nc2 = 12345678901234567890.0\nd = 0.1\ne = 1e-7\nf2 = 123456789.123456789\ng = 5e-324\nh = 1.0e0\n",
    ),
    ("big_decorator_args", "@app.route('/x', methods=['GET', 'POST'])\ndef f(): pass\n"),
    ("walrus_in_comp", "a = [y for x in z if (y := f(x))]\n"),
    ("lambda_body_tuple", "f = lambda: (1, 2)\ng = lambda x: x,\n"),
    (
        "slice_all",
        "a[:]\na[::]\na[1:]\na[:1]\na[::1]\na[1::]\na[:1:]\na[1:2:3]\na[:, :]\na[1, :]\na[..., 1]\n",
    ),
    ("print_chevron_legacy", "print(a, file=sys.stderr, end='')\n"),
    (
        "method_named_keywordish",
        "class A:\n    def match(self): pass\n    def case(self): pass\n    def type(self): pass\n    def print(self): pass\n",
    ),
    ("attr_named_softkw", "x.match.case.type = 1\nmatch.case = 2\n"),
    ("self_attr_in_default", "class A:\n    def f(self, x=self.y): pass\n"),
    ("self_in_class_body", "class A:\n    self = 1\n    x = self\n"),
    (
        "cls_as_regular_param",
        "def f(cls): return cls\nclass A:\n    def g(self, cls): return cls\n    def h(cls): return cls\n",
    ),
]
