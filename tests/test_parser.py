"""Parser unit tests (SPEC §3–§6): block-vs-display, ternary colons, newline rules, soft keywords,
decorators, else attachment, colon habit, positions."""

from __future__ import annotations

import ast

import pytest
from _util import PY, plain_dump


def _same(pydense_mod, dpy: str, py: str) -> ast.Module:
    tree = pydense_mod.parse(dpy)
    assert isinstance(tree, ast.Module)
    got, want = plain_dump(tree), plain_dump(ast.parse(py))
    assert got == want, f"\ndpy ={dpy!r}\nback={ast.unparse(tree)!r}\nwant={py!r}"
    return tree


# --------------------------------------------------------------------------- §6.1 block vs display


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("if x in {1,2}{}", "if x in {1, 2}:\n    pass"),
        ("if x in {1,2}{a}", "if x in {1, 2}:\n    a"),
        ("if x=={1}{go()}", "if x == {1}:\n    go()"),
        ("if {1}{a}", "if {1}:\n    a"),
        ("while{}{a}", "while {}:\n    a"),
        ("for x in {1,2}{a}", "for x in {1, 2}:\n    a"),
        ("if {**d}{a}", "if {**d}:\n    a"),
        ("if f({1,2}) and [{3}]{a}", "if f({1, 2}) and [{3}]:\n    a"),
        ("if (lambda:{1:2})(){a}", "if (lambda: {1: 2})():\n    a"),
        ("if {x for x in y}{a}", "if {x for x in y}:\n    a"),
        ("if {x:1 for x in y}{a}", "if {x: 1 for x in y}:\n    a"),
        ("if x in {k:v for k,v in d}{a}", "if x in {k: v for k, v in d}:\n    a"),
        ("with {1:2} as d{a}", "with {1: 2} as d:\n    a"),
        ("match {1:2}{case _{a}}", "match {1: 2}:\n    case _:\n        a"),
        ("match x{case {'k':v}{a}}", "match x:\n    case {'k': v}:\n        a"),
        ("match x{case {}{a}}", "match x:\n    case {}:\n        a"),
        ("x={}[0]", "x = {}[0]"),
        ("x={}\n[0]", "x = {}\n[0]"),
        ("if c{a}[1]", "if c:\n    a\n[1]"),
        ("if c{{}}", "if c:\n    {}"),
        ("if c{{1,2}}", "if c:\n    {1, 2}"),
        ("if c{}", "if c:\n    pass"),
        ("{1,2}", "{1, 2}"),
        ("{}", "{}"),
        ("{a:1}", "{a: 1}"),
        ("{**a}\n{*a}", "{**a}\n{*a}"),
        ("if a{}else{{1:2}}", "if a:\n    pass\nelse:\n    {1: 2}"),
        ("def f()->dict{return {}}", "def f() -> dict:\n    return {}"),
        ("x={1:{2:{3:{}}}}", "x = {1: {2: {3: {}}}}"),
        ("x={a:{b for b in c}}", "x = {a: {b for b in c}}"),
        ("while x{x-=1}", "while x:\n    x -= 1"),
    ],
)
def test_block_vs_display(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


def test_empty_braces_are_pass_or_dict_by_position(pydense_mod) -> None:
    tree = _same(pydense_mod, "if c{}", "if c:\n    pass")
    assert isinstance(tree.body[0].body[0], ast.Pass)
    tree = _same(pydense_mod, "x={}", "x = {}")
    assert isinstance(tree.body[0].value, ast.Dict)
    tree = _same(pydense_mod, "def f(){}\nclass A{}", "def f():\n    pass\nclass A:\n    pass")
    assert isinstance(tree.body[0].body[0], ast.Pass) and isinstance(tree.body[1].body[0], ast.Pass)


# --------------------------------------------------------------------------- §6.3 / §6.4 ternary and lambda colons


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("x=a?b:c", "x = b if a else c"),
        ("x=a?b:c?d:e", "x = b if a else (d if c else e)"),
        ("x=a?(b?c:d):e", "x = (c if b else d) if a else e"),
        ("x=(a?b:c)?d:e", "x = d if (b if a else c) else e"),
        ("d={a?b:c:d}", "d = {(b if a else c): d}"),
        ("d={a?b:c}", "d = {b if a else c}"),
        ("d={k:a?b:c}", "d = {k: b if a else c}"),
        ("x=s[c?a:b]", "x = s[a if c else b]"),
        ("x=s[c?a:b:e]", "x = s[(a if c else b):e]"),
        ("x=s[c?a:b:]", "x = s[(a if c else b):]"),
        ("x=s[1:c?a:b]", "x = s[1:a if c else b]"),
        ("x=s[1:n>2?-1:None]", "x = s[1:-1 if n > 2 else None]"),
        ("x=s[(c?a:b):e]", "x = s[(a if c else b):e]"),
        ("x=s[a?b:c?d:e:f]", "x = s[(b if a else (d if c else e)):f]"),
        ("x=lambda y:c?a:b", "x = lambda y: a if c else b"),
        ("x=a?(lambda:b):c", "x = (lambda: b) if a else c"),
        ("x=a if c else b", "x = a if c else b"),
        ("x=c?(a if d else b):e", "x = (a if d else b) if c else e"),
        ("x=a?b:c if d else e", "x = b if a else (c if d else e)"),
        ("x=(y:=c?a:b)", "x = (y := a if c else b)"),
        ("x=a?b:c,d", "x = (b if a else c), d"),
        ("x=a?-b:-c", "x = -b if a else -c"),
        ("x=a?not b:not c", "x = (not b) if a else (not c)"),
        ("x=a and b?c:d", "x = c if (a and b) else d"),
        ("x=a?b:c and d", "x = b if a else (c and d)"),
        ("f(a?b:c,d=e?f:g)", "f(b if a else c, d=f if e else g)"),
        ("x:int=a?b:c", "x: int = b if a else c"),
        ("return_=[c?a:b for v in vs if v]", "return_ = [a if c else b for v in vs if v]"),
        ("x=s[lambda:a:b]", "x = s[(lambda: a):b]"),
        ("x=s[a:lambda:b]", "x = s[a:lambda: b]"),
        ("x={lambda:a:b}", "x = {(lambda: a): b}"),
        ("x=lambda:lambda:1", "x = lambda: lambda: 1"),
        ("x=lambda a,/,b=1,*c,d,**k:a", "x = lambda a, /, b=1, *c, d, **k: a"),
        ("x=f'{(c?a:b)}'", "x = f'{a if c else b}'"),
        ("x=f'{(c?a:b)!r:>10}'", "x = f'{(a if c else b)!r:>10}'"),
        ("x=f'{x:{(c?w:5)}}'", "x = f'{x:{w if c else 5}}'"),
    ],
)
def test_ternary_and_lambda_colons(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


# --------------------------------------------------------------------------- §6.6 newline rules


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("x=1\ny=2", "x = 1\ny = 2"),
        ("x=1\n\ny=2\n", "x = 1\ny = 2"),
        ("x=1\n.y=2", "x = 1\nself.y = 2"),
        ("f(x)\n.y=2", "f(x)\nself.y = 2"),
        (".count+=1\n.mean=value", "self.count += 1\nself.mean = value"),
        ("import time\n.last=1", "import time\nself.last = 1"),
        ("import a.b\n.c=1", "import a.b\nself.c = 1"),
        ("from a.b import c\n.d=1", "from a.b import c\nself.d = 1"),
        ("import a\n.b.c()", "import a\nself.b.c()"),
        ("x=a\n-b", "x = a\n-b"),
        ("x=a\n(b)", "x = a\n(b)"),
        ("x=a\n[0]", "x = a\n[0]"),
        ("x=a\n[1,2]", "x = a\n[1, 2]"),
        ("x=a\n(1,2)", "x = a\n(1, 2)"),
        ("x=f()\n.g()", "x = f()\nself.g()"),
        ("x=a\n+b", "x = a\n+b"),
        ("x=a\nnot b", "x = a\nnot b"),
        ("x=a\n*b,=c", "x = a\n*b, = c"),
        ("x=a\n{1,2}", "x = a\n{1, 2}"),
        ("x=a\n'doc'", "x = a\n'doc'"),
        ("return_=1\nx=1\nlambda:2", "return_ = 1\nx = 1\nlambda: 2"),
        ("def f(){return x\n.y=1}", "def f():\n    return x\n    self.y = 1"),
        ("def f(){return\n.y=1}", "def f():\n    return\n    self.y = 1"),
        ("def f(){raise\n.y=1}", "def f():\n    raise\n    self.y = 1"),
        ("def g(){yield\n.y=1}", "def g():\n    yield\n    self.y = 1"),
        ("del a\n.y=1", "del a\nself.y = 1"),
        ("global a\n.y=1", "global a\nself.y = 1"),
        ("assert a\n.y=1", "assert a\nself.y = 1"),
        ("x=(a\n+b)", "x = a + b"),
        ("x=[1,\n2]", "x = [1, 2]"),
        ("x={1:\n2}", "x = {1: 2}"),
        ("x=f(a,\nb)", "x = f(a, b)"),
        ("def f(a,\nb){}", "def f(a, b):\n    pass"),
        ("if x\n{a}", "if x:\n    a"),
        ("if x{a\n}", "if x:\n    a"),
        ("if x{a}\nelse{b}", "if x:\n    a\nelse:\n    b"),
        ("if x{a}\n\n\nelse{b}", "if x:\n    a\nelse:\n    b"),
        ("if c{a}\nelif d{b}\nelse{c}", "if c:\n    a\nelif d:\n    b\nelse:\n    c"),
        ("try{a}\nexcept E{b}\nfinally{c}", "try:\n    a\nexcept E:\n    b\nfinally:\n    c"),
        (
            "match x\n{case 1{a}\ncase 2{b}}",
            "match x:\n    case 1:\n        a\n    case 2:\n        b",
        ),
        ("@a\n@b\ndef f(){}", "@a\n@b\ndef f():\n    pass"),
        ("@a\n\n@b\n\ndef f(){}", "@a\n@b\ndef f():\n    pass"),
        ("x=1\\\n+2", "x = 1 + 2"),
        ("x=1;;y=2;", "x = 1\ny = 2"),
        ("x=1;\n;y=2", "x = 1\ny = 2"),
        ("if x{a=1\nb=2}", "if x:\n    a = 1\n    b = 2"),
        ("x=a  # comment\n.b=1", "x = a\nself.b = 1"),
        ("x=a\n\n.b=1", "x = a\nself.b = 1"),
        ("x=a.\nb", "x = a.b"),
        ("x=a\n.b", "x = a\nself.b"),
    ],
)
def test_newline_rules(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


def test_newline_statement_count(pydense_mod) -> None:
    assert len(pydense_mod.parse("x=1\n.y=2").body) == 2
    assert len(pydense_mod.parse("import time\n.last=1").body) == 2
    assert len(pydense_mod.parse("x=f()\n.g()").body) == 2
    assert len(pydense_mod.parse("x=(f()\n.g())").body) == 1


def test_binary_operator_never_continues_across_newline(pydense_mod) -> None:
    tree = pydense_mod.parse("x=a\n+b")
    assert isinstance(tree.body[0].value, ast.Name)
    assert isinstance(tree.body[1].value, ast.UnaryOp)


# --------------------------------------------------------------------------- §6.7 soft keywords


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("match=1", "match = 1"),
        ("match(x)", "match(x)"),
        ("match[0]=2", "match[0] = 2"),
        ("match.x=1", "match.x = 1"),
        ("match,y=1,2", "match, y = 1, 2"),
        ("match:int=1", "match: int = 1"),
        ("match+=1", "match += 1"),
        ("match(x).y", "match(x).y"),
        ("match-1", "match - 1"),
        ("match*2", "match * 2"),
        ("match?a:b", "a if match else b"),
        ("match", "match"),
        ("match;x=1", "match\nx = 1"),
        ("x=match", "x = match"),
        ("print(match,type,case)", "print(match, type, case)"),
        ("match x{case 1{a}}", "match x:\n    case 1:\n        a"),
        ("match(x){case _{}}", "match (x):\n    case _:\n        pass"),
        ("match(x).y{case _{}}", "match (x).y:\n    case _:\n        pass"),
        ("match -x{case _{}}", "match -x:\n    case _:\n        pass"),
        ("match *a,b{case _{}}", "match *a, b:\n    case _:\n        pass"),
        ("match [1,2]{case _{}}", "match [1, 2]:\n    case _:\n        pass"),
        ("match {1,2}{case _{}}", "match {1, 2}:\n    case _:\n        pass"),
        ("match (x,){case _{}}", "match (x,):\n    case _:\n        pass"),
        ("match x,y{case a,b{}}", "match x, y:\n    case a, b:\n        pass"),
        ("match not x{case _{}}", "match not x:\n    case _:\n        pass"),
        ("match lambda:1{case _{}}", "match lambda: 1:\n    case _:\n        pass"),
        ("match await x{case _{}}", "match await x:\n    case _:\n        pass"),
        ("match 'a'{case _{}}", "match 'a':\n    case _:\n        pass"),
        ("match ...{case _{}}", "match ...:\n    case _:\n        pass"),
        ("match .x{case _{}}", "match self.x:\n    case _:\n        pass"),
        ("match match{case case{}}", "match match:\n    case case:\n        pass"),
        ("match x{case 1{a}case 2{b}}", "match x:\n    case 1:\n        a\n    case 2:\n        b"),
        ("match x{case _{}}", "match x:\n    case _:\n        pass"),
        ("match y?x:z{case _{}}", "match x if y else z:\n    case _:\n        pass"),
        ("type=3", "type = 3"),
        ("type(x)", "type(x)"),
        ("type.x=1", "type.x = 1"),
        ("type[0]=1", "type[0] = 1"),
        ("x=type", "x = type"),
        ("case=4", "case = 4"),
        ("case(x)", "case(x)"),
        ("x.match.case.type=1", "x.match.case.type = 1"),
        (
            "class A{def match(){}\ndef case(){}\ndef type(){}}",
            "class A:\n    def match(self):\n        pass\n    def case(self):\n        pass\n    def type(self):\n        pass",
        ),
    ],
)
def test_soft_keywords(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


@pytest.mark.skipif(PY < (3, 12), reason="type statement")
@pytest.mark.parametrize(
    "dpy,py",
    [
        ("type X=int", "type X = int"),
        ("type X[T]=list[T]", "type X[T] = list[T]"),
        ("type X[T:int,*Ts,**P]=dict[T,P]", "type X[T: int, *Ts, **P] = dict[T, P]"),
        ("type X[T:(int,str)]=T", "type X[T: (int, str)] = T"),
        ("type X=int;type=3", "type X = int\ntype = 3"),
        ("def f[T](x:T)->T{return x}", "def f[T](x: T) -> T:\n    return x"),
        ("class A[T:int](B[T],metaclass=M){}", "class A[T: int](B[T], metaclass=M):\n    pass"),
    ],
)
def test_type_soft_keyword(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


@pytest.mark.skipif(PY < (3, 13), reason="PEP 696 defaults")
def test_type_param_defaults(pydense_mod) -> None:
    _same(
        pydense_mod,
        "type X[T=int]=T\ntype Y[*Ts=*tuple[int]]=tuple[*Ts]\ntype Z[**P=[int]]=P",
        "type X[T = int] = T\ntype Y[*Ts = *tuple[int]] = tuple[*Ts]\ntype Z[**P = [int]] = P",
    )
    _same(
        pydense_mod,
        "def f[T=int,*Ts=*tuple[int,...],**P=[int]](x:T)->T{return x}",
        "def f[T = int, *Ts = *tuple[int, ...], **P = [int]](x: T) -> T:\n    return x",
    )


# --------------------------------------------------------------------------- §6.8 decorators


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("@a@b def f(){}", "@a\n@b\ndef f():\n    pass"),
        ("@a@b\ndef f(){}", "@a\n@b\ndef f():\n    pass"),
        ("@a\n@b\ndef f(){}", "@a\n@b\ndef f():\n    pass"),
        (
            "@property@abstractmethod def x(){return 1}",
            "@property\n@abstractmethod\ndef x():\n    return 1",
        ),
        ("@(a@b)def f(){}", "@(a @ b)\ndef f():\n    pass"),
        ("@a[b@c]def f(){}", "@a[b @ c]\ndef f():\n    pass"),
        ("@a(b@c)def f(){}", "@a(b @ c)\ndef f():\n    pass"),
        ("@a.b(1)class C{}", "@a.b(1)\nclass C:\n    pass"),
        ("@(c?a:b)def f(){}", "@(a if c else b)\ndef f():\n    pass"),
        ("@(a or b)def f(){}", "@(a or b)\ndef f():\n    pass"),
        ("@(lambda f:f)def f(){}", "@(lambda f: f)\ndef f():\n    pass"),
        ("@property def x(){return 1}", "@property\ndef x():\n    return 1"),
        ("@a[0].b(1)(2)def f(){}", "@a[0].b(1)(2)\ndef f():\n    pass"),
        (
            "@app.route('/x',methods=['GET','POST'])def f(){}",
            "@app.route('/x', methods=['GET', 'POST'])\ndef f():\n    pass",
        ),
        ("@dataclass(frozen=True)class A{x:int}", "@dataclass(frozen=True)\nclass A:\n    x: int"),
        ("@a.b async def f(){}", "@a.b\nasync def f():\n    pass"),
        ("x=a@b", "x = a @ b"),
        ("x@=b", "x @= b"),
        ("x=a@b@c", "x = a @ b @ c"),
        (
            "class A{@property def x(){return.x}}",
            "class A:\n    @property\n    def x(self):\n        return self.x",
        ),
        ("@x[1:2]def f(){}", "@x[1:2]\ndef f():\n    pass"),
        ("@self.x def f(){}", "@self.x\ndef f():\n    pass"),
        ("@.x def f(){}", "@self.x\ndef f():\n    pass"),
    ],
)
def test_decorators(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


def test_decorator_non_chain_is_e004(pydense_mod) -> None:
    for text in (
        "@a or b def f(){}",
        "@a if c else b def f(){}",
        "@a@b or c def f(){}",
        "@not a def f(){}",
    ):
        with pytest.raises(pydense_mod.PyDenseSyntaxError) as info:
            pydense_mod.parse(text)
        assert info.value.code == "E004", text


# --------------------------------------------------------------------------- §6.9 else attachment


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("if a{if b{x}}else{y}", "if a:\n    if b:\n        x\nelse:\n    y"),
        ("if a{if b{x}else{y}}", "if a:\n    if b:\n        x\n    else:\n        y"),
        ("for x in y{if c{a}}else{b}", "for x in y:\n    if c:\n        a\nelse:\n    b"),
        (
            "while c{if d{a}else{b}}else{e}",
            "while c:\n    if d:\n        a\n    else:\n        b\nelse:\n    e",
        ),
        ("try{a}except E{b}else{c}", "try:\n    a\nexcept E:\n    b\nelse:\n    c"),
        (
            "try{if a{b}}except E{c}else{d}finally{e}",
            "try:\n    if a:\n        b\nexcept E:\n    c\nelse:\n    d\nfinally:\n    e",
        ),
        ("if a{x=1}elif b{x=2}else{x=3}", "if a:\n    x = 1\nelif b:\n    x = 2\nelse:\n    x = 3"),
        ("if a{}else{if c{}}", "if a:\n    pass\nelse:\n    if c:\n        pass"),
        ("if a{}else{if c{}\nx=1}", "if a:\n    pass\nelse:\n    if c:\n        pass\n    x = 1"),
        ("for x in y{}else{z()}", "for x in y:\n    pass\nelse:\n    z()"),
        ("while c{break}else{w()}", "while c:\n    break\nelse:\n    w()"),
    ],
)
def test_else_attachment(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


def test_double_else_is_error(pydense_mod) -> None:
    with pytest.raises(pydense_mod.PyDenseSyntaxError):
        pydense_mod.parse("if c{a}else{b}else{c}")
    with pytest.raises(pydense_mod.PyDenseSyntaxError):
        pydense_mod.parse("else{b}")
    with pytest.raises(pydense_mod.PyDenseSyntaxError):
        pydense_mod.parse("x=1\nelse{b}")


# --------------------------------------------------------------------------- colon habit


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("if x:{a()}", "if x:\n    a()"),
        ("if x:{a()}else:{b()}", "if x:\n    a()\nelse:\n    b()"),
        ("if x:{a}elif y:{b}else:{c}", "if x:\n    a\nelif y:\n    b\nelse:\n    c"),
        ("def f(a):{return a}", "def f(a):\n    return a"),
        ("def f(a)->int:{return a}", "def f(a) -> int:\n    return a"),
        ("class A:{x=1}", "class A:\n    x = 1"),
        ("class A(B):{}", "class A(B):\n    pass"),
        ("while x:{}", "while x:\n    pass"),
        ("for x in y:{}", "for x in y:\n    pass"),
        (
            "try:{}except E as e:{}else:{}finally:{}",
            "try:\n    pass\nexcept E as e:\n    pass\nelse:\n    pass\nfinally:\n    pass",
        ),
        ("with a as b:{}", "with a as b:\n    pass"),
        (
            "match x:{case 1:{}case _:{}}",
            "match x:\n    case 1:\n        pass\n    case _:\n        pass",
        ),
        ("if x: {a}", "if x:\n    a"),
        ("if x:\n{a}", "if x:\n    a"),
        ("x:int=1", "x: int = 1"),
        ("if (x):{a}", "if x:\n    a"),
    ],
)
def test_colon_habit(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


def test_colon_without_block_is_error(pydense_mod) -> None:
    for text in ("if x:a", "if c{a}:x", "def f():"):
        with pytest.raises(pydense_mod.PyDenseSyntaxError):
            pydense_mod.parse(text)


# --------------------------------------------------------------------------- separators / misc §6.11, §6.12


@pytest.mark.parametrize(
    "dpy,py",
    [
        ("x=1;y=2", "x = 1\ny = 2"),
        ("if c{a=1;b=2}", "if c:\n    a = 1\n    b = 2"),
        ("return_=1;if c{a};x=2", "return_ = 1\nif c:\n    a\nx = 2"),
        ("def f(){return.mean}", "def f():\n    return self.mean"),
        ("def f(){return'x'}", "def f():\n    return 'x'"),
        ("def f(){return-1}", "def f():\n    return -1"),
        ("def f(){return...}", "def f():\n    return ..."),
        ("def f(){return(1,2)}", "def f():\n    return (1, 2)"),
        ("def f(){return[1]}", "def f():\n    return [1]"),
        ("def f(){return{1}}", "def f():\n    return {1}"),
        ("x=a in.keys()", "x = a in self.keys()"),
        ("def g(){yield''.join(buf)}", "def g():\n    yield ''.join(buf)"),
        ("x=a==''and b", "x = a == '' and b"),
        ("with open(p)as f{a}", "with open(p) as f:\n    a"),
        ("x=a--b", "x = a - -b"),
        ("x=not.x", "x = not self.x"),
        ("x=1if y else 2", "x = 1 if y else 2"),
        ("x=1.if y else 2.", "x = 1. if y else 2."),
        ("x=(1).real", "x = (1).real"),
        ("x=(1.).real", "x = (1.).real"),
        ("x=1 .real", "x = 1 .real"),
        ("x=1.0.real", "x = 1.0.real"),
        ("x=.5.real", "x = .5.real"),
        ("x=a[.5:]", "x = a[.5:]"),
        ("x=a[...]", "x = a[...]"),
        ("x=...;y=....real", "x = ...\ny = ....real"),
        ("x=1_000+0x1F+0o17+0b101", "x = 1_000 + 0x1F + 0o17 + 0b101"),
        ("x=1e309", "x = 1e309"),
        ("x='''a\n;}{'''", "x = '''a\n;}{'''"),
        ("x=f'{.x}'", "x = f'{self.x}'"),
        ("x=f'{.x!r:>{.w}}'", "x = f'{self.x!r:>{self.w}}'"),
        ("class A{def!f(this){}}", "class A:\n    def f(this):\n        pass"),
        ("x=a!=b", "x = a != b"),
        ("x=a**-b", "x = a ** -b"),
        ("x=-a**2", "x = -a ** 2"),
        ("x=(-a)**2", "x = (-a) ** 2"),
        ("x=a<-b", "x = a < -b"),
        ("x=a>-b", "x = a > -b"),
        ("from . import x", "from . import x"),
        ("from .. import x,y", "from .. import x, y"),
        ("from ...a import b", "from ...a import b"),
        ("from ....a import b", "from ....a import b"),
        ("from .....a import b", "from .....a import b"),
        ("from a import (b,c,)", "from a import (b, c,)"),
        ("from a import *", "from a import *"),
        ("import a.b.c as d,e", "import a.b.c as d, e"),
        ("(x):int", "(x): int"),
        ("(x.y):int=1", "(x.y): int = 1"),
        ("x[0]:int", "x[0]: int"),
        ("a[1:2,::3,...]=v", "a[1:2, ::3, ...] = v"),
        ("x=a[b:=c]", "x = a[b := c]"),
        (
            "x=a[*b,c:d]" if PY >= (3, 11) else "x=a[b]",
            "x = a[*b, c:d]" if PY >= (3, 11) else "x = a[b]",
        ),
        ("f(a=1,*b)", "f(a=1, *b)"),
        ("f(**{'a':1})", "f(**{'a': 1})"),
        ("*a,=b", "*a, = b"),
        ("a,*b=c", "a, *b = c"),
        ("[a,b]=c", "[a, b] = c"),
        ("(a,b)=c", "(a, b) = c"),
        ("for x, in y{}", "for x, in y:\n    pass"),
        ("for (x,y),z in w{}", "for (x, y), z in w:\n    pass"),
        ("for *a,b in c{}", "for *a, b in c:\n    pass"),
        ("def g(){return 1,}", "def g():\n    return 1,"),
        ("def g(){return *a,b}", "def g():\n    return *a, b"),
        ("def g(){yield *a,b}", "def g():\n    yield *a, b"),
        (
            "def g(){x=yield;y=yield 1;z=yield 1,2;w=yield from q;return(yield)}",
            "def g():\n    x = yield\n    y = yield 1\n    z = yield 1, 2\n    w = yield from q\n    return (yield)",
        ),
        (
            "async def f(){await(yield);f((yield));print((yield x).y)}",
            "async def f():\n    await (yield)\n    f((yield))\n    print((yield x).y)",
        ),
        ("x=*a,*b", "x = *a, *b"),
        ("del a,b[0],c.d", "del a, b[0], c.d"),
        ("del(a,b)", "del (a, b)"),
        ("assert(x,y)", "assert (x, y)"),
        ("assert x,(a,b)", "assert x, (a, b)"),
        ("raise E('x')from None", "raise E('x') from None"),
        ("x={1,}", "x = {1,}"),
        ("x={1:2,}", "x = {1: 2,}"),
        ("x={{1}}", "x = {{1}}"),
        ("x=[{1,2},{3:4}]", "x = [{1, 2}, {3: 4}]"),
        ("x=a if.b else.c", "x = a if self.b else self.c"),
        ("x={.x}", "x = {self.x}"),
        ("x={.x:.y}", "x = {self.x: self.y}"),
        ("x={.5:.x}", "x = {.5: self.x}"),
        ("x=a[.x:]", "x = a[self.x:]"),
        ("x=a[:.x]", "x = a[:self.x]"),
        ("if.count==1{a}", "if self.count == 1:\n    a"),
        ("try{a}except E{b}not c", "try:\n    a\nexcept E:\n    b\nnot c"),
        ("try{a}finally{b}~x\n-x", "try:\n    a\nfinally:\n    b\n~x\n-x"),
    ],
)
def test_separators_and_adjacency(pydense_mod, dpy, py) -> None:
    _same(pydense_mod, dpy, py)


def test_missing_separator_is_e003(pydense_mod) -> None:
    for text in ("x=1 y=2", "if c{a=1 b=2}", "f(a) g(b)"):
        with pytest.raises(pydense_mod.PyDenseSyntaxError) as info:
            pydense_mod.parse(text)
        assert info.value.code == "E003", text


# --------------------------------------------------------------------------- positions and plumbing


def test_positions_are_filled_in(pydense_mod) -> None:
    tree = pydense_mod.parse("x=1\nif x{\ny=2}")
    assert tree.body[0].lineno == 1 and tree.body[0].col_offset == 0
    assert tree.body[1].lineno == 2
    inner = tree.body[1].body[0]
    assert inner.lineno == 3 and inner.col_offset == 0
    assert inner.value.lineno == 3 and inner.value.col_offset == 2
    compile(tree, "<dpy>", "exec")  # requires every node to carry positions


def test_parse_result_compiles_and_runs(pydense_mod) -> None:
    code = pydense_mod.compile("def f(a){return a*2}\nr=f(21)")
    env: dict = {}
    exec(code, env)
    assert env["r"] == 42


def test_parse_returns_module_with_type_ignores(pydense_mod) -> None:
    tree = pydense_mod.parse("x=1")
    assert isinstance(tree, ast.Module)
    assert tree.type_ignores == []


def test_empty_and_comment_only_input(pydense_mod) -> None:
    assert pydense_mod.parse("").body == []
    assert pydense_mod.parse("\n\n").body == []
    assert pydense_mod.parse("# c\n").body == []
    assert pydense_mod.parse(";;").body == []


def test_filename_propagates_to_errors(pydense_mod) -> None:
    with pytest.raises(pydense_mod.PyDenseSyntaxError) as info:
        pydense_mod.parse("x=1 y=2", filename="a.dpy")
    assert info.value.filename == "a.dpy"


def test_deep_nesting_and_long_expressions(pydense_mod) -> None:
    deep = "x=" + "(" * 60 + "1" + ")" * 60
    assert pydense_mod.parse(deep).body[0].value.value == 1
    many = "x=" + "+".join(f"a{i}" for i in range(300))
    pydense_mod.parse(many)
    nested = "".join(f"if a{i}{{\n" for i in range(40)) + "x=1" + "}" * 40
    tree = pydense_mod.parse(nested)
    assert isinstance(tree.body[0], ast.If)


def test_hang_probe_invalid_input_errors_quickly(pydense_mod) -> None:
    import time

    t0 = time.perf_counter()
    for text in ("x=a not b", "x=a b c d", "match x{case", "if x{" * 50, "f(" * 50):
        with pytest.raises(pydense_mod.PyDenseSyntaxError):
            pydense_mod.parse(text)
    assert time.perf_counter() - t0 < 10.0
