"""Emitter unit tests (SPEC §5, §10, §11, §4.1): modes, pretty flag, canonical literals, ``{}`` for
pass, ``}else{`` glue and ``}\\n`` newline rules, parenthesisation obligations, spacing."""

from __future__ import annotations

import ast

import pytest
from _util import PY, plain_dump

SRC_MODES = (
    '"""Mod."""\n'
    "class A:\n"
    '    """Cls."""\n'
    "    x: int = 0\n"
    "    y: int\n"
    "    def f(self, a: int = 1, *b: str, c: int, **k: float) -> int:\n"
    '        """Doc."""\n'
    "        z: int = a\n"
    "        w: int\n"
    "        return z\n"
)


# --------------------------------------------------------------------------- modes (§11)


def test_mode_full_is_default_and_keeps_everything(pydense_mod) -> None:
    want = '"""Mod."""\nclass A{\n"""Cls."""\nx:int=0\ny:int\ndef f(a:int=1,*b:str,c:int,**k:float)->int{\n"""Doc."""\nz:int=a\nw:int\nreturn z}}'
    assert pydense_mod.encode(SRC_MODES) == want
    assert pydense_mod.encode(SRC_MODES, mode="full") == want
    assert pydense_mod.encode(SRC_MODES, mode=pydense_mod.Mode.FULL) == want


def test_mode_nodoc_drops_only_docstrings(pydense_mod) -> None:
    want = "class A{\nx:int=0\ny:int\ndef f(a:int=1,*b:str,c:int,**k:float)->int{\nz:int=a\nw:int\nreturn z}}"
    assert pydense_mod.encode(SRC_MODES, mode="nodoc") == want
    assert pydense_mod.encode(SRC_MODES, mode=pydense_mod.Mode.NODOC) == want


def test_mode_stripped_drops_annotations_but_keeps_bare_ones(pydense_mod) -> None:
    want = "class A{\nx=0\ny:int\ndef f(a=1,*b,c,**k){\nz=a\nw:int\nreturn z}}"
    assert pydense_mod.encode(SRC_MODES, mode="stripped") == want
    assert pydense_mod.encode(SRC_MODES, mode=pydense_mod.Mode.STRIPPED) == want


def test_mode_enum(pydense_mod) -> None:
    Mode = pydense_mod.Mode
    assert issubclass(Mode, str)
    assert Mode("nodoc") is Mode.NODOC
    assert Mode.FULL == "full" and Mode.NODOC == "nodoc" and Mode.STRIPPED == "stripped"
    assert [m.value for m in Mode] == ["full", "nodoc", "stripped"]
    with pytest.raises(ValueError):
        pydense_mod.encode("x=1", mode="loose")


@pytest.mark.parametrize(
    "src,mode,want",
    [
        ('def f():\n    """only doc"""\n', "nodoc", "def f(){}"),
        ('def f():\n    """only doc"""\n', "full", 'def f(){\n"""only doc"""}'),
        ('class A:\n    """only doc"""\n', "nodoc", "class A{}"),
        ('"""only a module docstring"""\n', "nodoc", ""),
        ('"""only a module docstring"""\n', "full", '"""only a module docstring"""'),
        ('"""mod"""\nx = 1\n', "nodoc", "x=1"),
        ("def f():\n    x = 1\n    'late string'\n", "nodoc", "def f(){\nx=1\n'late string'}"),
        ("def f():\n    'a'\n    'b'\n", "nodoc", "def f(){\n'b'}"),
        ("def f():\n    b'not a docstring'\n", "nodoc", "def f(){\nb'not a docstring'}"),
        ("def f():\n    f'not a docstring'\n", "nodoc", "def f(){\nf'not a docstring'}"),
        ("async def f():\n    'doc'\n    await x\n", "nodoc", "async def f(){\nawait x}"),
        ("def f():\n    'doc'\n    pass\n", "nodoc", "def f(){}"),
        ("'module level str not first'\nx = 1\n'second'\n", "nodoc", "x=1\n'second'"),
        (
            "def f(x: int = 1, *a: str, k: int, **kw: float) -> None:\n    pass\n",
            "stripped",
            "def f(x=1,*a,k,**kw){}",
        ),
        ("x: int = 5\ny: int\nself.z: float = 1.0\n", "stripped", "x=5\ny:int\n.z=1."),
        ("(x): int = 1\n", "stripped", "x=1"),
        ("lam = lambda a, b=1: a\n", "stripped", "lam=lambda a,b=1:a"),
        (
            "class A:\n    x: int\n    y: 'str'\n    (w): int\n",
            "stripped",
            "class A{\nx:int\ny:'str'\n(w):int}",
        ),
    ],
)
def test_mode_cases(pydense_mod, src, mode, want) -> None:
    assert pydense_mod.encode(src, mode=mode) == want


@pytest.mark.skipif(PY < (3, 12), reason="PEP 695")
def test_stripped_keeps_type_params_and_aliases(pydense_mod) -> None:
    assert (
        pydense_mod.encode("def f[T](x: T) -> T:\n    return x\n", mode="stripped")
        == "def f[T](x){\nreturn x}"
    )
    assert pydense_mod.encode("type X = int\n", mode="stripped") == "type X=int"
    assert (
        pydense_mod.encode("class Box[T](Generic[T]):\n    item: T\n", mode="stripped")
        == "class Box[T](Generic[T]){\nitem:T}"
    )


def test_u_prefix_kind_is_kept(pydense_mod) -> None:
    assert pydense_mod.encode("x = u'uni'") == "x=u'uni'"
    assert (
        pydense_mod.encode("x = U'uni'") == "x='uni'"
    )  # CPython records kind only for lowercase u
    assert pydense_mod.parse("x=u'uni'").body[0].value.kind == "u"


# --------------------------------------------------------------------------- pretty flag


def test_pretty_adds_space_after_keyword_before_dot_or_quote(pydense_mod) -> None:
    assert (
        pydense_mod.encode("def f(self): return self.x", pretty=True) == "def f(self){\nreturn .x}"
    )
    assert pydense_mod.encode("def f(self): return self.x") == "def f(self){\nreturn.x}"
    assert pydense_mod.encode("def f(): return 'x'", pretty=True) == "def f(){\nreturn 'x'}"
    assert pydense_mod.encode("def f(): return 'x'") == "def f(){\nreturn'x'}"
    assert pydense_mod.encode("def f(): return f'x'", pretty=True) == "def f(){\nreturn f'x'}"
    assert pydense_mod.encode("def f(): return f'x'") == "def f(){\nreturn f'x'}"
    assert pydense_mod.encode("if self.count == 1: pass", pretty=True) == "if .count==1{}"
    assert pydense_mod.encode("if self.count == 1: pass") == "if.count==1{}"
    assert pydense_mod.encode("x = a in self.s", pretty=True) == "x=a in .s"


def test_pretty_does_not_change_other_spacing_or_ast(pydense_mod) -> None:
    src = "class A:\n    def f(self, x):\n        return self.a + x if self.b else 'no'\n"
    pretty = pydense_mod.encode(src, pretty=True)
    plain = pydense_mod.encode(src)
    assert pretty == "class A{\ndef f(x){\nreturn .b?.a+x:'no'}}"
    assert plain == "class A{\ndef f(x){\nreturn.b?.a+x:'no'}}"
    assert plain_dump(pydense_mod.parse(pretty)) == plain_dump(ast.parse(src))
    assert pydense_mod.encode("x = a + b", pretty=True) == "x=a+b"
    assert pydense_mod.encode("f(a, b)", pretty=True) == "f(a,b)"


# --------------------------------------------------------------------------- canonical literals (§10.3)


@pytest.mark.parametrize(
    "py,dpy",
    [
        ("1.0", "1."),
        ("0.5", ".5"),
        ("0.0", "0."),
        ("100.0", "100."),
        ("-0.5", "-.5"),
        ("-1.0", "-1."),
        ("-0.0", "-0."),
        ("1e-5", "1e-05"),
        ("1e-05", "1e-05"),
        ("1.5e+300", "1.5e+300"),
        ("1e16", "1e+16"),
        ("1e+16", "1e+16"),
        ("1e100", "1e+100"),
        ("1.5e10", "15000000000."),
        ("123456789.0", "123456789."),
        ("0.0001", ".0001"),
        ("1e-7", "1e-07"),
        ("0.1", ".1"),
        ("0.15", ".15"),
        ("10.5", "10.5"),
        ("5e-324", "5e-324"),
        ("1.7976931348623157e308", "1.7976931348623157e+308"),
        ("1e400", "1e309"),
        ("1e309", "1e309"),
        ("-1e400", "-1e309"),
        ("1_0.0_1", "10.01"),
        ("1.0e0", "1."),
        ("1j", "1j"),
        ("1.5j", "1.5j"),
        ("0.5j", "0.5j"),
        ("1e3j", "1000j"),
        ("0j", "0j"),
        ("1e400j", "1e309j"),
        ("1 + 2j", "1+2j"),
        ("0x1F", "31"),
        ("0o17", "15"),
        ("0b101", "5"),
        ("1_000_000", "1000000"),
        ("10 ** 100", "10**100"),
        ("12345678901234567890", "12345678901234567890"),
        ("None", "None"),
        ("True", "True"),
        ("...", "..."),
        ("Ellipsis", "Ellipsis"),
    ],
)
def test_canonical_number_literals(pydense_mod, py, dpy) -> None:
    assert pydense_mod.encode(f"x = {py}") == f"x={dpy}"


def test_inf_and_nan_constants_from_ast(pydense_mod) -> None:
    def mod(value):
        return ast.fix_missing_locations(
            ast.Module(body=[ast.Expr(ast.Constant(value))], type_ignores=[])
        )

    assert pydense_mod.encode(mod(float("inf"))) == "1e309"
    assert pydense_mod.encode(mod(float("-inf"))) == "-1e309"
    assert pydense_mod.encode(mod(float("nan"))) == "(1e309-1e309)"
    assert pydense_mod.encode(mod(complex(0, float("inf")))) == "1e309j"
    back = pydense_mod.parse("x=1e309")
    assert back.body[0].value.value == float("inf")


@pytest.mark.parametrize(
    "py,dpy",
    [
        ("'it\\'s'", '"it\'s"'),
        ('"say \\"hi\\""', "'say \"hi\"'"),
        ("'plain'", "'plain'"),
        ('"plain"', "'plain'"),
        ("'a' 'b'", "'ab'"),
        ("b'\\x00'", "b'\\x00'"),
        ("rb'raw'", "b'raw'"),
        ("r'\\d+'", "'\\\\d+'"),
        ("'line\\nbreak'", "'line\\nbreak'"),
        ("'''tri'''", "'tri'"),
        ("'''multi\nline'''", "'multi\\nline'"),
        ("'é漢字🎉'", "'é漢字🎉'"),
        ("''", "''"),
        ("'both \\' \"'", "'''both ' \"'''"),  # both quote kinds: triple-quoted instead of escaped
    ],
)
def test_canonical_string_literals(pydense_mod, py, dpy) -> None:
    assert pydense_mod.encode(f"x = {py}") == f"x={dpy}"
    # ast.unparse's quote choice is the contract, except for the one documented deviation:
    # a string holding both quote kinds is triple-quoted instead of escaped (SPEC 10.3).
    value = ast.literal_eval(py)
    if not (isinstance(value, str) and "'" in value and '"' in value):
        assert (
            pydense_mod.encode(f"x = {py}")
            == "x=" + ast.unparse(ast.parse(f"x = {py}")).split(" = ", 1)[1]
        )


def test_docstrings_use_triple_quotes_like_unparse(pydense_mod) -> None:
    src = 'def f():\n    """Doc with \'quotes\' and "dq".\n\n    More.\n    """\n    return 1\n'
    assert (
        pydense_mod.encode(src)
        == 'def f(){\n"""Doc with \'quotes\' and "dq".\n\n    More.\n    """\nreturn 1}'
    )
    multi = 'x = """\nmulti\nline\n"""\n'
    assert pydense_mod.encode(multi) == "x=" + ast.unparse(ast.parse(multi)).split("= ", 1)[1]


def test_fstring_canonical_forms(pydense_mod) -> None:
    assert pydense_mod.encode("x = f'{y=}'") == "x=f'y={y!r}'"
    assert pydense_mod.encode("x = f'{a = }'") == "x=f'a = {a!r}'"
    assert pydense_mod.encode("x = f'{v!r:>{w}.{p}f} {{lit}}'") == "x=f'{v!r:>{w}.{p}f} {{lit}}'"
    assert pydense_mod.encode("x = f'{self.x}'") == "x=f'{.x}'"
    assert pydense_mod.encode("x = f'{self.x!r:>{self.w}}'") == "x=f'{.x!r:>{.w}}'"
    assert pydense_mod.encode("x = f'{a if c else b}'") == "x=f'{(c?a:b)}'"
    assert pydense_mod.encode("x = f'{(lambda: 1)()}'") == "x=f'{(lambda:1)()}'"
    assert pydense_mod.encode("x = f'a' 'b' f'{c}'") == "x=f'ab{c}'"
    assert pydense_mod.encode("x = f'{d[\"k\"]}'") == "x=f\"{d['k']}\""


# --------------------------------------------------------------------------- {} for pass (§10.4)


@pytest.mark.parametrize(
    "py,dpy",
    [
        ("def f(): pass", "def f(){}"),
        ("class A: pass", "class A{}"),
        ("class A(): pass", "class A{}"),
        ("if x: pass", "if x{}"),
        ("if x: pass\nelse: pass", "if x{}else{}"),
        ("while x: pass", "while x{}"),
        ("for x in y: pass", "for x in y{}"),
        ("try: pass\nexcept: pass", "try{}except{}"),
        ("try: pass\nfinally: pass", "try{}finally{}"),
        ("with x: pass", "with x{}"),
        ("async def f(): pass", "async def f(){}"),
        ("match x:\n    case _: pass", "match x{\ncase _{}}"),
        ("while x:\n    pass\n    pass", "while x{\npass\npass}"),
        ("def f():\n    pass\n    return 1", "def f(){\npass\nreturn 1}"),
        ("def f(): ...", "def f(){\n...}"),
        ("class A: ...", "class A{\n...}"),
        ("if x: ...", "if x{\n...}"),
        ("pass", "pass"),
        ("if x: pass\npass", "if x{}\npass"),
    ],
)
def test_empty_block_for_pass(pydense_mod, py, dpy) -> None:
    assert pydense_mod.encode(py) == dpy


# --------------------------------------------------------------------------- layout: }else{ glue and }\n (§5.4)


@pytest.mark.parametrize(
    "py,dpy",
    [
        ("if a:\n    x = 1\nelse:\n    x = 2", "if a{\nx=1}else{\nx=2}"),
        (
            "if a:\n    x = 1\nelif b:\n    x = 2\nelse:\n    x = 3",
            "if a{\nx=1}elif b{\nx=2}else{\nx=3}",
        ),
        ("if a:\n    x = 1\ny = 2", "if a{\nx=1}\ny=2"),
        ("def f():\n    if x:\n        a()\ny = 1", "def f(){\nif x{\na()}}\ny=1"),
        (
            "try:\n    a()\nexcept E:\n    b()\nelse:\n    c()\nfinally:\n    d()",
            "try{\na()}except E{\nb()}else{\nc()}finally{\nd()}",
        ),
        (
            "try:\n    a()\nexcept E as e:\n    b()\nexcept F:\n    c()",
            "try{\na()}except E as e{\nb()}except F{\nc()}",
        ),
        ("for x in y:\n    a()\nelse:\n    b()", "for x in y{\na()}else{\nb()}"),
        ("while c:\n    a()\nelse:\n    b()", "while c{\na()}else{\nb()}"),
        (
            "match x:\n    case 1:\n        a()\n    case _:\n        b()",
            "match x{\ncase 1{\na()}\ncase _{\nb()}}",
        ),
        (
            "class A:\n    def f(self):\n        return 1\n    def g(self):\n        return 2",
            "class A{\ndef f(){\nreturn 1}\ndef g(){\nreturn 2}}",
        ),
        (
            "def f():\n    return 1\ndef g():\n    return 2",
            "def f(){\nreturn 1}\ndef g(){\nreturn 2}",
        ),
        ("if a:\n    pass\nelse:\n    if b:\n        pass\n    c()", "if a{}else{\nif b{}\nc()}"),
        ("if a:\n    pass\nelse:\n    if b:\n        pass", "if a{}elif b{}"),
        ("if a:\n    if b:\n        x()\nelse:\n    y()", "if a{\nif b{\nx()}}else{\ny()}"),
        ("x = 1\ny = 2\nz = 3", "x=1\ny=2\nz=3"),
        ("@a\n@b.c(1)\ndef f():\n    pass", "@a@b.c(1)def f(){}"),
        (
            "@dataclass(frozen=True)\nclass A:\n    x: int",
            "@dataclass(frozen=True)class A{\nx:int}",
        ),
        ("@property\ndef x(self):\n    return 1", "@property def x(self){\nreturn 1}"),
        ("@a[0]\ndef f():\n    pass", "@a[0]def f(){}"),
        ("@(a or b)\ndef f():\n    pass", "@(a or b)def f(){}"),
        ("@(a @ b)\ndef f():\n    pass", "@(a@b)def f(){}"),
        ("@lambda f: f\ndef f():\n    pass", "@(lambda f:f)def f(){}"),
        ("@a.b\nasync def f():\n    pass", "@a.b async def f(){}"),
        ("@a\nclass B:\n    pass", "@a class B{}"),
        ("import os\n\n\nx = 1  # comment\n", "import os\nx=1"),
    ],
)
def test_layout_rules(pydense_mod, py, dpy) -> None:
    out = pydense_mod.encode(py)
    assert out == dpy
    assert not out.endswith("\n")


def test_no_trailing_newline_and_no_blank_lines(pydense_mod) -> None:
    out = pydense_mod.encode("x = 1\n\n\ny = 2\n\n")
    assert out == "x=1\ny=2"
    assert pydense_mod.encode("") == ""
    assert pydense_mod.encode("# just a comment\n") == ""
    assert pydense_mod.encode("\n\n") == ""


# --------------------------------------------------------------------------- parenthesisation (§4.1)


@pytest.mark.parametrize(
    "py,dpy",
    [
        ("s[1:-1 if n > 2 else None]", "s[1:(n>2?-1:None)]"),
        ("s[(a if c else b):e]", "s[(c?a:b):e]"),
        ("s[a:(b if c else d)]", "s[a:(c?b:d)]"),
        ("s[a:b:(c if d else e)]", "s[a:b:(d?c:e)]"),
        ("s[a if c else b]", "s[c?a:b]"),
        ("s[a if c else b, 1]", "s[c?a:b,1]"),
        ("{(a if c else b): v}", "{(c?a:b):v}"),
        ("{k: (a if c else b)}", "{k:c?a:b}"),
        ("f'{a if c else b}'", "f'{(c?a:b)}'"),
        ("f'{(lambda: 1)}'", "f'{(lambda:1)}'"),
        ("(a if c else b) if d else e", "d?(c?a:b):e"),
        ("a if (b if c else d) else e", "(c?b:d)?a:e"),
        ("a if c else (d if e else f)", "c?a:e?d:f"),
        ("a if c else d if e else f", "c?a:e?d:f"),
        ("(lambda: 1) if c else (lambda: 2)", "c?(lambda:1):(lambda:2)"),
        ("lambda: a if c else b", "lambda:c?a:b"),
        ("(lambda: a) if b else c", "b?(lambda:a):c"),
        ("a[(lambda: 1):2]", "a[(lambda:1):2]"),
        ("a[lambda: 1]", "a[lambda:1]"),
        ("{(lambda: 1): 2}", "{(lambda:1):2}"),
        ("{k: lambda: 1}", "{k:lambda:1}"),
        ("f(lambda: 1, key=lambda x: x[1])", "f(lambda:1,key=lambda x:x[1])"),
        ("(a or b) and c", "(a or b)and c"),
        ("a or (b and c)", "a or b and c"),
        ("(a and b) + 1", "(a and b)+1"),
        ("a and (b and c)", "a and(b and c)"),
        ("(-a) ** 2", "(-a)**2"),
        ("-a ** 2", "-a**2"),
        ("a ** -b", "a**-b"),
        ("(a ** b) ** c", "(a**b)**c"),
        ("2 ** 3 ** 4", "2**3**4"),
        ("not a and not(b or c)", "not a and not(b or c)"),
        ("not (a == b)", "not a==b"),
        ("(not a) == b", "(not a)==b"),
        ("(a, b) == (c, d)", "(a,b)==(c,d)"),
        ("(a + b) * c", "(a+b)*c"),
        ("a + b * c", "a+b*c"),
        ("a - (b - c)", "a-(b-c)"),
        ("(a - b) - c", "a-b-c"),
        ("a - -b", "a--b"),
        ("a + (+b)", "a++b"),
        ("-(a + b)", "-(a+b)"),
        ("-(-x)", "--x"),
        ("~a & b", "~a&b"),
        ("(a | b) & c", "(a|b)&c"),
        ("a @ (b @ c)", "a@(b@c)"),
        ("(1).real", "(1).real"),
        ("1.0 .real", "(1.).real"),
        ("1.5.real", "(1.5).real"),
        ("'x'.upper()", "'x'.upper()"),
        ("[1].pop()", "[1].pop()"),
        ("{}.get(1)", "{}.get(1)"),
        ("(1,).count(1)", "(1,).count(1)"),
        ("(...).x", "....x"),
        ("(a if b else c).d", "(b?a:c).d"),
        ("(a if b else c)()", "(b?a:c)()"),
        ("(a if b else c)[d]", "(b?a:c)[d]"),
        ("-(a if b else c)", "-(b?a:c)"),
        ("(a if b else c) + d", "(b?a:c)+d"),
        ("(a if b else c), d", "(b?a:c),d"),
        ("a, (b if c else d)", "a,(c?b:d)"),
        ("(a := 1)", "(a:=1)"),
        ("f(x := 1)", "f(x:=1)"),
        ("print((x := 5))", "print(x:=5)"),
        ("[y := f(x), y ** 2]", "[y:=f(x),y**2]"),
        ("(yield)", "yield"),
        ("f((yield))", "f((yield))"),
        ("f((x for x in y), 1)", "f((x for x in y),1)"),
        ("f(x for x in y)", "f(x for x in y)"),
        ("sum(x * x for x in xs)", "sum(x*x for x in xs)"),
        ("(x for x in y)", "(x for x in y)"),
        ("[x for x in y if x if x > 1]", "[x for x in y if x if x>1]"),
        ("[x for x in (a if b else c)]", "[x for x in(b?a:c)]"),
        (
            "{k: v for k, v in d.items() if v is not None}",
            "{k:v for k,v in d.items()if v is not None}",
        ),
        ("x[1, 2]", "x[1,2]"),
        ("x[(1, 2)]", "x[1,2]"),
        ("x[1,]", "x[1,]"),
        ("x[()]", "x[()]"),
        ("(a, b)[0]", "(a,b)[0]"),
        ("f((a, b), c)", "f((a,b),c)"),
        ("print((a, b))", "print((a,b))"),
        ("x = a, b", "x=a,b"),
        ("x = (a, b)", "x=a,b"),
        ("x = *a, b", "x=*a,b"),
        ("x = a ** -b", "x=a**-b"),
        ("print(-x ** 2)", "print(-x**2)"),
        ("x = ()", "x=()"),
        ("x = (a,)", "x=a,"),
        ("x = [(), (1,)]", "x=[(),(1,)]"),
        ("for x in a, b: pass", "for x in a,b{}"),
        ("for x, in y: pass", "for x,in y{}"),
        ("for (a, b), c in d: pass", "for(a,b),c in d{}"),
        ("del (a, b)", "del(a,b)"),
        ("del a, b", "del a,b"),
        ("assert (x, y)", "assert(x,y)"),
        ("assert x, (a, b)", "assert x,(a,b)"),
        ("x = a == '' and b", "x=a==''and b"),
        ("x = 1.0 in y", "x=1. in y"),
        ("x = y in 0.5", "x=y in .5"),
        ("x = a if 1.0 else b", "x=1.?a:b"),
        ("x = 'a' if c else 'b'", "x=c?'a':'b'"),
        ("x = not self.x", "x=not.x"),
        ("x = -self.x in self.s", "x=-.x in.s"),
        ("x = a * -b", "x=a*-b"),
        ("x = a < -b", "x=a<-b"),
        ("x = a - -0.5", "x=a--.5"),
        ("x = 1.0 - 0.5 - -0.5", "x=1.-.5--.5"),
        ("x = a < b <= c != d == e > f >= g", "x=a<b<=c!=d==e>f>=g"),
        ("x = a in b not in c is d is not e", "x=a in b not in c is d is not e"),
        ("x = a @ b", "x=a@b"),
        ("x @= y", "x@=y"),
        ("x **= 2", "x**=2"),
        ("x //= 2", "x//=2"),
        ("x >>= 1", "x>>=1"),
        ("x: tuple[int, ...] = ()", "x:tuple[int,...]=()"),
        ("x: 'Forward' = None", "x:'Forward'=None"),
        ("x = a[1:2, ::3, ...]", "x=a[1:2,::3,...]"),
        ("x = a[:, None]", "x=a[:,None]"),
        ("x = a[::-1]", "x=a[::-1]"),
        ("x = a[:-1]", "x=a[:-1]"),
        ("print(*a, sep='')", "print(*a,sep='')"),
        ("f(*a, *b, **c, **d, k=1)", "f(*a,*b,**c,**d,k=1)"),
        ("f(a=1, *b)", "f(*b,a=1)"),
        ("f(**{'a': 1})", "f(**{'a':1})"),
        ("{**a, 'b': 1, **c}", "{**a,'b':1,**c}"),
        ("{*a, *b}", "{*a,*b}"),
        ("[*a, *b]", "[*a,*b]"),
        ("x = {}", "x={}"),
        ("x = set()", "x=set()"),
        ("x = {*()}", "x={*()}"),
        ("class A(B, metaclass=M, **kw): pass", "class A(B,metaclass=M,**kw){}"),
        ("class C(*bases): pass", "class C(*bases){}"),
        ("from .... import w", "from .... import w"),
        ("from ...a.b import c as d, e", "from ...a.b import c as d,e"),
        ("from a import (b, c,)", "from a import b,c"),
        ("import a.b.c as d, e", "import a.b.c as d,e"),
        ("global a, b", "global a,b"),
        ("raise E('x') from None", "raise E('x')from None"),
        ("raise", "raise"),
        ("return_ = lambda *, k: k", "return_=lambda *,k:k"),
        ("f = lambda a, b=1, /, c=2, *d, e, f=3, **g: 0", "f=lambda a,b=1,/,c=2,*d,e,f=3,**g:0"),
        ("f = lambda x=lambda: 1: x", "f=lambda x=lambda:1:x"),
        ("f = lambda: (yield)", "f=lambda:(yield)"),
        ("x = 'a' 'b'", "x='ab'"),
        ("with a as b, c as d: pass", "with a as b,c as d{}"),
        ("with (a as b, c as d): pass", "with a as b,c as d{}"),
        ("with a as (b, c): pass", "with a as(b,c){}"),
        ("with a as b[0], c as d.e: pass", "with a as b[0],c as d.e{}"),
        (
            "async def f():\n    async with a as b, c: pass",
            "async def f(){\nasync with a as b,c{}}",
        ),
        ("async def f():\n    return await (await x)", "async def f(){\nreturn await(await x)}"),
        ("async def f():\n    x = (await a) ** 2", "async def f(){\nx=await a**2}"),
        ("async def f():\n    x = await a ** 2", "async def f(){\nx=await a**2}"),
        ("async def f():\n    x = -await a", "async def f(){\nx=-await a}"),
        (
            "async def f():\n    x = [y async for y in z if await y]",
            "async def f(){\nx=[y async for y in z if await y]}",
        ),
        ("def g():\n    x = yield", "def g(){\nx=yield}"),
        ("def g():\n    x = yield a, b", "def g(){\nx=yield a,b}"),
        ("def g():\n    yield a, b", "def g(){\nyield a,b}"),
        ("def g():\n    yield *a, b", "def g(){\nyield *a,b}"),
        ("def g():\n    return *a, b", "def g(){\nreturn *a,b}"),
        ("def g():\n    return a, b", "def g(){\nreturn a,b}"),
        ("def g():\n    return (a, b)", "def g(){\nreturn a,b}"),
        ("def g():\n    return (yield)", "def g(){\nreturn(yield)}"),
        ("def g():\n    x = yield from other()", "def g(){\nx=yield from other()}"),
        ("def g():\n    return -1", "def g(){\nreturn -1}"),
        ("def g():\n    return not x", "def g(){\nreturn not x}"),
        ("def g():\n    return [x]", "def g(){\nreturn[x]}"),
        ("def g():\n    return {1}", "def g(){\nreturn {1}}"),
        ("def g():\n    return ...", "def g(){\nreturn...}"),
        ("def g():\n    return b'x'", "def g(){\nreturn b'x'}"),
        ("def g():\n    return .5", "def g(){\nreturn .5}"),
        ("def g():\n    return self.mean, vol", "def g(){\nreturn.mean,vol}"),
        ("def g():\n    yield ''.join(buf)", "def g(){\nyield''.join(buf)}"),
        ("if self.count == 1: pass", "if.count==1{}"),
        (
            "vol = math.sqrt(self.var) if self.count >= self.min_p else 0.0",
            "vol=.count>=.min_p?math.sqrt(.var):0.",
        ),
        (
            "self.var = (1.0 - self.alpha) * (self.var + self.alpha * delta ** 2)",
            ".var=(1.-.alpha)*(.var+.alpha*delta**2)",
        ),
        ("x = (foo()\n     .bar()\n     .baz())", "x=foo().bar().baz()"),
        ("x = 1 + \\\n    2", "x=1+2"),
        ("x = 1 .real", "x=(1).real"),
        (
            "match x:\n    case [a, *rest]: pass\n    case (a, b): pass",
            "match x{\ncase[a,*rest]{}\ncase[a,b]{}}",
        ),
        (
            "match x:\n    case 1 | 2 as z: pass\n    case Point(x=0) | None: pass",
            "match x{\ncase 1|2 as z{}\ncase Point(x=0)|None{}}",
        ),
        (
            "match x:\n    case -1: pass\n    case 1 + 2j: pass\n    case -1 - 2j: pass\n    case a.b: pass",
            "match x{\ncase -1{}\ncase 1+2j{}\ncase -1-2j{}\ncase a.b{}}",
        ),
        (
            "match x:\n    case {'k': v, **rest}: pass\n    case {}: pass",
            "match x{\ncase {'k':v,**rest}{}\ncase {}{}}",
        ),
        (
            "match x:\n    case [a] if a > 0: pass\n    case _: pass",
            "match x{\ncase[a]if a>0{}\ncase _{}}",
        ),
        (
            "match x:\n    case Point(1, 2, z=3): pass\n    case str(): pass",
            "match x{\ncase Point(1,2,z=3){}\ncase str(){}}",
        ),
    ],
)
def test_parenthesisation_and_spacing(pydense_mod, py, dpy) -> None:
    out = pydense_mod.encode(py)
    assert out == dpy
    assert plain_dump(pydense_mod.parse(out)) == plain_dump(ast.parse(py))


@pytest.mark.skipif(PY < (3, 11), reason="PEP 646 star subscripts")
def test_starred_subscript_without_trailing_comma(pydense_mod) -> None:
    assert pydense_mod.encode("a[*idx]") == "a[*idx]"
    assert pydense_mod.encode("a[*idx, 1]") == "a[*idx,1]"
    assert pydense_mod.encode("def f(*args: *Ts): pass") == "def f(*args:*Ts){}"


def test_elif_collapse_matches_unparse(pydense_mod) -> None:
    src = "if a:\n    pass\nelse:\n    if b:\n        pass\n    else:\n        if c:\n            pass\n"
    assert pydense_mod.encode(src) == "if a{}elif b{}elif c{}"


def test_encode_accepts_ast_module(pydense_mod) -> None:
    src = "class A:\n    def f(self, x):\n        return self.y + x\n"
    assert pydense_mod.encode(ast.parse(src)) == pydense_mod.encode(src)
    assert pydense_mod.encode(ast.parse(src), mode="nodoc") == pydense_mod.encode(src, mode="nodoc")


def test_encode_rejects_invalid_python(pydense_mod) -> None:
    with pytest.raises(SyntaxError):
        pydense_mod.encode("def f(:\n")


def test_decode_is_unparse_with_trailing_newline(pydense_mod) -> None:
    out = pydense_mod.decode("class A{\ndef f(x){\nreturn.y+x}}")
    assert out == "class A:\n\n    def f(self, x):\n        return self.y + x\n"
    assert pydense_mod.decode("x=1") == "x = 1\n"


def test_version_string(pydense_mod) -> None:
    assert pydense_mod.__version__ == "1.0.0"


def test_public_api_surface(pydense_mod) -> None:
    for name in (
        "encode",
        "parse",
        "decode",
        "compile",
        "check",
        "lint",
        "Mode",
        "Diagnostic",
        "PyDenseSyntaxError",
        "CHEATSHEET",
        "run",
        "format_compact_error",
        "__version__",
    ):
        assert hasattr(pydense_mod, name), name
    assert isinstance(pydense_mod.CHEATSHEET, str) and "PyDense" in pydense_mod.CHEATSHEET
