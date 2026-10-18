"""SPEC §7: the implicit receiver rule, both directions, for every row of the table."""

from __future__ import annotations

import ast

import pytest
from _util import PY, plain_dump

# (id, method source inside ``class A:`` (4-space indented), canonical dpy inside ``class A{``)
TABLE = [
    ("dropped", "def m(self, x):\n        pass", "def m(x){}"),
    ("dropped_init", "def __init__(self, a, b=1):\n        pass", "def __init__(a,b=1){}"),
    (
        "classmethod_dropped",
        "@classmethod\n    def c(cls, x):\n        pass",
        "@classmethod def c(x){}",
    ),
    (
        "staticmethod_plain",
        "@staticmethod\n    def s(x):\n        pass",
        "@staticmethod def s(x){}",
    ),
    ("new_cls_plain", "def __new__(cls, *a):\n        pass", "def __new__(cls,*a){}"),
    ("annotated_self", "def m(self: 'A', x):\n        pass", "def m(self:'A',x){}"),
    ("defaulted_self", "def m(self=None):\n        pass", "def m(self=None){}"),
    ("sole_posonly_self", "def m(self, /, x):\n        pass", "def m(self,/,x){}"),
    ("sole_posonly_self_only", "def m(self, /):\n        pass", "def m(self,/){}"),
    ("self_then_cls", "def m(self, cls):\n        pass", "def m(self,cls){}"),
    ("def_bang_this", "def m(this, x):\n        pass", "def!m(this,x){}"),
    ("def_bang_noargs", "def m():\n        pass", "def!m(){}"),
    ("def_bang_varargs", "def m(*args):\n        pass", "def!m(*args){}"),
    ("def_bang_kwonly", "def m(*, x):\n        pass", "def!m(*,x){}"),
    ("def_bang_kwargs", "def m(**kw):\n        pass", "def!m(**kw){}"),
    ("def_bang_kwonly_self", "def m(*, self):\n        pass", "def!m(*,self){}"),
    ("def_bang_x_then_self", "def m(x, self):\n        pass", "def!m(x,self){}"),
    (
        "classmethod_klass",
        "@classmethod\n    def c(klass):\n        pass",
        "@classmethod def!c(klass){}",
    ),
    (
        "classmethod_self_plain",
        "@classmethod\n    def c(self):\n        pass",
        "@classmethod def c(self){}",
    ),
    (
        "classmethod_cls_self_plain",
        "@classmethod\n    def c(cls, self):\n        pass",
        "@classmethod def c(cls,self){}",
    ),
    (
        "staticmethod_self_plain",
        "@staticmethod\n    def s(self):\n        pass",
        "@staticmethod def s(self){}",
    ),
    ("staticmethod_noargs", "@staticmethod\n    def s():\n        pass", "@staticmethod def s(){}"),
    ("posonly_group_dropped", "def m(self, x, /, y):\n        pass", "def m(x,/,y){}"),
    ("posonly_group_dropped_2", "def m(self, x, /):\n        pass", "def m(x,/){}"),
    (
        "init_subclass_plain",
        "def __init_subclass__(cls, **kw):\n        pass",
        "def __init_subclass__(cls,**kw){}",
    ),
    (
        "metaclass_call_plain",
        "def __call__(cls, *a, **kw):\n        pass",
        "def __call__(cls,*a,**kw){}",
    ),
    (
        "dotted_decorator_dropped",
        "@abc.abstractmethod\n    def m(self):\n        pass",
        "@abc.abstractmethod def m(){}",
    ),
    (
        "call_decorator_dropped",
        "@functools.cache\n    def m(self, x):\n        pass",
        "@functools.cache def m(x){}",
    ),
    ("property_dropped", "@property\n    def p(self):\n        pass", "@property def p(){}"),
    (
        "staticmethod_call_is_not_bare",
        "@staticmethod()\n    def m(self, x):\n        pass",
        "@staticmethod()def m(x){}",
    ),
    (
        "builtins_staticmethod_is_not_bare",
        "@builtins.staticmethod\n    def m(self, x):\n        pass",
        "@builtins.staticmethod def m(x){}",
    ),
    (
        "stacked_staticmethod_first",
        "@staticmethod\n    @cache\n    def s(x):\n        pass",
        "@staticmethod@cache def s(x){}",
    ),
    (
        "stacked_staticmethod_last",
        "@cache\n    @staticmethod\n    def s(x):\n        pass",
        "@cache@staticmethod def s(x){}",
    ),
    ("async_dropped", "async def am(self, x):\n        pass", "async def am(x){}"),
    ("async_def_bang", "async def am(x):\n        pass", "async def!am(x){}"),
    ("self_kw_default_dropped", "def m(self, *, cls=1):\n        pass", "def m(*,cls=1){}"),
    (
        "nested_def_not_method",
        "def m(self):\n        def inner(y):\n            pass",
        "def m(){\ndef inner(y){}}",
    ),
    (
        "nested_class_in_method",
        "def m(self):\n        class B:\n            def n(self):\n                pass",
        "def m(){\nclass B{\ndef n(){}}}",
    ),
    ("lambda_in_class_untouched", "f = lambda self: self.x", "f=lambda self:.x"),
    (
        "if_block_is_transparent",
        "if TYPE_CHECKING:\n        def m(self, x):\n            pass",
        "if TYPE_CHECKING{\ndef m(x){}}",
    ),
    (
        "try_block_is_transparent",
        "try:\n        def m(self):\n            pass\n    except E:\n        def m(this):\n            pass",
        "try{\ndef m(){}}except E{\ndef!m(this){}}",
    ),
    (
        "for_block_is_transparent",
        "for i in r:\n        def m(self):\n            pass",
        "for i in r{\ndef m(){}}",
    ),
    (
        "with_block_is_transparent",
        "with ctx():\n        def m(self):\n            pass",
        "with ctx(){\ndef m(){}}",
    ),
    (
        "match_block_is_transparent",
        "match x:\n        case 1:\n            def m(self):\n                pass",
        "match x{\ncase 1{\ndef m(){}}}",
    ),
]

GENERIC_ROWS = [
    ("generic_method_dropped", "def m[T](self, x: T) -> T:\n        pass", "def m[T](x:T)->T{}"),
    (
        "generic_init_dropped",
        "def __init__[T](self, x: T):\n        pass",
        "def __init__[T](x:T){}",
    ),
    ("generic_def_bang", "def m[T](x: T) -> T:\n        pass", "def!m[T](x:T)->T{}"),
]


def _params(rows):
    return [pytest.param(py, dpy, id=rid) for rid, py, dpy in rows]


def _py(body: str) -> str:
    return f"class A:\n    {body}\n"


def _dpy(body: str) -> str:
    return "class A{\n" + body + "}"


@pytest.mark.parametrize("py,dpy", _params(TABLE))
def test_python_to_dpy(py, dpy, pydense_mod) -> None:
    assert pydense_mod.encode(_py(py)) == _dpy(dpy)


@pytest.mark.parametrize("py,dpy", _params(TABLE))
def test_dpy_to_python(py, dpy, pydense_mod) -> None:
    assert plain_dump(pydense_mod.parse(_dpy(dpy))) == plain_dump(ast.parse(_py(py)))


@pytest.mark.skipif(PY < (3, 12), reason="PEP 695 generics")
@pytest.mark.parametrize("py,dpy", _params(GENERIC_ROWS))
def test_generic_methods_both_ways(py, dpy, pydense_mod) -> None:
    assert pydense_mod.encode(_py(py)) == _dpy(dpy)
    assert plain_dump(pydense_mod.parse(_dpy(dpy))) == plain_dump(ast.parse(_py(py)))


# --------------------------------------------------------------------------- parser-side forms

PARSER_ONLY = [
    ("explicit_self_accepted", "def m(self,x){}", "def m(self, x):\n        pass"),
    (
        "explicit_cls_accepted",
        "@classmethod def c(cls,x){}",
        "@classmethod\n    def c(cls, x):\n        pass",
    ),
    ("cls_first_without_decorator", "def m(cls,x){}", "def m(cls, x):\n        pass"),
    ("inject_self", "def m(x){}", "def m(self, x):\n        pass"),
    ("inject_self_empty", "def m(){}", "def m(self):\n        pass"),
    ("inject_self_varargs", "def m(*a){}", "def m(self, *a):\n        pass"),
    ("inject_self_kwonly", "def m(*,k){}", "def m(self, *, k):\n        pass"),
    ("inject_self_kwargs", "def m(**kw){}", "def m(self, **kw):\n        pass"),
    ("inject_joins_posonly", "def m(x,/,y){}", "def m(self, x, /, y):\n        pass"),
    ("inject_joins_posonly_only", "def m(x,/){}", "def m(self, x, /):\n        pass"),
    ("inject_cls", "@classmethod def c(x){}", "@classmethod\n    def c(cls, x):\n        pass"),
    ("inject_cls_empty", "@classmethod def c(){}", "@classmethod\n    def c(cls):\n        pass"),
    (
        "staticmethod_no_injection",
        "@staticmethod def s(x){}",
        "@staticmethod\n    def s(x):\n        pass",
    ),
    ("staticmethod_empty", "@staticmethod def s(){}", "@staticmethod\n    def s():\n        pass"),
    (
        "dotted_abstractmethod_injects",
        "@abc.abstractmethod def m(x){}",
        "@abc.abstractmethod\n    def m(self, x):\n        pass",
    ),
    (
        "staticmethod_call_injects",
        "@staticmethod()def m(x){}",
        "@staticmethod()\n    def m(self, x):\n        pass",
    ),
    ("def_bang_no_injection", "def!m(this,x){}", "def m(this, x):\n        pass"),
    ("def_bang_empty", "def!m(){}", "def m():\n        pass"),
    (
        "classmethod_def_bang",
        "@classmethod def!c(klass){}",
        "@classmethod\n    def c(klass):\n        pass",
    ),
    ("this_gets_self_injected", "def m(this,x){}", "def m(self, this, x):\n        pass"),
    (
        "nested_def_untouched",
        "def m(){def inner(y){}}",
        "def m(self):\n        def inner(y):\n            pass",
    ),
    ("lambda_untouched", "f=lambda self:.x", "f = lambda self: self.x"),
    ("lambda_no_self", "g=lambda x:x", "g = lambda x: x"),
    (
        "if_block_transparent",
        "if T{def m(x){}}",
        "if T:\n        def m(self, x):\n            pass",
    ),
    (
        "else_block_transparent",
        "if T{def m(x){}}else{def m(y){}}",
        "if T:\n        def m(self, x):\n            pass\n    else:\n        def m(self, y):\n            pass",
    ),
    (
        "with_block_transparent",
        "with c{def m(x){}}",
        "with c:\n        def m(self, x):\n            pass",
    ),
    (
        "class_in_method_injects_again",
        "def m(){class B{def n(x){}}}",
        "def m(self):\n        class B:\n            def n(self, x):\n                pass",
    ),
    ("annotated_self_kept", "def m(self:'A',x){}", "def m(self: 'A', x):\n        pass"),
    ("dot_x_in_default_is_self", "def m(x=.y){}", "def m(self, x=self.y):\n        pass"),
    ("async_inject", "async def am(x){}", "async def am(self, x):\n        pass"),
]


@pytest.mark.parametrize("dpy,py", [pytest.param(d, p, id=i) for i, d, p in PARSER_ONLY])
def test_parser_receiver_forms(dpy, py, pydense_mod) -> None:
    assert plain_dump(pydense_mod.parse(_dpy(dpy))) == plain_dump(ast.parse(_py(py)))


def test_module_level_def_is_not_a_method(pydense_mod) -> None:
    assert (
        pydense_mod.encode("def f(self, x):\n    return self.x + x\n")
        == "def f(self,x){\nreturn.x+x}"
    )
    assert plain_dump(pydense_mod.parse("def f(x){return.x}")) == plain_dump(
        ast.parse("def f(x):\n    return self.x")
    )
    assert plain_dump(pydense_mod.parse("def f(self,x){}")) == plain_dump(
        ast.parse("def f(self, x):\n    pass")
    )


def test_function_nested_in_method_is_not_a_method(pydense_mod) -> None:
    src = "class A:\n    def m(self):\n        def inner(self, y):\n            return self\n        return inner\n"
    assert (
        pydense_mod.encode(src)
        == "class A{\ndef m(){\ndef inner(self,y){\nreturn self}\nreturn inner}}"
    )


def test_dot_name_is_always_self(pydense_mod) -> None:
    for text, py in [
        ("x=.y", "x = self.y"),
        ("def f(){return .y}", "def f():\n    return self.y"),
        ("class A{x=.y}", "class A:\n    x = self.y"),
        ("f=lambda:.y", "f = lambda: self.y"),
        ("x=f'{.y}'", "x = f'{self.y}'"),
        ("match x{case .y{}}", "match x:\n    case self.y:\n        pass"),
    ]:
        assert plain_dump(pydense_mod.parse(text)) == plain_dump(ast.parse(py)), text


def test_self_attribute_always_emitted_as_dot(pydense_mod) -> None:
    assert pydense_mod.encode("x = self.y") == "x=.y"
    assert pydense_mod.encode("f = lambda self: self.x") == "f=lambda self:.x"
    assert (
        pydense_mod.encode("del self.x\nself.x += 1\nself.x: int = 1") == "del.x\n.x+=1\n.x:int=1"
    )
    assert pydense_mod.encode("print(self)") == "print(self)"
    assert pydense_mod.encode("x = self") == "x=self"
    assert pydense_mod.encode("x = self[0].y") == "x=self[0].y"
