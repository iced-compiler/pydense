"""Lenient-input battery (SPEC §17.6 plus the panel's hand-written dialect texts).

Each item is ``(name, dpy_text, python_reference)``: the .dpy text must parse and its AST must equal
``ast.parse(python_reference)``.  Items needing a newer interpreter carry a 4th element ``(3, 12)``.
"""

V311 = (3, 11)
V312 = (3, 12)
V313 = (3, 13)

SNIPPETS = [
    # ---------------------------------------------------------------- SPEC §17.6 list
    ("python_ternary", "y=a if c else b", "y = a if c else b"),
    ("python_ternary_spaced", "y = c ? a : b", "y = a if c else b"),
    ("python_ternary_nested", "y=a if c else d if e else f", "y = a if c else (d if e else f)"),
    (
        "lambda_keyword",
        "f=lambda x,y=2:x+y\ng=lambda:0\nh=lambda *a,**k:(a,k)",
        "f = lambda x, y=2: x + y\ng = lambda: 0\nh = lambda *a, **k: (a, k)",
    ),
    (
        "explicit_self",
        "class A{def f(self,x){self.x=x\nreturn self.x}}",
        "class A:\n    def f(self, x):\n        self.x = x\n        return self.x",
    ),
    (
        "explicit_self_mixed_dot",
        "class A{def f(self, x){return .y + x}}",
        "class A:\n    def f(self, x):\n        return self.y + x",
    ),
    (
        "explicit_cls",
        "class A{@classmethod def make(cls,x){return cls(x)}}",
        "class A:\n    @classmethod\n    def make(cls, x):\n        return cls(x)",
    ),
    (
        "self_dot_x_long_form",
        "class A{def f(){self.x=1\n.y=2}}",
        "class A:\n    def f(self):\n        self.x = 1\n        self.y = 2",
    ),
    (
        "float_long_spellings",
        "x=1.0+0.5\ny=0.0\nz=100.0\nw=1.0e5\nv=1.e5\nu=.5e-3",
        "x = 1.0 + 0.5\ny = 0.0\nz = 100.0\nw = 1.0e5\nv = 1.e5\nu = .5e-3",
    ),
    (
        "pass_in_braces",
        "def f(){pass}\nclass A{pass}\nif x{pass}else{}",
        "def f():\n    pass\nclass A:\n    pass\nif x:\n    pass\nelse:\n    pass",
    ),
    ("semicolon_after_close_brace", "if a{x=1};y=2", "if a:\n    x = 1\ny = 2"),
    ("semicolon_before_close_brace", "if a{x=1;}", "if a:\n    x = 1"),
    ("semicolons_everywhere", "x=1;;y=2;\nif x{y=3;}", "x = 1\ny = 2\nif x:\n    y = 3"),
    ("trailing_semicolons_mixed", "if a{x=1;};y=2", "if a:\n    x = 1\ny = 2"),
    ("colon_habit_if", "if x:{a()}", "if x:\n    a()"),
    (
        "colon_habit_else_elif",
        "if a{x=1}elif b:{x=2}else:{x=3}",
        "if a:\n    x = 1\nelif b:\n    x = 2\nelse:\n    x = 3",
    ),
    ("colon_habit_def", "def f(a):{return a}", "def f(a):\n    return a"),
    (
        "colon_habit_all_headers",
        "while x:{}\nfor x in y:{}\ntry:{}except E:{}finally:{}\nclass A:{}\nwith a:{}\nmatch x:{case 1:{}}",
        "while x:\n    pass\nfor x in y:\n    pass\ntry:\n    pass\nexcept E:\n    pass\nfinally:\n    pass\nclass A:\n    pass\nwith a:\n    pass\nmatch x:\n    case 1:\n        pass",
    ),
    ("colon_habit_def_arrow", "def f(a)->int:{return a}", "def f(a) -> int:\n    return a"),
    (
        "newline_before_open_brace",
        "def f(a, b)\n{\n  x = a + b\n  if x > 1 {\n    return x\n  }\n  else {\n    return 0\n  }\n}\n",
        "def f(a, b):\n    x = a + b\n    if x > 1:\n        return x\n    else:\n        return 0",
    ),
    ("newline_before_close_brace", "if x{\n  a=1\n  b=2\n}\n", "if x:\n    a = 1\n    b = 2"),
    ("newline_before_else", "if c{a}\nelse{b}", "if c:\n    a\nelse:\n    b"),
    (
        "newline_before_elif_else_blank_lines",
        "if c{a}\n\nelif d{b}\n\n\nelse{c}",
        "if c:\n    a\nelif d:\n    b\nelse:\n    c",
    ),
    (
        "newline_before_except_finally",
        "try{a}\nexcept E{b}\nfinally{c}",
        "try:\n    a\nexcept E:\n    b\nfinally:\n    c",
    ),
    (
        "newline_before_case",
        "match x\n{\ncase 1{a}\n\ncase 2{b}\n}",
        "match x:\n    case 1:\n        a\n    case 2:\n        b",
    ),
    (
        "pretty_printed_indented",
        "def f(a){\n    if a{\n        return 1\n    }\n    return 2\n}",
        "def f(a):\n    if a:\n        return 1\n    return 2",
    ),
    ("comments", "x = 1  # set x\n# full line\ny = 2", "x = 1\ny = 2"),
    (
        "comment_inside_block_and_braces",
        "if x{ # open\n a=1 # one\n # alone\n}\n# done",
        "if x:\n    a = 1",
    ),
    ("comment_with_special_chars", "x=1 # { } ; : ? \\ \" '\ny=2", "x = 1\ny = 2"),
    ("hash_in_string_not_comment", "x='#'#'\ny=a//b#c", "x = '#'\ny = a // b"),
    ("backslash_continuation", "x=1\\\n+2\ny=a\\\n  +b", "x = 1 + 2\ny = a + b"),
    ("backslash_continuation_in_header", "if a and \\\n b{c}", "if a and b:\n    c"),
    ("decorators_on_own_lines", "@a\n@b\ndef f(){}", "@a\n@b\ndef f():\n    pass"),
    (
        "decorator_then_newline_class",
        "@dataclass\nclass P{x:int\ny:int=0}",
        "@dataclass\nclass P:\n    x: int\n    y: int = 0",
    ),
    ("decorators_blank_lines", "@a\n\n@b\n\ndef f(){}", "@a\n@b\ndef f():\n    pass"),
    (
        "decorators_in_class_on_own_lines",
        "class A{\n@property\n@abstractmethod\ndef x(){return 1}\n}",
        "class A:\n    @property\n    @abstractmethod\n    def x(self):\n        return 1",
    ),
    (
        "with_parenthesised",
        "with(a as b){}\nwith(a as b,c as d){}\nwith(a,b){}\nwith (\n a as b,\n c as d,\n){}",
        "with a as b:\n    pass\nwith a as b, c as d:\n    pass\nwith a, b:\n    pass\nwith a as b, c as d:\n    pass",
    ),
    ("import_then_dot_statement", "import a\n.x=1", "import a\nself.x = 1"),
    ("import_time_then_dot_last", "import time\n.last=1", "import time\nself.last = 1"),
    ("from_import_then_dot_statement", "from a import b\n.x=1", "from a import b\nself.x = 1"),
    (
        "generator_sole_argument",
        "f(x for x in y)\ns=sum(x*x for x in xs)\nf((x for x in y))",
        "f(x for x in y)\ns = sum(x * x for x in xs)\nf(x for x in y)",
    ),
    (
        "fstring_debug_equals",
        "x=f'{y=}'\nz=f'{a = }'\nw=f'{b=!s:>5}'",
        "x = f'{y=}'\nz = f'{a = }'\nw = f'{b=!s:>5}'",
    ),
    # ---------------------------------------------------------------- layout freedom
    (
        "spaces_everywhere",
        "for i , x in enumerate ( xs ) { print ( i , x ) }",
        "for i, x in enumerate(xs):\n    print(i, x)",
    ),
    ("spaces_around_dot_self", "def f(self) { return .x }", "def f(self):\n    return self.x"),
    ("multi_line_call", "r = f(1,\n      2,\n      k=3)\nprint(r)", "r = f(1, 2, k=3)\nprint(r)"),
    ("multi_line_dict", "d={\n  'a':1,\n  'b':2\n}", "d = {'a': 1, 'b': 2}"),
    (
        "multi_line_list_and_parens",
        "x=[1,\n2]\ny=(1\n+2)\nz=(foo()\n.bar()\n.baz())",
        "x = [1, 2]\ny = 1 + 2\nz = foo().bar().baz()",
    ),
    ("one_statement_per_line", "x=1\ny=2\nz=x+y", "x = 1\ny = 2\nz = x + y"),
    ("blank_lines", "x=1\n\n\ny=2\n", "x = 1\ny = 2"),
    ("semicolon_separated_single_line", "x=1;y=2;z=3", "x = 1\ny = 2\nz = 3"),
    ("tabs_and_crlf", "x=1\r\n\tif x{\r\n\t\ty=2\r\n\t}\r\n", "x = 1\nif x:\n    y = 2"),
    ("block_then_stmt_same_line", "if x{a()}b()", "if x:\n    a()\nb()"),
    (
        "nested_blocks_one_line",
        "def f(a){if a{return 1}return 2}",
        "def f(a):\n    if a:\n        return 1\n    return 2",
    ),
    (
        "closing_braces_stacked",
        "class A{def f(){if x{return 1}}}",
        "class A:\n    def f(self):\n        if x:\n            return 1",
    ),
    # ---------------------------------------------------------------- Python spellings that are accepted
    (
        "python_float_and_pass_and_lambda",
        "xs.sort(key=lambda t:t[1]);z=(lambda:0)()",
        "xs.sort(key=lambda t: t[1])\nz = (lambda: 0)()",
    ),
    (
        "return_tuple_parens",
        "def f(d){return (1,2),{k:v for k,v in d.items()}}",
        "def f(d):\n    return (1, 2), {k: v for k, v in d.items()}",
    ),
    ("docstring_in_def", "def f(){'doc';return 1}", "def f():\n    'doc'\n    return 1"),
    (
        "explicit_parens_in_header",
        "if (x in {1,2}){go()}\nif x in({1,2}){go()}",
        "if x in {1, 2}:\n    go()\nif x in {1, 2}:\n    go()",
    ),
    (
        "walrus_parenthesised_header",
        "while (chunk:=f.read(8)){go(chunk)}\nif (n:=len(a))>10{pass}",
        "while chunk := f.read(8):\n    go(chunk)\nif (n := len(a)) > 10:\n    pass",
    ),
    (
        "yield_parenthesised",
        "def g(){x=(yield)\nr=f((yield))\nreturn (yield 1)}",
        "def g():\n    x = yield\n    r = f((yield))\n    return (yield 1)",
    ),
    (
        "not_keyword_statement",
        "try{a()}except E{b()}not c()",
        "try:\n    a()\nexcept E:\n    b()\nnot c()",
    ),
    (
        "sequence_pattern_parens",
        "match x{case (a,b){}case (p){}case (p,){}}",
        "match x:\n    case (a, b):\n        pass\n    case (p):\n        pass\n    case (p,):\n        pass",
    ),
    (
        "mapping_pattern_parenthesised",
        "match x{case({'k':v}){a}}",
        "match x:\n    case {'k': v}:\n        a",
    ),
    (
        "match_subject_parenthesised",
        "match(x){case _{}}\nmatch({1:2}){case _{a}}",
        "match (x):\n    case _:\n        pass\nmatch {1: 2}:\n    case _:\n        a",
    ),
    (
        "set_in_header_no_parens",
        "if x in {1,2}{go()}\nif x=={1}{go()}\nif d=={}{go()}\nwhile{}{a}\nfor x in {1,2}{a}",
        "if x in {1, 2}:\n    go()\nif x == {1}:\n    go()\nif d == {}:\n    go()\nwhile {}:\n    a\nfor x in {1, 2}:\n    a",
    ),
    ("ternary_in_slice_unparenthesised", "y=s[1:n>2?-1:None]", "y = s[1:-1 if n > 2 else None]"),
    (
        "ternary_in_dict_key_unparenthesised",
        "d={a?b:c:v}\ne={k:a?b:c}",
        "d = {(b if a else c): v}\ne = {k: b if a else c}",
    ),
    (
        "ternary_in_slice_positions",
        "x=s[c?a:b]\ny=s[c?a:b:e]\nz=s[c?a:b:]\nv=s[(c?a:b):e]",
        "x = s[a if c else b]\ny = s[(a if c else b):e]\nz = s[(a if c else b):]\nv = s[(a if c else b):e]",
    ),
    (
        "ternary_chain_right_assoc",
        "x=a?b:c?d:e\ny=a?(b?c:d):e\nz=(a?b:c)?d:e",
        "x = b if a else (d if c else e)\ny = (c if b else d) if a else e\nz = d if (b if a else c) else e",
    ),
    (
        "ternary_mixed_with_python_form",
        "y=a?b:c if d else e\nz=c?(a if d else b):e",
        "y = b if a else (c if d else e)\nz = (a if d else b) if c else e",
    ),
    (
        "ternary_operands",
        "x=a?-b:-c\ny=a?not b:not c\nz=a and b?c:d\nw=a?b:c and d\nv=a?b:c,d\nf(a?b:c,d=e?f:g)\nx:int=a?b:c\nt=(y:=c?a:b)",
        "x = -b if a else -c\ny = (not b) if a else (not c)\nz = c if (a and b) else d\nw = b if a else (c and d)\nv = (b if a else c), d\nf(b if a else c, d=f if e else g)\nx: int = b if a else c\nt = (y := a if c else b)",
    ),
    (
        "lambda_body_ternary",
        "f=lambda x:x?1:0\ng=lambda y:c?a:b",
        "f = lambda x: 1 if x else 0\ng = lambda y: a if c else b",
    ),
    (
        "fstring_parenthesised_ternary",
        "s=f'{(c?a:b)}'\nt=f'{(c?a:b)!r:>10}'",
        "s = f'{a if c else b}'\nt = f'{(a if c else b)!r:>10}'",
    ),
    (
        "fstring_self_fields",
        "class A{def s(){return f'{.x:>10} {.y!r} {.z:{.w}}'}}",
        "class A:\n    def s(self):\n        return f'{self.x:>10} {self.y!r} {self.z:{self.w}}'",
    ),
    (
        "self_dot_after_keywords",
        "class A{def f(){return -.x in .s}}\nx=not.x\ny=a in.x\nz=a is.x\nw=a and.x\nv=a if.b else.c\ndel.x\nif.count==1{a}",
        "class A:\n    def f(self):\n        return -self.x in self.s\nx = not self.x\ny = a in self.x\nz = a is self.x\nw = a and self.x\nv = a if self.b else self.c\ndel self.x\nif self.count == 1:\n    a",
    ),
    (
        "self_dot_in_displays_and_slices",
        "x={.x}\ny={.x:.y}\nz={.5:.x}\nw=a[.x:]\nv=a[:.x]\nu=a[.5:]\nt=[.a for .a in b]",
        "x = {self.x}\ny = {self.x: self.y}\nz = {0.5: self.x}\nw = a[self.x:]\nv = a[:self.x]\nu = a[0.5:]\nt = [self.a for self.a in b]",
    ),
    (
        "self_dot_in_patterns",
        "match x{case .y{}case Point(x=.z){}}",
        "match x:\n    case self.y:\n        pass\n    case Point(x=self.z):\n        pass",
    ),
    (
        "keyword_glue",
        "def f(){return.mean\nreturn'x'\nreturn b'x'\nreturn f'{x}'\nreturn...\nreturn-1\nreturn.5\nreturn[1]\nreturn{1}\nreturn(1)}",
        "def f():\n    return self.mean\n    return 'x'\n    return b'x'\n    return f'{x}'\n    return ...\n    return -1\n    return .5\n    return [1]\n    return {1}\n    return (1)",
    ),
    (
        "keyword_glue_2",
        "x=''and y\ny='a'if b else'c'\nwith open(p)as f{a}\nz=1if 2else 3\nw=1.if y else z\nv=1.in y\nu=1.,.5\nt=1.-.5",
        "x = '' and y\ny = 'a' if b else 'c'\nwith open(p) as f:\n    a\nz = 1 if 2 else 3\nw = 1. if y else z\nv = 1. in y\nu = 1., .5\nt = 1. - .5",
    ),
    (
        "number_dot_forms",
        "x=1.e5\ny=1.j\nz=(1.).real\nw=.5.real\nv=1.0.real\nu=1 .real\nt=a-.5\ns=a-.x\nr=....real\nq=a[...]",
        "x = 1.e5\ny = 1.j\nz = (1.).real\nw = .5.real\nv = 1.0.real\nu = 1 .real\nt = a - .5\ns = a - self.x\nr = ....real\nq = a[...]",
    ),
    (
        "unary_operator_runs",
        "x=a--b\ny=a-- b\nz=--a\nw=-a**2\nv=(-a)**2\nu=a**-b\nt=a*-b\ns=a<-b\nr=a<--b",
        "x = a - -b\ny = a - -b\nz = --a\nw = -a ** 2\nv = (-a) ** 2\nu = a ** -b\nt = a * -b\ns = a < -b\nr = a < --b",
    ),
    (
        "decorator_forms",
        "@a@b def f(){}\n@a@b\ndef f(){}\n@(a@b)def f(){}\n@a[b@c]def f(){}\n@a(b@c)def f(){}\n@a.b(1)class C{}\n@(c?a:b)def f(){}\n@property def x(){return 1}",
        "@a\n@b\ndef f():\n    pass\n@a\n@b\ndef f():\n    pass\n@(a @ b)\ndef f():\n    pass\n@a[b @ c]\ndef f():\n    pass\n@a(b @ c)\ndef f():\n    pass\n@a.b(1)\nclass C:\n    pass\n@(a if c else b)\ndef f():\n    pass\n@property\ndef x():\n    return 1",
    ),
    (
        "display_vs_block",
        "x={}[0]\nx={}\n[0]\nif c{a}[1]\nif c{{}}\nif c{{1,2}}\nif c{}\n{1,2}\n{}\n{a:1}",
        "x = {}[0]\nx = {}\n[0]\nif c:\n    a\n[1]\nif c:\n    {}\nif c:\n    {1, 2}\nif c:\n    pass\n{1, 2}\n{}\n{a: 1}",
    ),
    (
        "newline_splits_statements",
        "x=a\n-b\ny=a\n(b)\nz=a\n[0]\nw=f()\n.g()\nv=a\n*b,=c\nu=1\n{1,2}",
        "x = a\n-b\ny = a\n(b)\nz = a\n[0]\nw = f()\nself.g()\nv = a\n*b, = c\nu = 1\n{1, 2}",
    ),
    (
        "newline_dot_statements_in_method",
        "class A{def update(value){\n.count+=1\n.mean=value\n}}\nclass B{def update(value){\n.count+=1;\n.mean=value;\n}}",
        "class A:\n    def update(self, value):\n        self.count += 1\n        self.mean = value\nclass B:\n    def update(self, value):\n        self.count += 1\n        self.mean = value",
    ),
    (
        "newline_dot_after_various",
        "return_=1\nx=y\n.z()\nif c{a=1\n.b=2}\nfor x in xs{total+=x\n.log(x)}\nx=a\n\n.b=1\nx=a  # comment\n.b=1",
        "return_ = 1\nx = y\nself.z()\nif c:\n    a = 1\n    self.b = 2\nfor x in xs:\n    total += x\n    self.log(x)\nx = a\nself.b = 1\nx = a\nself.b = 1",
    ),
    (
        "return_then_dot_statement",
        "def f(){return x\n.y=1}\ndef g(){return\n.y=1}",
        "def f():\n    return x\n    self.y = 1\ndef g():\n    return\n    self.y = 1",
    ),
    (
        "string_then_newline_then_string",
        "x=a\n'doc'\ny=f(a)\n'''doc'''",
        "x = a\n'doc'\ny = f(a)\n'''doc'''",
    ),
    ("lambda_after_newline", "x=1\nlambda:2", "x = 1\nlambda: 2"),
    (
        "match_soft_keyword_statements",
        "match=1\nmatch(x)\nmatch[0]=2\nmatch.y=3\nmatch,y=1,2\nmatch:int=1\nmatch+=1\nmatch(x).y\ntype=3\ntype(x)\ntype.x=1\ntype[0]=1\ncase=4\nprint(match,type,case)",
        "match = 1\nmatch(x)\nmatch[0] = 2\nmatch.y = 3\nmatch, y = 1, 2\nmatch: int = 1\nmatch += 1\nmatch(x).y\ntype = 3\ntype(x)\ntype.x = 1\ntype[0] = 1\ncase = 4\nprint(match, type, case)",
    ),
    (
        "match_statement_speculation",
        "match(x){case 1{a}}\nmatch -x{case _{}}\nmatch *a,b{case _{}}\nmatch [1,2]{case _{}}\nmatch {1,2}{case _{}}\nmatch (x,){case _{}}\nmatch x,y{case a,b{}}",
        "match (x):\n    case 1:\n        a\nmatch -x:\n    case _:\n        pass\nmatch *a, b:\n    case _:\n        pass\nmatch [1, 2]:\n    case _:\n        pass\nmatch {1, 2}:\n    case _:\n        pass\nmatch x,:\n    case _:\n        pass\nmatch x, y:\n    case a, b:\n        pass",
    ),
    (
        "match_keywordish_subjects",
        "match not x{case _{}}\nmatch lambda:1{case _{}}\nmatch y?x:z{case _{}}\nmatch match{case case{}}\nmatch x{case 1{a}case 2{b}}",
        "match not x:\n    case _:\n        pass\nmatch lambda: 1:\n    case _:\n        pass\nmatch x if y else z:\n    case _:\n        pass\nmatch match:\n    case case:\n        pass\nmatch x:\n    case 1:\n        a\n    case 2:\n        b",
    ),
    (
        "type_soft_keyword",
        "type X=int\ntype Y[T]=list[T]\ntype Z[T:int,*Ts,**P]=dict[T,P]",
        "type X = int\ntype Y[T] = list[T]\ntype Z[T: int, *Ts, **P] = dict[T, P]",
        V312,
    ),
    (
        "type_params_defaults",
        "type X[T=int]=T\ntype Y[*Ts=*tuple[int]]=tuple[*Ts]\ntype Z[**P=[int]]=P\nclass A[T=int,*Ts=*tuple[int,...],**P=[int]](Base){}",
        "type X[T = int] = T\ntype Y[*Ts = *tuple[int]] = tuple[*Ts]\ntype Z[**P = [int]] = P\nclass A[T = int, *Ts = *tuple[int, ...], **P = [int]](Base):\n    pass",
        V313,
    ),
    (
        "else_attachment",
        "if a{if b{x}}else{y}\nfor x in y{if c{a}}else{b}\nwhile c{if d{a}else{b}}else{e}\ntry{a}except E{b}else{c}",
        "if a:\n    if b:\n        x\nelse:\n    y\nfor x in y:\n    if c:\n        a\nelse:\n    b\nwhile c:\n    if d:\n        a\n    else:\n        b\nelse:\n    e\ntry:\n    a\nexcept E:\n    b\nelse:\n    c",
    ),
    (
        "def_bang_forms",
        "class A{def!weird(this,x){return this.x}\ndef!f(){}\ndef!g(*a){}\n@classmethod def!c(klass){return klass}}",
        "class A:\n    def weird(this, x):\n        return this.x\n    def f():\n        pass\n    def g(*a):\n        pass\n    @classmethod\n    def c(klass):\n        return klass",
    ),
    (
        "receiver_injection_forms",
        "class A{def f(x){}\ndef g(x,/,y){}\ndef h(){}\ndef i(*,x){}\ndef j(*a){}\ndef k(**kw){}\ndef l(x,/){}\n@classmethod def c(x){}\n@staticmethod def s(x){}\n@classmethod def c2(cls,x){}\ndef m(self,x){}\ndef n(cls,x){}}",
        "class A:\n    def f(self, x):\n        pass\n    def g(self, x, /, y):\n        pass\n    def h(self):\n        pass\n    def i(self, *, x):\n        pass\n    def j(self, *a):\n        pass\n    def k(self, **kw):\n        pass\n    def l(self, x, /):\n        pass\n    @classmethod\n    def c(cls, x):\n        pass\n    @staticmethod\n    def s(x):\n        pass\n    @classmethod\n    def c2(cls, x):\n        pass\n    def m(self, x):\n        pass\n    def n(cls, x):\n        pass",
    ),
    (
        "method_default_referencing_self",
        "class A{def f(x=self){}}",
        "class A:\n    def f(self, x=self):\n        pass",
    ),
    (
        "unicode_identifiers",
        "π=3.14159\n変数=1\ndef naïve(ß){return ß}",
        "π = 3.14159\n変数 = 1\ndef naïve(ß):\n    return ß",
    ),
    (
        "nested_fstring_fields",
        "x=f'{.x}'\ny=f'{.x!r:>{.w}}'",
        "x = f'{self.x}'\ny = f'{self.x!r:>{self.w}}'",
    ),
    (
        "fstring_nested_same_quotes",
        "x=f\"{d[\"k\"]}\"\ny=f'{f'{z}'}'",
        "x = f\"{d[\"k\"]}\"\ny = f'{f'{z}'}'",
        V312,
    ),
    ("triple_quoted_string_with_braces", "x='''a\n;}{'''\ny=1", "x = '''a\n;}{'''\ny = 1"),
    (
        "strings_with_special_chars",
        "x='#'; y='//'; z=\"{}\"; w=';'; v='}'; u='{'; t='a?b:c'; s='\\\\'",
        "x = '#'; y = '//'; z = \"{}\"; w = ';'; v = '}'; u = '{'; t = 'a?b:c'; s = '\\\\'",
    ),
    (
        "numbers_lexing",
        "x=1_000\ny=0x1F\nz=1e309\nw=0o17\nv=0b101\nu=1.5J\nt=1_0.0_1",
        "x = 1_000\ny = 0x1F\nz = 1e309\nw = 0o17\nv = 0b101\nu = 1.5J\nt = 1_0.0_1",
    ),
    ("empty_text", "", ""),
    ("only_newlines_and_comments", "\n\n# nothing\n\n", ""),
    ("only_semicolons", ";;;", ""),
    # ---------------------------------------------------------------- judge 3 hand-written programs (PyDense-B dialect texts)
    (
        "judge3_program_A",
        "import math;from functools import cached_property;class Vec{__slots__=('x','y');def __init__(x:float=0.,y:float=0.){.x=x;.y=y}@classmethod def from_polar(cls,r,theta){return cls(r*math.cos(theta),r*math.sin(theta))}@staticmethod def dot(a,b){return a.x*b.x+a.y*b.y}@property def norm(){return math.hypot(.x,.y)}def scaled(k=1.){def clamp(v){return -1e6<v<1e6?v:math.copysign(1e6,v)}return Vec(clamp(.x*k),clamp(.y*k))}def __repr__(){return f\"Vec({.x!r}, {.y:.3f}, {(.norm==1.?'unit':'free')})\"}def nearest(others,key=lambda v,w=1.:v.norm*w){if(n:=len(others))==0{return None}if.x in {0,1}and n>1{others=sorted(others,key=key)}return n==1?others[0]:others[1:][0]}}",
        'import math\nfrom functools import cached_property\n\nclass Vec:\n    __slots__ = ("x", "y")\n\n    def __init__(self, x: float = 0.0, y: float = 0.0):\n        self.x = x\n        self.y = y\n\n    @classmethod\n    def from_polar(cls, r, theta):\n        return cls(r * math.cos(theta), r * math.sin(theta))\n\n    @staticmethod\n    def dot(a, b):\n        return a.x * b.x + a.y * b.y\n\n    @property\n    def norm(self):\n        return math.hypot(self.x, self.y)\n\n    def scaled(self, k=1.0):\n        def clamp(v):\n            return v if -1e6 < v < 1e6 else math.copysign(1e6, v)\n        return Vec(clamp(self.x * k), clamp(self.y * k))\n\n    def __repr__(self):\n        return f"Vec({self.x!r}, {self.y:.3f}, {\'unit\' if self.norm == 1.0 else \'free\'})"\n\n    def nearest(self, others, key=lambda v, w=1.0: v.norm * w):\n        if (n := len(others)) == 0:\n            return None\n        if self.x in {0, 1} and n > 1:\n            others = sorted(others, key=key)\n        return others[0] if n == 1 else others[1:][0]\n',
    ),
    (
        "judge3_program_B",
        "import asyncio;import json;@retry(times=3)@log_calls async def fetch_all(session,urls,*,limit=10,timeout=2.5){sem=asyncio.Semaphore(limit);results={};async def one(url){async with sem,session.get(url)as resp{try{data=await resp.json()}except(ValueError,KeyError)as exc{raise RuntimeError(f\"bad json from {url}\")from exc}except asyncio.TimeoutError{return url,None}else{return url,data}finally{await asyncio.sleep(0)}}}for url,data in await asyncio.gather(*(one(u)for u in urls)){match data{case {'status':'ok','items':[first,*rest]}if rest{results[url]=first}case {'status':'ok'}|None{continue}case str()as s{results[url]=s[1:(len(s)>2?-1:None)]}case _{results[url]={k:v for k,v in data.items()if k not in('meta','debug')}}}}return results}",
        'import asyncio\nimport json\n\n@retry(times=3)\n@log_calls\nasync def fetch_all(session, urls, *, limit=10, timeout=2.5):\n    sem = asyncio.Semaphore(limit)\n    results = {}\n    async def one(url):\n        async with sem, session.get(url) as resp:\n            try:\n                data = await resp.json()\n            except (ValueError, KeyError) as exc:\n                raise RuntimeError(f"bad json from {url}") from exc\n            except asyncio.TimeoutError:\n                return url, None\n            else:\n                return url, data\n            finally:\n                await asyncio.sleep(0)\n    for url, data in await asyncio.gather(*(one(u) for u in urls)):\n        match data:\n            case {"status": "ok", "items": [first, *rest]} if rest:\n                results[url] = first\n            case {"status": "ok"} | None:\n                continue\n            case str() as s:\n                results[url] = s[1:-1 if len(s) > 2 else None]\n            case _:\n                results[url] = {k: v for k, v in data.items() if k not in ("meta", "debug")}\n    return results\n',
    ),
    (
        "judge3_program_C",
        "_cache={};def tokens(text,stop=frozenset({';','\\n'})){global _cache;if text in _cache{yield from _cache[text];return}buf=[];for ch in text{if ch in stop{if buf{yield ''.join(buf);del buf[:]}}else{buf.append(ch)}}else{if buf{yield ''.join(buf)}}assert not buf or buf==[],'leftover'}class Registry(type){def!__new__(mcs,name,bases,ns){cls=super().__new__(mcs,name,bases,ns);cls._reg=ns.get('_reg',{})|{name:cls};return cls}def register(cls,kind,*,override=False){if kind in cls._reg and not override{raise KeyError(kind)}cls._reg[kind]=cls;return cls}}def checksum(data:bytes,seed:int=0x5A)->int{acc=~seed&0xFF;i=0;while(chunk:=data[i:i+4]){acc^=sum(chunk)%256;i+=4}return acc>=0?acc:-acc}",
        '_cache = {}\n\ndef tokens(text, stop=frozenset({";", "\\n"})):\n    global _cache\n    if text in _cache:\n        yield from _cache[text]\n        return\n    buf = []\n    for ch in text:\n        if ch in stop:\n            if buf:\n                yield "".join(buf)\n                del buf[:]\n        else:\n            buf.append(ch)\n    else:\n        if buf:\n            yield "".join(buf)\n    assert not buf or buf == [], "leftover"\n\nclass Registry(type):\n    def __new__(mcs, name, bases, ns):\n        cls = super().__new__(mcs, name, bases, ns)\n        cls._reg = ns.get("_reg", {}) | {name: cls}\n        return cls\n\n    def register(cls, kind, *, override=False):\n        if kind in cls._reg and not override:\n            raise KeyError(kind)\n        cls._reg[kind] = cls\n        return cls\n\ndef checksum(data: bytes, seed: int = 0x5A) -> int:\n    acc = ~seed & 0xFF\n    i = 0\n    while (chunk := data[i:i + 4]):\n        acc ^= sum(chunk) % 256\n        i += 4\n    return acc if acc >= 0 else -acc\n',
    ),
]
