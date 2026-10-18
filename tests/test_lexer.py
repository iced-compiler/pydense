"""Lexer unit tests (SPEC §2): token kinds with line/col, PEP 701 f-strings, numbers, comments,
depth-0 NEWLINE, backslash continuation, Unicode names, stray-backslash error.

Token attribute names are not fixed by the API contract; ``_util.tok_*`` read them tolerantly."""

from __future__ import annotations

import pytest
from _util import (
    PY,
    has_newline_between,
    significant,
    tok_col,
    tok_fields,
    tok_line,
    tok_type,
    tok_value,
    tokens_of,
)


def _sig(text: str) -> list[tuple[str, str]]:
    return significant(tokens_of(text))


def _values(text: str) -> list[str]:
    return [v for _, v in _sig(text)]


def test_module_exports(pydense_mod) -> None:
    from pydense import lexer

    assert hasattr(lexer, "tokenize") and hasattr(lexer, "Token")


def test_simple_tokens_and_positions() -> None:
    toks = tokens_of("x=1")
    kinds = [tok_fields(t) for t in toks if tok_type(t) not in ("NEWLINE", "EOF", "ENDMARKER")]
    assert kinds == [("NAME", "x", 1, 0), ("OP", "=", 1, 1), ("NUMBER", "1", 1, 2)]


def test_last_token_is_eof() -> None:
    toks = tokens_of("x=1")
    assert tok_type(toks[-1]) in ("EOF", "ENDMARKER")
    assert tok_type(tokens_of("")[-1]) in ("EOF", "ENDMARKER")


def test_positions_across_lines() -> None:
    toks = tokens_of("x=1\ny=22\n  z=3")
    by_val = {
        tok_value(t): (tok_line(t), tok_col(t)) for t in toks if tok_type(t) in ("NAME", "NUMBER")
    }
    assert by_val["y"] == (2, 0)
    assert by_val["22"] == (2, 2)
    assert by_val["z"] == (3, 2)


def test_crlf_counts_as_one_newline() -> None:
    toks = tokens_of("x=1\r\ny=2")
    y = [t for t in toks if tok_value(t) == "y"][0]
    assert (tok_line(y), tok_col(y)) == (2, 0)
    assert has_newline_between(toks, "1", "y")


def test_newline_significant_at_depth_zero_only() -> None:
    assert has_newline_between(tokens_of("x=1\ny=2"), "1", "y")
    assert not has_newline_between(tokens_of("f(a,\nb)"), ",", "b")
    assert not has_newline_between(tokens_of("x=[1,\n2]"), ",", "2")
    assert not has_newline_between(tokens_of("x=f(a,\n  b,\n  c)"), "b", ",")
    assert not has_newline_between(tokens_of("x=(a\n+b)"), "a", "+")


def test_blank_lines_do_not_add_tokens() -> None:
    sig = _sig("x=1\n\n\n\ny=2")
    assert sig == [
        ("NAME", "x"),
        ("OP", "="),
        ("NUMBER", "1"),
        ("NAME", "y"),
        ("OP", "="),
        ("NUMBER", "2"),
    ]
    newlines = [t for t in tokens_of("x=1\n\n\n\ny=2") if tok_type(t) == "NEWLINE"]
    assert len(newlines) <= 2, (
        "blank lines collapse (at most one NEWLINE between statements plus one at EOF)"
    )


def test_backslash_newline_continuation() -> None:
    toks = tokens_of("x=1\\\n+2")
    assert _values("x=1\\\n+2") == ["x", "=", "1", "+", "2"]
    assert not has_newline_between(toks, "1", "+")
    plus = [t for t in toks if tok_value(t) == "+"][0]
    assert (tok_line(plus), tok_col(plus)) == (2, 0)


def test_comments_are_discarded_but_newline_kept() -> None:
    toks = tokens_of("x=1 # set x\ny=2")
    assert all(tok_type(t) != "COMMENT" for t in toks)
    assert "#" not in "".join(tok_value(t) for t in toks)
    assert _values("x=1 # set x\ny=2") == ["x", "=", "1", "y", "=", "2"]
    assert has_newline_between(toks, "1", "y")
    assert _values("x=1#c") == ["x", "=", "1"]
    assert _values("# only\n# comments\n") == []
    assert _values("x=a//b#c") == ["x", "=", "a", "//", "b"]
    assert _values("x='#'#'") == ["x", "=", "'#'"]


@pytest.mark.parametrize(
    "lit",
    [
        "0",
        "1",
        "1_000",
        "1_000_000",
        "0x1F",
        "0xff",
        "0o17",
        "0b101",
        "1j",
        "1.5J",
        ".5",
        ".5j",
        "1.",
        "1.e5",
        "1e-5",
        "1E5",
        "1_0.0_1",
        "1.5e+300",
        "123456789.0",
        "0.5",
        "1e309",
    ],
)
def test_number_literals_are_single_tokens(lit: str) -> None:
    sig = _sig(f"x={lit}")
    assert sig == [("NAME", "x"), ("OP", "="), ("NUMBER", lit)]


def test_float_followed_by_keyword() -> None:
    assert _sig("x=1.if y else z")[2:4] == [("NUMBER", "1."), ("NAME", "if")]
    assert _sig("x=1.in y")[2:4] == [("NUMBER", "1."), ("NAME", "in")]
    assert _sig("x=1.and y")[2:4] == [("NUMBER", "1."), ("NAME", "and")]
    assert _sig("x=1.j")[2] == ("NUMBER", "1.j")
    assert _sig("x=1.e5")[2] == ("NUMBER", "1.e5")
    assert _sig("x=1.,.5")[2:] == [("NUMBER", "1."), ("OP", ","), ("NUMBER", ".5")]
    assert _sig("x=1.-.5")[2:] == [("NUMBER", "1."), ("OP", "-"), ("NUMBER", ".5")]


def test_dot_disambiguation() -> None:
    assert _sig("x=.5")[2] == ("NUMBER", ".5")
    assert _sig("x=...")[2] == ("OP", "...")
    assert _sig("x=.y")[2:] == [("OP", "."), ("NAME", "y")]
    assert _sig("a.b") == [("NAME", "a"), ("OP", "."), ("NAME", "b")]
    assert _values("x=....real") == ["x", "=", "...", ".", "real"]
    assert _values("return.mean") == ["return", ".", "mean"]
    assert _values("del.x") == ["del", ".", "x"]
    assert _values("not.x") == ["not", ".", "x"]
    assert _values("a-.5") == ["a", "-", ".5"]
    assert _values("a-.x") == ["a", "-", ".", "x"]


@pytest.mark.parametrize(
    "op",
    [
        "**=",
        "//=",
        ">>=",
        "<<=",
        "->",
        "**",
        "//",
        "<<",
        ">>",
        "<=",
        ">=",
        "==",
        "!=",
        "+=",
        "-=",
        "*=",
        "/=",
        "%=",
        "&=",
        "|=",
        "^=",
        "@=",
        ":=",
        "+",
        "-",
        "*",
        "/",
        "%",
        "@",
        "&",
        "|",
        "^",
        "~",
        "<",
        ">",
        ",",
        ":",
        ";",
        "=",
        "?",
        "!",
    ],
)
def test_operators_longest_match(op: str) -> None:
    sig = _sig(f"a {op} b")
    assert sig[1] == ("OP", op), sig


def test_operator_runs_split_correctly() -> None:
    assert _values("a--b") == ["a", "-", "-", "b"]
    assert _values("a<--b") == ["a", "<", "-", "-", "b"]
    assert _values("a->b") == ["a", "->", "b"]
    assert _values("a!=b") == ["a", "!=", "b"]
    assert _values("def!f") == ["def", "!", "f"]
    assert _values("c?a:b") == ["c", "?", "a", ":", "b"]
    assert _values("x:=1") == ["x", ":=", "1"]
    assert _values("x:int=1") == ["x", ":", "int", "=", "1"]
    assert _values("a**-b") == ["a", "**", "-", "b"]
    assert _values("{}") == ["{", "}"]
    assert _values("[](){}") == ["[", "]", "(", ")", "{", "}"]


@pytest.mark.parametrize(
    "lit",
    [
        "'x'",
        '"x"',
        "'''x'''",
        '"""x"""',
        "b'x'",
        "rb'\\d'",
        "Rb'x'",
        "BR'y'",
        "u'x'",
        "f'{a}'",
        "F'{a}'",
        "rf'\\d{x}'",
        "fr'{x}'",
        "r'\\n'",
        "''",
        "f''",
        "'it\\'s'",
        '"say \\"hi\\""',
        "f'{x:{w}}'",
        "f'{{}}'",
        "f'{\"}\"}'",
        "f'{d[\"k\"]}'",
        "f\"{f'{x}'}\"",
        "f'{x!r:>10}'",
        "'\\\\'",
    ],
)
def test_string_literals_are_single_tokens(lit: str) -> None:
    sig = _sig(f"x={lit}")
    assert sig == [("NAME", "x"), ("OP", "="), ("STRING", lit)], sig


@pytest.mark.skipif(PY < (3, 12), reason="PEP 701")
@pytest.mark.parametrize(
    "lit",
    ['f"{d["k"]}"', "f'{d['k']}'", "f'{f'{x}'}'", "f'{x\n}'", "f'{\"\\n\"}'", 'f"{f"{f"{x}"}"}"'],
)
def test_pep701_nested_fstrings_are_single_tokens(lit: str) -> None:
    sig = _sig(f"x={lit}")
    assert sig == [("NAME", "x"), ("OP", "="), ("STRING", lit)], sig


def test_multiline_string_advances_line_number() -> None:
    toks = tokens_of("x='''a\nb\nc'''\ny=1")
    y = [t for t in toks if tok_value(t) == "y"][0]
    assert (tok_line(y), tok_col(y)) == (4, 0)
    assert has_newline_between(toks, "'''a\nb\nc'''", "y")


def test_implicit_concatenation_is_two_tokens() -> None:
    assert _sig("'a' 'b'") == [("STRING", "'a'"), ("STRING", "'b'")]
    assert _sig("f'{a}' 'b'") == [("STRING", "f'{a}'"), ("STRING", "'b'")]


def test_string_prefix_recognised_before_name() -> None:
    assert _sig("return'x'") == [("NAME", "return"), ("STRING", "'x'")]
    assert _sig("return b'x'") == [("NAME", "return"), ("STRING", "b'x'")]
    assert _sig("return f'{x}'") == [("NAME", "return"), ("STRING", "f'{x}'")]
    assert _sig("returnb'x'") == [("NAME", "returnb"), ("STRING", "'x'")]
    assert _sig("yield''.join(buf)")[:3] == [("NAME", "yield"), ("STRING", "''"), ("OP", ".")]
    assert _sig("==''and") == [("OP", "=="), ("STRING", "''"), ("NAME", "and")]


def test_keyword_identifier_adjacency() -> None:
    assert _values(")as f{") == [")", "as", "f", "{"]
    assert _values("in.keys()") == ["in", ".", "keys", "(", ")"]
    assert _values("x=1if 2else 3") == ["x", "=", "1", "if", "2", "else", "3"]
    assert _values("returnx") == ["returnx"]
    assert _values("if.count==1{") == ["if", ".", "count", "==", "1", "{"]


def test_unicode_identifiers() -> None:
    assert _sig("π=1") == [("NAME", "π"), ("OP", "="), ("NUMBER", "1")]
    assert _sig("変数=1")[0] == ("NAME", "変数")
    assert _sig("naïve(ß)") == [("NAME", "naïve"), ("OP", "("), ("NAME", "ß"), ("OP", ")")]
    assert _sig("Ωmega.mét")[0] == ("NAME", "Ωmega")
    sig = _sig("x='漢字'")
    assert sig[2] == ("STRING", "'漢字'")


def test_whitespace_is_insignificant() -> None:
    assert _sig("for i , x in enumerate ( xs ) { print ( i , x ) }") == _sig(
        "for i,x in enumerate(xs){print(i,x)}"
    )
    assert _sig("x\t=\t1") == _sig("x=1")
    assert _sig("x = 1 \f") == _sig("x=1")


def test_stray_backslash_is_e006(pydense_mod) -> None:
    for text, line in (("x=\\ 1", 1), ("a=b \\ c", 1), ("x=\\\n\\ 1", 2)):
        with pytest.raises(pydense_mod.PyDenseSyntaxError) as info:
            pydense_mod.parse(text)
        assert info.value.code == "E006", text
        assert info.value.lineno == line


def test_backslash_lambda_is_e008(pydense_mod) -> None:
    with pytest.raises(pydense_mod.PyDenseSyntaxError) as info:
        pydense_mod.parse("f=\\x:x")
    assert info.value.code == "E008"


def test_lexical_errors_raise_pydense_syntax_error(pydense_mod) -> None:
    for text in ("x='abc", 'x="""abc', "x=1.real", "x=$y", "x=1_", "x=0x", "x=09"):
        with pytest.raises(SyntaxError) as info:
            pydense_mod.parse(text)
        assert isinstance(info.value, pydense_mod.PyDenseSyntaxError), text
        assert info.value.lineno == 1, text


def test_token_positions_inside_blocks() -> None:
    toks = tokens_of("def f(a){\nreturn a}\n")
    ret = [t for t in toks if tok_value(t) == "return"][0]
    assert (tok_line(ret), tok_col(ret)) == (2, 0)
    close = [t for t in toks if tok_value(t) == "}"][0]
    assert (tok_line(close), tok_col(close)) == (2, 8)


def test_tokenize_accepts_empty_and_whitespace_only() -> None:
    assert _sig("") == []
    assert _sig("   \n\n  ") == []
