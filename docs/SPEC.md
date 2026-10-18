# PyDense v1.0 — Final Grammar Specification

> **Normative.** This document is the grammar of PyDense 1.0. The implementation in `pydense/`, the public API in
> `docs/API_CONTRACT.md`, the tests and every number in `README.md` are written against it; where they disagree,
> this document wins and the other is a bug. The measurements are reproduced by `benchmarks/token_compression.py`
> (§12.1–12.3) and `benchmarks/corpus_fidelity.py` (§12.5, §17.3).

*A whitespace-free, brace-blocked, AST-bijective surface syntax for Python 3.10–3.13, designed so that a frontier
LLM that knows Python can read and write it zero-shot while paying measurably fewer BPE tokens.*

Status: **FINAL** (synthesis of three candidate designs after a design review). File suffix: **`.dpy`** (the previous
`.pyd` suffix is Python's own Windows extension-module suffix and is recognised by the import system; it must not
be used). Reference measurements: `benchmarks/token_compression.py` (the 7 samples; `--dump DIR` writes
`sN.{full,nodoc,stripped}.dpy`) and `benchmarks/corpus_fidelity.py` (corpus). Every token count below is an exact `tiktoken` count
(`o200k_base` primary, `cl100k_base` secondary) made on 2026-10-18 with `python3.13`.

---

## 0. Decision record (what was synthesised and why)

Three candidate designs were compared in a design review: a *brace-block candidate* (Python keywords kept, `{}`
blocks, implicit receiver), a *lenient-input candidate* (Python spellings accepted as aliases, diagnostics with
positions) and a *sigil candidate* (keywords replaced by punctuation, as in v0.2). The reviewers scored all three
independently; the table records what was taken from each and what was rejected.

| source | decision |
|---|---|
| **brace-block candidate** (highest total score; preferred by two of the three reviewers) | base grammar: Python keywords kept, `{}` blocks, `.x`/implicit self, `c?a:b`, canonical floats, `{}` for `pass`, Python-rule newline termination, block-vs-display rule "a `{` can never follow a complete expression", `def!` escape, decorator primary-chain rule |
| from the **lenient-input candidate** | accept `a if c else b` as an input alias; Unicode identifiers (PEP 3131); free newline after block-closing `}`; implicit `cls` under `@classmethod` (the brace-block candidate silently dropped the receiver); line:col error messages with a one-line hint; larger fidelity corpus (469 files) as CI gate |
| from the **sigil candidate** | `}else{` fusion measurement (kept as the only glue rule for continuation keywords), `1e309` inf/nan handling, brace-depth-at-EOF diagnostics, one-flag-at-a-time ablation harness, 699-file stdlib sweep + 170-construct edge matrix as CI assets, parser builds `ast` nodes directly; all of its sigils (`?`-if, `~` for, `!` except, `^` return, `&&`, `||`, `\`, `@i(`, `import a=b`, `from m:a`) **rejected** on the measurements in §12 |
| flaws fixed (found by every reviewer) | the brace-block candidate rejected the Python ternary → accepted; two candidates rejected non-ASCII identifiers → accepted; `@classmethod def make(x)` lost its receiver → `cls` injected; `def f(this,x)` silent injection → lint W002; `type X[*Ts=*tuple[int]]` (PEP 696 starred default) → in grammar; docstring-only module became `pass` → empty body; `1 .real` text bug → parser emits AST, emitter writes `(1).real`; colon habit `if x:{` → accepted; non-primary decorator error → actionable message; `foo()\n.bar()` → lint W001 and emitter never produces it; `import m\n.x=1` glued into `import m.x` by the brace-block candidate's reference parser → grammar rule §6.6 (a depth-0 newline ends the dotted name) |
| rejected after re-measurement | `\` lambda (exactly 0 tokens in 8/8 realistic contexts, §12.3), `}:{` else (−3 tokens on 7 samples = 0.2%, alien, "most forgettable sigil"), `.name` receiver marker (ties `def!` at 13/13, loses on `def f(.,*a)` 13 vs 12), `@i(` (−3 per `__init__` but invented syntax that collides with a decorator named `i`), `;` as canonical separator (1283 vs 1281 for newlines; newline keeps the model's line-based reasoning), `return .x` spacing as canonical (+10 tokens = +0.6%; available as `--pretty`) |

---

## 1. Design principles (measured)

1. **Python keywords are free.** A keyword is one BPE token and the following space fuses into the next identifier
   (`def update(` = `def`,` update`,`(`). Every sigil keyword measured in context is neutral or negative
   (`@f update(` = 3 tokens, `~x:y{` = `for x in y{` ±1, `!isinstance(` splits `is`+`instance`). PyDense keeps every
   Python keyword, operator, literal form, import, decorator, comprehension, pattern and f-string spelling.
2. **Whitespace and line structure are the tax.** Removing optional spaces: −9.3%. `{}` blocks instead of
   newline+indent (2 tokens per line at any depth): another −5%. One statement per line costs nothing once blocks are
   braces (`\n` = 1 token = `;`; 1281 vs 1283 on the 7 samples), and `){`, `{\n`, `}\n`, `}}`, `}else` are single tokens.
3. **`self` is the largest lexical redundancy.** `self.x` = 2 tokens, `.x` = 1; the receiver parameter costs 1–2
   per method. Both are removed by an exactly invertible rule (§7).
4. **Three expression-level notations pay and are familiar from C/JS/Python itself:** `c?a:b` (−1.7 tokens per
   use), canonical floats `1.` / `.5` (−1 to −2 per float, same `float` value ⇒ same AST), `{}` for a `pass`-only body (−2).
5. **Bijection is the headline guarantee.** Every rule has a stated inverse; `ast.dump(parse(emit(src))) ==
   ast.dump(ast.parse(src))` is the oracle, verified 469/469 on 148 stdlib + 321 site-packages files (12,508
   top-level statements) in FULL and NODOC modes (§12.5).
   Where a shortcut cannot be inverted the emitter falls back to the explicit Python spelling (`def!`, explicit `self`).
6. **Lenient input, canonical output.** The parser accepts every Python spelling it replaces (`a if c else b`,
   `lambda`, explicit `self`, `self.x`, `1.0`, `pass`, `;`, newlines, `if x:{`, comments, `\`-continuation);
   the emitter always produces the canonical form (§10), so `emit(parse(text))` is idempotent.
7. **Honest numbers.** Three modes are always reported side by side (§11): FULL (true AST bijection, docstrings kept),
   LOSSLESS-NODOC (docstrings dropped on both sides) and STRIPPED (lossy). Baselines are `ast.unparse` output and
   python-minifier on the same files.

---

## 2. Lexical grammar

Whitespace (space, tab, form feed, CR) is never significant outside string literals. The lexer produces
NAME, NUMBER, STRING, OP, NEWLINE, COMMENT (discarded) and EOF.

```
NAME      ::= Python identifier (Unicode, PEP 3131; NFKC-normalised as CPython does)
KEYWORD   ::= False None True and as assert async await break class continue def del elif else except
              finally for from global if import in is lambda nonlocal not or pass raise return try while with yield
SOFT_KW   ::= match case type        (contextual, §6.7)
NUMBER    ::= Python numeric literal: decimal/hex/octal/binary ints with `_` separators (0xFF, 0o7, 0b1, 1_000),
              floats (1.5, 1., .5, 1e-5, 1_0.0_1), imaginary (1j, 1.5J, .5j).
              `.` followed by a digit is always a NUMBER; `1.` followed by a non-digit, non-`.` is a float.
STRING    ::= Python string/bytes literal: prefixes r R b B u U f F and the combinations rb br Rb fr rf FR …,
              single or triple quotes, escapes as Python. f-strings: PEP 701 (3.12) rules — replacement fields are
              PyDense *expressions* (so `{.x}` works), nested quotes of the same kind allowed, `{{`/`}}` escapes,
              `!r !s !a` conversions, `:spec` with nested `{fields}`, `=` debug form accepted on input.
              Adjacent STRING tokens are implicitly concatenated (Python rule); canonical output merges them.
OP        ::= longest match from:
              **= //= >>= <<= -> ** // << >> <= >= == != += -= *= /= %= &= |= ^= @= := ...
              + - * / % @ & | ^ ~ < > ( ) [ ] { } , : ; . = ? !
NEWLINE   ::= '\n' (and '\r\n') at bracket depth 0 (see §6.6 for where it is significant)
COMMENT   ::= '#' to end of line — skipped; not part of the AST; never emitted (§11)
CONTINUE  ::= '\' immediately followed by NEWLINE — the newline is removed (Python's explicit line join);
              '\' anywhere else is an error ("PyDense has no `\` lambda; write `lambda`")
```

Notes.
* `?` and `!` are the only characters with non-Python meaning: `?` is the ternary operator; `!` appears in `!=`
  (one token) and directly after `def` (`def!`, §7). `!` is **not** `not`.
* `.`: `.5` is a NUMBER; `...` is Ellipsis (longest match); `.NAME` at the start of an atom is `self.NAME` (§6.5);
  `.NAME` after a complete primary is attribute access. `1..real` and `1.real` are lexical errors as in Python; the
  emitter writes `(1).real` and `(1.).real`.
* String prefixes are recognised before NAME, so `return f'x'` needs its space but `return'x'` does not (§10.2).
* A `#` comment ends at the newline; the NEWLINE token is still produced (so a comment never joins two statements).

---

## 3. Statement grammar (EBNF)

Notation: `A?` optional, `A*` repetition, `A+` one or more, `|` alternative, terminals quoted, `&X` lookahead.

```ebnf
module        ::= stmt_list EOF
stmt_list     ::= (statement | ";")*                       (* ";" tolerated anywhere between statements *)
block         ::= "{" stmt_list "}"                        (* "{}" ⇔ body [Pass] in def/class/compound bodies *)

statement     ::= compound_stmt | simple_stmt sep
sep           ::= ";" | NEWLINE | &"}" | EOF                (* NEWLINE only at bracket depth 0, §6.6 *)

simple_stmt   ::= "pass" | "break" | "continue"
                | "return" star_exprs?
                | "raise" (expression ("from" expression)?)?
                | ("global" | "nonlocal") NAME ("," NAME)*
                | "del" targets
                | "assert" expression ("," expression)?
                | "import" dotted alias_as? ("," dotted alias_as?)*
                | "from" ("."* dotted | "."+) "import" ("*" | "(" names ","? ")" | names)
                | "type" NAME type_params? "=" expression                  (* soft keyword, §6.7 *)
                | target ":" expression ("=" rhs)?                         (* AnnAssign; "(x):T" ⇒ simple=0 *)
                | target AUGOP rhs                                         (* AugAssign, 13 operators *)
                | star_exprs ("=" rhs)*                                    (* Assign / Expr *)
rhs           ::= yield_expr | star_exprs
alias_as      ::= "as" NAME
names         ::= NAME alias_as? ("," NAME alias_as?)*
dotted        ::= NAME ("." NAME)*                                         (* may not cross a NEWLINE, §6.6 *)
AUGOP         ::= "+=" | "-=" | "*=" | "/=" | "//=" | "%=" | "**=" | "<<=" | ">>=" | "&=" | "|=" | "^=" | "@="

compound_stmt ::= if_stmt | while_stmt | for_stmt | with_stmt | try_stmt | match_stmt
                | decorators? ("async"? funcdef | classdef)
if_stmt       ::= "if" named_expr ":"? block ("elif" named_expr ":"? block)* else_block?
else_block    ::= "else" ":"? block
while_stmt    ::= "while" named_expr ":"? block else_block?
for_stmt      ::= "async"? "for" star_targets "in" star_exprs ":"? block else_block?
with_stmt     ::= "async"? "with" (with_items | "(" with_items ","? ")") ":"? block
with_items    ::= with_item ("," with_item)*
with_item     ::= expression ("as" star_target)?
try_stmt      ::= "try" ":"? block (handler+ else_block? finally_block? | finally_block)
handler       ::= "except" "*"? (expression ("as" NAME)?)? ":"? block     (* all handlers plain or all "*" *)
finally_block ::= "finally" ":"? block
match_stmt    ::= "match" star_exprs ":"? "{" case_clause+ "}"
case_clause   ::= "case" patterns ("if" named_expr)? ":"? block

decorators    ::= ("@" decorator NEWLINE?)+
decorator     ::= primary_chain | "(" expression ")"       (* primary_chain: NAME ("." NAME | "(" args? ")" | "[" slices "]")* *)
funcdef       ::= "def" "!"? NAME type_params? "(" params? ")" ("->" expression)? ":"? block
classdef      ::= "class" NAME type_params? ("(" args? ")")? ":"? block

params        ::= param ("," param)* ","?
param         ::= NAME (":" expression)? ("=" expression)?
                | "/"
                | "*" (NAME (":" ("*"? expression))?)?                     (* "*args:*Ts" PEP 646 *)
                | "**" NAME (":" expression)?
type_params   ::= "[" type_param ("," type_param)* ","? "]"
type_param    ::= NAME (":" expression)? ("=" expression)?
                | "*" NAME ("=" ("*"? expression))?                         (* 3.13 default; "*Ts=*tuple[int]" *)
                | "**" NAME ("=" expression)?
```

The optional `":"` before every block is the *colon habit* lenience (`if x:{`, `def f():{`, `else:{`); it is never
emitted. It is unambiguous because a header expression cannot end in a bare `:` (ternary and lambda consume their
own colon; `:=` is one token) and no statement can start with `:`.

### 3.1 Patterns (match)

```ebnf
patterns      ::= pattern ("," pattern)* ","?                               (* open sequence if a comma is present *)
pattern       ::= or_pattern ("as" NAME)?
or_pattern    ::= closed_pattern ("|" closed_pattern)*
closed_pattern::= literal_pattern | capture | wildcard | value_pattern | group_or_seq
                | "[" (pattern ("," pattern)* ","?)? "]"
                | "{" (mapping_item ("," mapping_item)* ("," "**" NAME)? ","?)? "}"
                | class_pattern | "*" NAME
literal_pattern ::= ("-")? NUMBER (("+" | "-") NUMBER)? | STRING+ | "None" | "True" | "False"
capture       ::= NAME            wildcard ::= "_"
value_pattern ::= NAME ("." NAME)+ | "." NAME                               (* ".x" ≡ self.x, §6.5 *)
group_or_seq  ::= "(" (pattern ("," pattern)* ","?)? ")"                    (* "(p)" is p; "(p,)" / "()" sequences *)
class_pattern ::= (NAME | value_pattern) "(" (pattern ("," pattern)*)? ("," NAME "=" pattern)* ","? ")"
mapping_item  ::= (literal_pattern | value_pattern) ":" pattern
```

---

## 4. Expression grammar and precedence

```ebnf
star_exprs    ::= star_expr ("," star_expr)* ","?            (* Tuple iff a comma is present *)
star_expr     ::= "*" bitwise_or | named_expr
star_targets  ::= star_target ("," star_target)* ","?
star_target   ::= "*"? target
target        ::= primary (Name/Attribute/Subscript) | "(" star_targets ")" | "[" star_targets "]"
named_expr    ::= NAME ":=" expression | expression

expression    ::= "lambda" lambda_params? ":" expression
                | disjunction "?" disjunction ":" expression              (* IfExp: test ? body : orelse *)
                | disjunction "if" disjunction "else" expression          (* Python spelling, accepted *)
                | disjunction
disjunction   ::= conjunction ("or" conjunction)*
conjunction   ::= inversion ("and" inversion)*
inversion     ::= "not" inversion | comparison
comparison    ::= bitwise_or (comp_op bitwise_or)*
comp_op       ::= "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "not" "in" | "is" | "is" "not"
bitwise_or    ::= bitwise_xor ("|" bitwise_xor)*
bitwise_xor   ::= bitwise_and ("^" bitwise_and)*
bitwise_and   ::= shift ("&" shift)*
shift         ::= sum (("<<" | ">>") sum)*
sum           ::= term (("+" | "-") term)*
term          ::= factor (("*" | "/" | "//" | "%" | "@") factor)*
factor        ::= ("+" | "-" | "~") factor | power
power         ::= await_primary ("**" factor)?
await_primary ::= "await" primary | primary
primary       ::= atom ("." NAME | "(" args? ")" | "[" slices "]")*
atom          ::= NAME | NUMBER | STRING+ | "..." | "None" | "True" | "False"
                | "." NAME                                                (* self.NAME *)
                | "(" (yield_expr | star_expr comp_for+ | star_exprs)? ")"
                | "[" (star_expr comp_for+ | star_exprs)? "]"
                | "{" ( kv ("," kv)* ","? | expression ":" expression comp_for+
                      | star_expr comp_for+ | star_exprs )? "}"           (* "{}" is an empty dict *)
kv            ::= expression ":" expression | "**" bitwise_or
comp_for      ::= "async"? "for" star_targets "in" disjunction ("if" disjunction)*
args          ::= arg ("," arg)* ","?
arg           ::= "*" expression | "**" expression | NAME "=" expression | named_expr comp_for*
slices        ::= slice ("," slice)* ","?
slice         ::= expression? ":" expression? (":" expression?)? | named_expr | "*" bitwise_or
yield_expr    ::= "yield" ("from" expression | star_exprs)?
lambda_params ::= Python lambda parameter list (names, defaults, "/", "*", "**"; no annotations)
```

### 4.1 Precedence table (lowest binds loosest; identical to CPython's `ast._Unparser._Precedence`)

| level | constructs | associativity / note |
|---|---|---|
| TUPLE | `a,b` (bare tuple in return/assign/for/subscript) | |
| YIELD | `yield`, `yield from` | parenthesised except as statement / assignment RHS / for-iter |
| TEST | `c?a:b`, `lambda`, (`a if c else b`) | right-assoc orelse: `c?a:d?b:e` = `a if c else (b if d else e)`; body/test that are themselves TEST are parenthesised |
| OR | `or` | n-ary flat |
| AND | `and` | n-ary flat |
| NOT | `not` | prefix |
| CMP | `< > == >= <= != in not in is is not` | chained |
| BOR | `\|` |  |
| BXOR | `^` |  |
| BAND | `&` |  |
| SHIFT | `<< >>` |  |
| ARITH | `+ -` |  |
| TERM | `* / // % @` |  |
| FACTOR | unary `+ - ~` |  |
| POWER | `**` | right-assoc; left operand at AWAIT level, right at FACTOR level (`(-a)**2`, `a**-b`, `(a**b)**c` round-trip) |
| AWAIT | `await` |  |
| ATOM | names, literals, displays, calls, attributes, subscripts, `.x` | |

The emitter inherits `ast._Unparser`'s parenthesisation verbatim, so tree shape is preserved exactly where
`ast.unparse` preserves it (`(a or b) and c`, `(a and b)+1`, `[x for x in y if x if x>1]`). Additional emitter
obligations (readability rules; the parser does not need them): an `IfExp` or `Lambda` is parenthesised when it is a
slice bound (`a[(c?x:y):]`), a dict key (`{(c?a:b):v}`), an f-string replacement field (`f'{(c?a:b)}'`, required:
Python's `:` starts the format spec), or the test/body of another ternary (`c?(d?x:y):z`).

---

## 5. Blocks, separators and layout

1. A **block** is `{ stmt_list }`. `{}` is a body of exactly `[Pass]`. `{pass}` is accepted (same AST).
2. A **compound statement ends at its `}`**; nothing follows it (`;` is tolerated). The next statement starts
   immediately or on the next line.
3. A **simple statement ends** at `;`, at a NEWLINE at bracket depth 0, before `}`, or at EOF.
4. **Canonical layout** (what the emitter writes; all other layouts are accepted):
   * one statement per line;
   * `{` on the header line, followed by a newline when the block is non-empty (`def f(a){` ⏎ `return a}`);
   * `}` glued to the last statement of the block (a newline before `}` costs one token: `'\n'`,`'}'` vs `'()}'`);
   * a newline after `}` **unless** the next token is another `}` or one of `else elif except finally`
     (`}else` is one BPE token; `}elif`, `}except`, `}finally` cost the same either way and are kept on the line
     for consistency); `case` clauses start on a new line;
   * stacked decorators and their `def`/`class` on one line: `@a@b.c(1)def f(){` (+2 tokens if split; `@dc(...)⏎class` costs 0 but is not canonical);
   * module-level statements separated by newlines; no blank lines; no indentation (indentation costs 1 token per line).

Measured on the 7 samples (LOSSLESS-NODOC, o200k): canonical 1281; `;`-separated single line 1283; newline-separated
without `}\n` 1279; newline before `}` as well +7. The layout band is 0.3% wide; the canonical form is chosen for
line-structure (every reviewer asked for it) at a cost of 2 tokens in 1281.

---

## 6. Disambiguation rules (deterministic recursive descent, ≤2 tokens of lookahead except §6.7)

**6.1 Block `{` vs dict/set `{`.** A `{` opens a block iff it follows a complete *header*. In the expression grammar
no production lets `{` follow a complete expression, so the header expression parser simply stops when it sees `{`
where no operand is expected, and the compound-statement parser takes it as the block. Inside a header a `{` where
an operand *is* expected is a display: `if x in {1,2}{…}` — `in` needs an operand, `{1,2}` is a set, `}` closes it,
the next `{` is the block. `while{}{…}`, `if x=={1}{`, `match {1:2}{case…}`, `case {'k':v}{` all parse with no
parentheses. At statement start `{` is always a display (Python has no bare blocks). LL(1).

**6.2 Dict vs set inside a display.** Python's own rule: `{}` dict; first item `**x` or `expr ':' expr` ⇒ dict /
dict-comp; otherwise set / set-comp. LL(1) after the first item.

**6.3 Ternary `?` and its `:`.** `?` has no other meaning. After `?` the body is parsed as a *disjunction*, which
cannot contain a top-level `:`, so the next `:` is the ternary's; the orelse is an `expression` (right-recursive).
Consequences: `s[c?a:b:e]` = `Slice(lower=IfExp)`; `{c?a:b:v}` key is the ternary; `lambda x:c?a:b` body is the
ternary; `f'{c?a:b}'` is an error because `:` starts the format spec (parenthesise). The Python form
`a if c else b` is parsed at the same level (`disjunction "if" disjunction "else" expression`). LL(1).

**6.4 Lambda colon vs slice/dict colon.** A lambda body is an `expression`; its only possible top-level `:` belongs to a
nested ternary, which consumes it. `a[lambda:x:y]` = `a[(lambda:x):y]`, as in Python. LL(1).

**6.5 `.` disambiguation.** `.`+digit ⇒ NUMBER (`.5`). `...` ⇒ Ellipsis. `.`+NAME in *prefix* position (start of an
atom: after an operator, `(` `[` `{` `,` `:` `=` `?`, a keyword, `@`, or at statement start) ⇒ `Attribute(Name('self'),
NAME)`; in *postfix* position (after a complete primary) ⇒ attribute access. Whitespace is insignificant, so
`a .b` = `a.b`; a NEWLINE at depth 0 *is* significant, so `x=1⏎.y=2` is two statements (§6.6). `.x` is pure textual
sugar: it is valid anywhere (module level, nested functions, patterns, f-string fields) and always means `self.x`;
bare `self` is still written `self`. LL(2) (`.` then digit/NAME/`.`).

**6.6 Newlines.** A NEWLINE is significant only at bracket depth 0, where depth counts `(` `)` `[` `]` and
*display* `{` `}` (block braces do not count — they are statement structure). A depth-0 NEWLINE:
* ends a simple statement (so `x=a⏎-b`, `x=a⏎(b)`, `x=a⏎[0]`, `x=f()⏎.g()` are two statements each — Python's rule);
* ends the dotted name of `import a.b` / `from a.b import` (so `import time⏎.last=1` is `import time` then
  `self.last=1`; the brace-block candidate's reference parser glued these — fixed here);
* is **ignored** before `{`, `}`, `else`, `elif`, `except`, `finally`, `case`, after a decorator, after `\`
  (explicit join), between stacked `;`, and after a NEWLINE (blank lines).
Binary operators never continue across a depth-0 newline; multi-line expressions need brackets, as in Python.
`return`/`raise`/`yield`/`del`/`global`/`assert` followed by NEWLINE end there (Python rule).

**6.7 Soft keywords.** `type`: an alias iff the next token is a NAME (two adjacent operands cannot be an
expression) — LL(2). `case`: only inside a match body. `match`: a match statement iff the next token is one of
NAME, NUMBER, STRING, `not`, `await`, `lambda`, `{`, `...` (LL(2), same adjacency argument); an expression statement
iff the next token is `=`, an AUGOP, `:` (not `:=`), `;`, NEWLINE, `}`, `)`, `]`, `,`, `?`, `.`+NAME-followed-by-a-non-operand,
or a binary operator other than `- + ~ *`; otherwise (next token `(`, `[`, `-`, `+`, `~`, `*`, `.`) the parser
**speculates**: it parses `match star_exprs` and checks for `{` `case`, rewinding to an expression statement on
failure. This bounded speculation is exactly CPython's PEG strategy for the same soft keyword and is the only
place the parser looks past two tokens.

**6.8 Decorators.** A decorator is a *primary chain* (`NAME` with `.NAME`, `(...)`, `[...]` trailers) or `( expression )`.
Hence `@` after a complete chain starts the next decorator (`@property@abstractmethod def` is two decorators, never
matmul), and `def` / `class` / `async` ends the list. Statement-initial `@` is never matmul. A real matmul decorator is
written `@(a@b)`; any other non-chain decorator `@(a or b)`. The error for `@a or b def` says so. LL(1).

**6.9 Else.** `else` after a block's `}` belongs to the innermost open `if`/`for`/`while`/`try` — the parser knows
which block it just closed. There is no dangling-else problem because every body is braced.

**6.10 `def!`.** `!` directly after `def` means "do not inject a receiver" (§7). `!` has no other use except in `!=`,
so `def!` is LL(2).

**6.11 Separators.** `x={}⏎[0]` is a dict statement then a list statement (depth-0 NEWLINE); `x={}[0]` is a subscript;
`if c{a}[1]` is a block followed by a list statement — the parser knows whether the `}` it just consumed closed a
block or a display.

**6.12 Keyword/identifier adjacency.** Tokens are produced by maximal munch of NAME / NUMBER / STRING-with-prefix /
OP, so `return.mean`, `in.keys()`, `yield''.join(buf)`, `==''and`, `)as f{`, `a--b`, `not.x` are all well-formed.
`returnx` would be a NAME, so a space is required between two word tokens (§10.2).

### 6.13 Lookahead summary

| decision | tokens consulted |
|---|---|
| statement kind | 1 (first token); `def` `!`: 2; `type` NAME: 2; `match`: 2 or bounded speculation (§6.7) |
| `{` block vs display | 0 (grammatical position) |
| `.x` vs `.5` vs `...` | 2 |
| `else`/`elif`/`except`/`finally` continuation | 1 |
| `:` before block (colon habit) | 2 (`:` then `{`) |
| `*`/`**` starred vs operator | 0 (operand vs operator position) |
| decorator end | 1 (`@`, `def`, `class`, `async`) |
| simple-statement end | 1 (`;`, NEWLINE, `}`, EOF) |
| import dotted name | 1 (`.` without `nl_before`) |

---

## 7. Implicit receiver (`self` / `cls`) — exact bijective rule

**Scope.** A `def`/`async def` is a *method* iff the nearest enclosing `def`, `lambda` or `class` scope is a `class`.
`if`/`for`/`while`/`try`/`with`/`match` blocks are transparent (a `def` inside `if TYPE_CHECKING:` in a class body is a
method); functions nested inside a method and lambdas are never methods.

**Receiver name.** For a method, `R` = none if any decorator is the bare `Name('staticmethod')`; `cls` if any decorator
is the bare `Name('classmethod')`; otherwise `self`. (`@abc.abstractmethod`, `@functools.cache`, `@property`,
`@staticmethod()` with a call, etc. do not change `R`.)

**Parser rule.** For a method with receiver `R ≠ none`: prepend parameter `R` to the written parameter list **unless**
(a) the def is written `def!`, or (b) the first written parameter (positional-only or regular) is literally named
`self` or `cls`. If the written list begins with positional-only parameters (a `/` is present), the injected `R`
joins the positional-only group; otherwise it becomes the first regular parameter.

**Emitter rule** (total and invertible). Let `p` = real parameters (posonly + regular). Write the method:
* **dropped** (`def m(rest)`) iff `p[0]` exists, `p[0].arg == R`, `p[0]` has no annotation and no default, `p[0]` is not
  the *only* positional-only parameter (dropping it would leave a bare `/`), and the parser rule applied to `p[1:]`
  would inject (i.e. `p[1]` is not literally `self`/`cls`);
* **plain** (`def m(p)`) iff the parser rule applied to `p` would not inject: `R == none`, or `p[0].arg ∈ {self, cls}`
  (covers `__new__(cls)`, `__init_subclass__(cls)`, metaclass `__call__(cls,…)`, annotated `self: T`, defaulted or
  positional-only `self, /`, `def register(self, cls)`);
* **`def!`** otherwise (first parameter neither `self` nor `cls`, or no parameters at all).

Corpus frequency (469 files, 10,116 methods): dropped 9,506 (94.0%), implicit `cls` 290 (2.9%), plain 190 (1.9%),
`@staticmethod` 75 (0.7%), `def!` 55 (0.5%).

| Python (in a class body) | PyDense | why |
|---|---|---|
| `def m(self, x):` | `def m(x){` | dropped |
| `def __init__(self, a, b=1):` | `def __init__(a,b=1){` | dropped |
| `@classmethod def c(cls, x):` | `@classmethod def c(x){` | dropped, `R = cls` |
| `@staticmethod def s(x):` | `@staticmethod def s(x){` | `R = none`, plain |
| `def __new__(cls, *a):` | `def __new__(cls,*a){` | first param literally `cls` ⇒ plain |
| `def m(self: 'A', x):`, `def m(self=None):`, `def m(self, /, x):` | written verbatim | annotated / defaulted / sole posonly |
| `def m(self, cls):` | `def m(self,cls){` | dropping would make the parser see `cls` first |
| `def m(this, x):`, `def m():`, `def m(*args):` | `def!m(this,x){`, `def!m(){`, `def!m(*args){` | not invertible otherwise |
| `@classmethod def c(klass):` | `@classmethod def!c(klass){` | |
| nested `def inner(y):` inside a method | `def inner(y){` | not a method |
| `lambda self: self.x` | unchanged (`.x` still allowed: `lambda self:.x`) | lambdas never inject |

Writers may always write `self`/`cls` explicitly (rule b) and `self.x` instead of `.x`. The lint rule W002 (§13)
warns when a method's first written parameter is one of `this mcs metacls meta klass kls that me obj` without `def!`.

---

## 8. Decorators, imports, and other statement forms

* **Decorators**: `@name`, `@name.attr`, `@name(args)`, `@name[idx].attr(...)` chains written adjacent:
  `@dataclass(frozen=True)class A{`, `@property@abstractmethod def x(){`. Any other expression: `@(expr)`.
  Space after a decorator only when it ends in a word character and `def`/`class`/`async` follows
  (`@property def`). Newline between decorators accepted, not canonical.
* **Imports**: Python syntax, spaces removed where legal: `import numpy as np`, `import a.b,c`, `from ..pkg.mod import
  thing as t,other`, `from . import x`, `from m import *`, `from m import (a,b)` accepted. Relative level = number of
  leading dots (`...` lexes as one token and counts 3). Measured: `import numpy=np` saves 1 token but is invented and
  rejected; `from pathlib:Path` saves 0.
* **Assignments**: `a=b=c`; `a,*b=c`; `x:int=5`; `x:int`; `(x):int` ⇔ `simple=0`; all 13 augmented operators
  (`x@=m`, `x**=2`, `x<<=1`, `x//=2`).
* **Return / yield / raise / del / assert / global / nonlocal / pass / break / continue**: Python keywords. Tuples are
  bare where Python allows (`return a,b`, `yield a,b`, `for x in a,b{`, `x=a,b`); `return (a,b)` costs +2.
* **Type aliases**: `type X[T:int,*Ts,**P]=dict[T,P]`; defaults `type X[T=int,*Ts=*tuple[int],**P=[int]]=...`.
* **Generic defs/classes**: `def f[T](x:T)->T{`, `class Box[T](Generic[T]){`.
* **With**: `with a as b,c{`; parenthesised form `with(a as b,c){` accepted; `async with`.
* **Try**: `try{}except E as e{}except(A,B){}except{}else{}finally{}`; `except*E as eg{}` (TryStar). Handlers are all
  plain or all starred (AST constraint).
* **Match**: `match s{` ⏎ `case [a,*rest]if a>0{...}` ⏎ `case {'k':v,**r}{...}` ⏎ `case Point(x=0)|Point(y=0){...}` ⏎ `case str()as s{...}` ⏎ `case _{}}`.

---

## 9. Bijection table — every `ast` node of Python 3.10–3.13

`mod`: **Module** ⇄ `stmt_list` (empty module ⇄ empty text; `type_ignores` not representable, §11). `Interactive`,
`Expression`, `FunctionType` are not module source and are out of scope (an expression parses as a one-statement module).

### 9.1 Statements (28 classes)

| `ast.stmt` | PyDense | note |
|---|---|---|
| FunctionDef | `decorators def[!] NAME[type_params](params)->returns{body}` | params minus receiver (§7); `{}` ⇔ `[Pass]` |
| AsyncFunctionDef | `async def …` | |
| ClassDef | `decorators class NAME[type_params](bases,keywords){body}` | `()` omitted when no bases/keywords |
| Return | `return` / `return v` / `return a,b` | |
| Delete | `del t1,t2` | |
| Assign | `t1=t2=value` | bare tuples both sides |
| TypeAlias (3.12) | `type NAME[type_params]=value` | |
| AugAssign | `target OP= value` | 13 ops |
| AnnAssign | `target:ann` / `target:ann=value` / `(name):ann` | `simple` by parentheses |
| For / AsyncFor | `[async ]for targets in iter{body}else{orelse}` | |
| While | `while test{body}else{orelse}` | |
| If | `if test{body}elif test{body}else{orelse}` | an `orelse` that is exactly one `If` collapses to `elif` (as `ast.unparse`); `else{if c{}}` is kept when orelse has anything else |
| With / AsyncWith | `[async ]with item,item{body}` | item = `expr` or `expr as target` |
| Match (3.10) | `match subject{case …}` | |
| Raise | `raise` / `raise e` / `raise e from c` | |
| Try | `try{}except…{}else{}finally{}` | |
| TryStar (3.11) | same with `except*` | |
| Assert | `assert t` / `assert t,msg` | |
| Import | `import a.b as c,d` | |
| ImportFrom | `from ..m import a as b,c` / `from . import x` / `from m import *` | level = dots |
| Global / Nonlocal | `global a,b` / `nonlocal a,b` | |
| Expr | the expression; `yield x` bare | a docstring is an `Expr(Constant(str))` first in a body |
| Pass | `pass`; a body that is exactly `[Pass]` ⇄ `{}` | |
| Break / Continue | `break` / `continue` | |

### 9.2 Expressions (27 classes)

| `ast.expr` | PyDense | note |
|---|---|---|
| BoolOp | `a and b and c` / `a or b` | flat n-ary; only a nested *same* operator is parenthesised (`a or(b or c)`); `a or b and c`, `not a and not(b or c)` are written without parentheses |
| NamedExpr | `(n:=v)` ; bare where Python allows it: `if`/`elif`/`while` headers (`while n:=f(){`), call arguments (`f(x:=1)`), list and set items (`[y:=f(x),y**2]`) | parenthesised everywhere else (`x=(y:=1)`, `a[(i:=1)]`) |
| BinOp | `+ - * @ / % ** << >> \| ^ & //` | no spaces; `**` right-assoc; a unary right operand of `**` is bare (`a**-b`) |
| UnaryOp | `-x +x ~x not x` | |
| Lambda | `lambda a,b=1,*c,d,**k:body` ; `lambda:0` | |
| IfExp | `test?body:orelse` | Python form accepted on input |
| Dict | `{k:v,**m}` ; `{}` | |
| Set | `{a,b}` ; empty set `{*()}` (as `ast.unparse`) | |
| ListComp / SetComp / DictComp / GeneratorExp | `[e for t in it if c]` `{e …}` `{k:v …}` `(e …)` | `async for`; multiple `for`/`if`; sole call argument `f(x for x in y)` accepted and canonical |
| Await | `await x` | |
| Yield / YieldFrom | `yield` / `yield x` / `yield from x` | parenthesised inside expressions |
| Compare | `a<b<=c`, `a not in b`, `a is not b` | chained |
| Call | `f(a,*b,k=1,**kw)` | |
| FormattedValue / JoinedStr | f-string with PyDense fields: `f'{.x!r:>{w}.{p}f} {d["k"]} x={x!r} {{lit}}'` | `{x=}` debug accepted, canonical `x={x!r}` (as `ast.unparse`) |
| Constant | int (decimal), float (shortest spelling: `1.` `.5` `0.` `1e-05` `1e309` for inf), complex `1j`, str/bytes (`repr`-style quote choice), `True False None`, `...`; `kind='u'` ⇔ `u'…'` | |
| Attribute | `obj.name` ; `.name` when obj is `Name('self')` ; `(1).real` for numeric receivers | |
| Subscript | `a[i]` `a[lo:hi:st]` `a[i,j]` `a[*s]` | |
| Starred | `*x` in calls, displays, targets, `return *a,b`, subscripts | |
| Name | `name` ; ctx (Load/Store/Del) by position | |
| List / Tuple | `[a,b]` ; `a,b` / `(a,b)` by precedence ; `()` ; `(a,)` | |
| Slice | `lo:hi:step`, each part optional | IfExp/Lambda bounds parenthesised |

### 9.3 Other nodes

| node | PyDense |
|---|---|
| expr_context Load/Store/Del | by position |
| boolop And/Or; operator ×13; unaryop ×4; cmpop ×10 | Python spellings |
| comprehension | `[async ]for target in iter if c1 if c2` |
| ExceptHandler | `except[*] type as name{body}` ; bare `except{` |
| arguments / arg | posonly `/`, `*args[:*Ts]`, kwonly `*`, `**kw`, defaults, annotations (§3) |
| keyword | `name=value` / `**value` |
| alias | `name as asname` |
| withitem | `ctx as target` |
| match_case | `case pattern if guard{body}` |
| MatchValue | literal, `-1`, `1+2j`, `a.b.c`, `.x` |
| MatchSingleton | `None` `True` `False` |
| MatchSequence | `[p,q,*r]` (canonical brackets; `(p,q)` accepted) |
| MatchMapping | `{k:p,**rest}` |
| MatchClass | `Cls(p,q,attr=p)` |
| MatchStar | `*name` / `*_` |
| MatchAs | `name` / `_` / `pattern as name` |
| MatchOr | `p\|q\|r` |
| TypeVar / ParamSpec / TypeVarTuple (3.12) | `T`, `T:bound`, `T=default` (3.13), `**P`, `**P=[int]`, `*Ts`, `*Ts=*tuple[int]` |
| TypeIgnore / type_comment | **not representable** (dropped; CPython only records them with `type_comments=True`) |

**Not representable** (identical to `ast.unparse`): comments, blank lines and original formatting, `# type:` comments,
non-canonical parenthesisation, literal spelling the AST does not keep (`0x1F` vs `31`, `1_000`, quote and escape
style, implicit concatenation, `{x=}` text), `Interactive`/`Expression`/`FunctionType` roots, deprecated node aliases
(`Num`, `Str`, `Index`, `ExtSlice`, `Suite`, `AugLoad` — never produced by a 3.8+ parser). 3.14 t-strings are out of scope.

---

## 10. Canonical form (so that `emit(parse(emit(x))) == emit(x)`)

The emitter is a pure function of the AST; `parse(emit(x))` reproduces the AST (§9); therefore the canonical text is a
fixed point. Rules:

**10.1 Layout.** §5.4. One statement per line; `{⏎` after a non-empty block header; `}` glued to the last statement;
`}⏎` unless followed by `}`/`else`/`elif`/`except`/`finally`; decorators adjacent to their `def`/`class`; no `;`; no
blank lines; no indentation; file ends without a trailing newline.

**10.2 Spacing.** A single space is written only when (a) both adjacent characters are word characters, (e) a keyword is followed by `{`, `-`, `+`, `~` or `*` (`in {1,2}`, `case -1`, `return *a,b`, `yield *a`, `lambda *,k:k`; the glue reads as an operator otherwise),
(`[\w]`, including string prefixes: `return f'x'`, `async def`, `is not`, `raise E from c`, `yield from`, `not x`,
`a in b`, `@dec def`), (b) a number ending in `.` is followed by a word character (`1. if`), (c) a word character is
followed by `.`+digit (`in .5`), or (d) the last character of one token and the first of the next would lex as a
different operator (`* *`→`**`, `/ /`, `< <`, `> >`, `= =`, `: =`, `- >`, `. .`, and any operator followed by `=`);
`a--b` needs no space because Python has no `--` operator. Consequences the parser accepts: `return.mean`, `if.count==1{`, `return'x'`,
`==''and`, `)as f{`, `yield''.join(buf)`, `not.x`. The `--pretty` option writes a space between a keyword and a following
`.`/quote (`return .mean`, `return 'x'`) at a measured +8 tokens / 1279 (+0.6%; +0.5% on the 469-file corpus); it is not canonical.

**10.3 Literals.** Floats: `repr(value)` then `X.0 → X.`, `0.Y → .Y` (`-0.5 → -.5`), exponent forms keep the mantissa
rule (`1e-05`, `1.5e+300`); `inf → 1e309`, `nan → (1e309-1e309)` (as `ast.unparse`). Ints decimal. Complex `1j`,
`(1+2j)` by precedence. Strings/bytes by `ast`'s quote selection (prefers `'`, switches to `"` to avoid escapes; triple
quotes for docstrings, exactly as `ast.unparse`). One deliberate deviation from `ast.unparse`: a string
that contains both quote kinds is written with triple quotes instead of backslash escapes (`'''it's "x"'''`
for `'it\'s "x"'`), which is fewer tokens and has no backslash noise; special whitespace is still escaped
(`'\n'`), so a non-docstring literal never contains a raw newline. f-strings as `ast.unparse` with PyDense fields.

**10.4 Structure.** `{}` for a `[Pass]` body (never `{pass}`); `pass` only when it is not the whole body. Tuples bare
where Python allows; `()` and `(a,)` otherwise. `elif` collapse as `ast.unparse`. Decorator chains unparenthesised,
`@(expr)` otherwise. Receiver dropped per §7. IfExp/Lambda parenthesised per §4.1. `(~x)` is not needed (no `~`
statement sigil). `(1).real` for numeric attribute receivers. Generator as sole argument without double parens.

**10.5 Modes** change only which nodes are present (§11), never the spelling of a node. One consequence: NODOC and
STRIPPED are idempotent except when a body has two leading string statements — dropping the first makes the second
the docstring of the re-encoded text, so the fixed point is reached after one more round (the AST is unchanged).

**10.6 Parenthesisation added by the shipped emitter** (all round-trip-neutral): a one-element tuple as `for` iterable
or `match` subject (`for x in (a,){`; a bare `a,{` would run the comma into the block), a `yield` as iterable, subject
or value of another yield (`for x in (yield){`, `yield(yield x)`), a dict/set display as an exception type
(`except({1}){`; a bare `{1}` would read as the handler body), an `IfExp` or `Lambda` inside a bare tuple
(`(c?a:b),d`), and a `Lambda` as ternary else-branch (`c?(lambda:1):(lambda:2)`). A bare `a[*idx]` is written for the
one-element starred subscript tuple.

---

## 11. Modes (lossless vs stripped)

| mode | flag | annotations | docstrings | AST equality target | lossy? |
|---|---|---|---|---|---|
| **FULL** (default) | — | kept | kept | `ast.parse(src)` exactly | **no** (AST-bijective) |
| **NODOC** | `--mode nodoc` | kept | dropped | `ast.parse(src)` minus the docstring `Expr` of every Module/ClassDef/FunctionDef (a body left empty becomes `[Pass]` in def/class, `[]` in Module) | yes, by exactly those nodes |
| **STRIPPED** | `--mode stripped` | param/return annotations dropped; `x:T=v → x=v` | dropped | annotation-stripped, docstring-stripped reference | yes |

Bare `x:T` (dataclass / Protocol / `__slots__`-style fields) is **kept** in STRIPPED mode: deleting it deletes a
statement and changes behaviour. Type parameters and `type` aliases are kept. Comments are not in the AST: they are
accepted in input and dropped in every mode (a future CST-based emitter may preserve them; the lexical grammar already
admits them so that would be backward compatible). `# type:` comments and `TypeIgnore` are dropped (allowed by the task).

---

## 12. Measurements and ablation

All counts: `ast.dump`-verified text, exact tiktoken. Baseline = `ast.unparse(ast.parse(sample))` of the 7 samples
(the 5 reference samples in `benchmarks/token_compression.py` + `textwrap.TextWrapper._wrap_chunks` +
`json.encoder.py_encode_basestring_ascii`/`JSONEncoder.default` extracted as module-level functions): **1865 o200k /
1839 cl100k with docstrings, 1550 / 1530 without.** The five reference samples are domain-neutral programs with the
same construct mix as the design-review set (a class with `__init__` and an updating method, a numpy/pandas
function, a frozen dataclass with a multi-default function, an async loader with try/except/with and a dict
comprehension, a decorator factory with star-arguments).

### 12.1 Headline (7 samples)

Figures in this subsection are produced by `benchmarks/token_compression.py` against the shipped implementation (the baseline
has no trailing newline). The micro-measurements and the
ablation ladder in §12.2–§12.4 are design-time figures made with the reference emitter of the design review; they differ from
the shipped emitter by a few tokens (e.g. `yield a,b` bare, `a**-b`, `a or b and c`, triple-quoted strings holding both quote kinds).

| mode | o200k | reduction | cl100k | reduction | baseline used |
|---|---|---|---|---|---|
| **FULL** (true AST bijection) | **1559** | **−16.41%** | **1529** | **−16.86%** | with docstrings (1865 / 1839) |
| **LOSSLESS-NODOC** | **1249** | **−19.42%** | **1225** | **−19.93%** | without docstrings (1550 / 1530) |
| LOSSLESS-NODOC vs verbatim with-doc baseline (the number v0.2 headlined) | 1249 | −33.03% | 1225 | −33.39% | 1865 / 1839 — the docstrings themselves are 16.9% of the baseline |
| **STRIPPED** | **1178** | **−24.00%** | **1158** | **−24.31%** | without docstrings |
| STRIPPED vs verbatim with-doc baseline | 1178 | −36.84% | 1158 | −37.03% | lossy; label as such |
| samples 1–5 only (the five reference samples) | 693 / 622 | −21.07% lossless-nodoc (878) / −31.80% stripped vs with-doc (912) | | | |

Per sample (o200k; cl100k): `py_doc py_nodoc FULL LOSSLESS STRIPPED`

| sample | o200k | cl100k |
|---|---|---|
| 1 RunningStats | 221 206 148 134 116 | 220 205 147 133 116 |
| 2 inverse_variance_weights | 210 191 175 157 148 | 206 187 173 155 147 |
| 3 plan_retry | 167 167 141 141 127 | 167 167 140 140 126 |
| 4 load_manifests | 145 145 122 122 107 | 144 144 120 120 105 |
| 5 with_multiplier / score_pipeline | 169 169 139 139 124 | 165 165 134 134 121 |
| 6 textwrap._wrap_chunks | 649 496 555 403 403 | 641 489 544 393 393 |
| 7 json.encoder (2 functions) | 304 176 279 153 153 | 296 173 271 150 150 |

### 12.2 Ablation ladder (7 samples, docstrings dropped on both sides; one notation added per rung)

| rung | o200k | Δ | cumulative | cl100k | cumulative |
|---|---|---|---|---|---|
| L0 `ast.unparse` | 1578 | — | 0.0% | 1559 | 0.0% |
| L1 remove optional whitespace (valid Python, 1-space indent) | 1432 | −146 | −9.25% | 1413 | −9.36% |
| L2 `{}` blocks, one statement per line, canonical layout | 1354 | −78 | −14.20% | 1335 | −14.37% |
| L2b (same with `;` and no newlines — the brace-block candidate's canonical form) | 1348 | | −14.58% | 1324 | −15.07% |
| L3 + `.x` and implicit receiver | 1328 | −26 | −15.84% | 1309 | −16.04% |
| L4 + `c?a:b` | 1323 | −5 | −16.16% | 1303 | −16.42% |
| L5 + `{}` for `pass` | 1323 | 0 (no empty bodies in samples; −2 per occurrence) | −16.16% | 1303 | −16.42% |
| **L6 + canonical floats = LOSSLESS-NODOC** | **1281** | −42 | **−18.82%** | **1261** | **−19.11%** |
| L7 + strip annotations = STRIPPED | 1209 | −72 | −23.38% | 1193 | −23.48% |

Variants of the final form (o200k, LOSSLESS-NODOC): `;`-separated single line 1283; newline-separated without `}⏎` 1279;
`--pretty` keyword spacing 1291; Python ternary everywhere 1288; explicit `self` everywhere 1306; `}else{→}:{` 1278;
`lambda→\` 1281 (0 lambdas in samples; 0 in every micro context). Implicit self contributes little here because 5 of
the 7 samples have no methods; on the corpus it is worth 1–3 points (§12.5).

### 12.3 Micro-measurements behind each kept / rejected notation (o200k / cl100k)

| construct | Python spelling | tokens | PyDense spelling | tokens | verdict |
|---|---|---|---|---|---|
| method header | `def update(self,value){` | 6 | `def update(value){` | 4 | keep implicit self |
| self attribute | `return self.mean,vol}` | 6 | `return.mean,vol}` | 5 | keep `.x` (`return .mean` = 6) |
| if on attribute | `if self.count==1{` | 6 | `if.count==1{` | 5 | keep |
| classmethod | `@classmethod def make(cls,x){…}` | 11 | `@classmethod def make(x){…}` | 10 | **adopt** implicit `cls` (from the lenient-input candidate) |
| escape hatch | `def!f(this,x){` 13 / `def!f(){` 11 / `def!f(*a){` 12 | | `def f(.this,x){` 13 / `def f(.){` 11 / `def f(.,*a){` 13 | | keep `def!` (ties or wins) |
| constructor | `def __init__(a,b=1){` | 16 (in class) | `@i(a,b=1){` (sigil candidate) | 13 | **reject** (invented, collides with `@i` decorator; 1 construct) |
| ternary | `vol=math.sqrt(.var) if .count>=.min_p else 0.` | 18 | `vol=.count>=.min_p?math.sqrt(.var):0.` | 15 | keep `?:` (`??` also 15: second `?` buys nothing) |
| ternary (short) | `x=a if c else b` | 6 | `x=c?a:b` | 4 | |
| floats | `x=1.0;y=0.5;z=0.0` | 16 / 15 | `x=1.;y=.5;z=0.` | 12 / 11 | keep |
| empty body | `class A{pass}` | 5 | `class A{}` | 3 | keep |
| lambda | `key=lambda t:t[1]`, `sorted(xs,key=lambda p:p.name)`, `map(lambda x:x*2,xs)`, `f=lambda a,b:a+b`, `default_factory=lambda:[]`, `f(lambda:1,2)`, `field(default_factory=lambda:{})`, `return lambda x:x+n` | 9 8 9 6 5 7 6 5 | same with `\` | 9 8 9 6 5 7 6 5 | **reject `\`** (exactly 0 in 8/8; collides with line continuation) |
| else | `if a{x=1}else{x=3}` / `.s=w` body / `return` body / `indent=` body | 10 12 10 16 | `}:{` forms | 10 11 10 15 | **reject `}:{`** (0–1 per else; −3 on samples) |
| not | `if not x{` / `if not isinstance(x,int){` | 4 / 6 | `if !x{` / `if !isinstance(x,int){` | 4 / 7 | keep `not` |
| and | `if a and b{` | 5 | `if a&&b{` | 5 | keep `and` |
| for | `for x in y{f(x)}` | 8 | `~x:y{f(x)}` | 7 | keep `for` (−1 but alien; `~i,v:enumerate(xs){` is +1) |
| import alias | `import numpy as np` | 4 | `import numpy=np` | 3 | keep Python (−1, invented) |
| from import | `from pathlib import Path` | 4 | `from pathlib:Path` | 4 | keep Python |
| with | `with open(p)as f{` | 7 | `with open(p):f{` | 6 | keep Python (rated the most error-prone sigil in the design review) |
| return | `return x` / `{return x}` | 2 / 3 | `^x` / `{^x}` | 2 / 4 | keep `return` |
| colon habit | `if x:{a()}` / `def f(a):{return a}` | 5 / 8 | `if x{a()}` / `def f(a){return a}` | 5 / 7 | accept, not canonical |
| separators | `x=1;y=2` | 6 | `x=1⏎y=2` | 7 | micro favours `;`, whole samples favour `⏎` (1279 vs 1283); `⏎` canonical |
| `}` continuation | `}else{` 10 vs `}⏎else{` 11 ; `}elif` 12 = `}⏎elif` 12 ; `}except` 9 = 9 ; `}finally` 8 = 8 ; `}case` 16 = 16 ; `}x` 8 = `}⏎x` 8 ; `}}` 9 = `}⏎}` 9 ; `}def` 11 vs `}⏎def` 10 | | | | glue only `else`; newline elsewhere |
| `{` newline | `def f(a){return a}` 7 / `def f(a){⏎return a⏎}` 8 (the `⏎}` costs) ; `class A{⏎def…` = `class A{def…` | | | | `{⏎` free, `⏎}` +1 |
| decorators | `@property@abstractmethod def x(){…}` 11 / `@dataclass(frozen=True)class A{` 11 / `@functools.cache def f` 12 | | newline-separated 13 / 11 / 13 | | adjacent canonical |
| `*Ts` default | `class A[*Ts=*tuple[int]]{}` | 9 | | | in grammar |
| Unicode | `π=3.14159` 6, `変数=1` 4/5 | | | | accepted |
| line join | `x=a+\⏎b` | 5 | `x=a+b` | 3 | accepted, never emitted |
| f-string field | `f'{self.x}'` | 6 | `f'{.x}'` | 6 | same count; `.x` kept for consistency (`{.x!r:>10}` is unambiguous) |

Previously rejected with numbers (design-phase evidence log, summarised in `docs/PRIOR_ART.md` §5): all `#`/`%` macros (+35 tokens on the samples), `@f`/`@c`
(+10), `^>` `^!` `^~` `^@` `@aw` `@in` `@is` `@w` `~?` `>pkg` (+1 to +3 each), `$n` positional (−3 on short functions,
+6 on sample 6, semantically fragile), `===`/`!==` (−2, equality-confusion risk), identifier-dictionary prelude (never
pays), `;` after every `}` (+13), `return` always `^` (+5).

### 12.4 Why keywords beat sigils (tokenizer mechanics, measured)

o200k's pre-tokenizer (`[^\r\n\p{L}\p{N}]?\p{L}+`) lets **one** leading punctuation character or a space attach to a
word: `def update` → `def`,` update`; `.mean` → `.mean`; `(a` → `(a`; but `@f update(` → `@`,`f`,` update`,`(` because the
space takes the prefix slot, and `!isinstance` → `!`,`is`,`instance` because the sigil breaks a vocabulary word.
Punctuation runs merge until a letter/digit: `){` `:{` `};` `}}` `}else`(!) `()}` `){⏎` `}⏎` are single tokens, `}}}` is 2.
`\s+(?!\S)` makes newline+indent exactly 2 tokens at any depth, so braces beat indentation by ~1 token per line and
`⏎` without indentation equals `;`.

### 12.5 Corpus (469 files = 148 CPython 3.13 stdlib modules + 321 site-packages modules; 12,508 top-level statements)

Shipped implementation (`pydense.encode`, 469/469 files AST-identical in FULL and NODOC, STRIPPED idempotent), o200k (cl100k):

| corpus | baseline with doc | baseline no doc | python-minifier (vs with-doc) | **FULL** (vs with-doc) | **NODOC** (vs no-doc) | STRIPPED, lossy (vs with-doc / no-doc) |
|---|---|---|---|---|---|---|
| stdlib, 148 files, 5,510 stmts | 952,530 (944,074) | 718,852 (710,985) | 885,071 **−7.08%** (−7.41%) | 826,605 **−13.22%** (−13.59%) | 596,269 **−17.05%** (−17.58%) | 595,582 −37.47% / −17.15% (−38.00%) |
| site-packages, 321 files, 6,998 stmts | 1,253,450 (1,253,430) | 918,110 (919,705) | 1,172,830 **−6.43%** (−6.62%) | 1,113,884 **−11.13%** (−11.31%) | 781,270 **−14.90%** (−15.12%) | 702,496 −43.96% / −23.48% (−43.99%) |
| **all 469 files** | 2,205,980 (2,197,504) | 1,636,962 (1,630,690) | 2,057,901 **−6.71%** (−6.96%) | 1,940,489 **−12.04%** (−12.29%) | 1,377,539 **−15.85%** (−16.19%) | 1,298,078 −41.16% / −20.70% (−41.41%) |

`--pretty` costs +0.53% on the corpus.

**Design-time measurement** (the reference emitter of the design review, not the shipped `pydense.encode`; kept as
the record the grammar decisions were made on). Fidelity (oracle §17.3, through the reference parser with the §6.6
import rule): **FULL 469/469, NODOC 469/469**. Emit 121 s, parse 8 s for 2.2M tokens.

| corpus | baseline (ast.unparse, with doc) | no-doc baseline | python-minifier whitespace-only | **FULL** | **LOSSLESS-NODOC** (vs no-doc) | **STRIPPED** (vs with-doc / vs no-doc) |
|---|---|---|---|---|---|---|
| stdlib, 148 files, 5,510 stmts | 952,530 o / 944,074 c | 718,852 / 710,985 | 885,132 (−7.08%) / 874,215 (−7.40%) | 826,103 (**−13.27%**) / 815,272 (−13.64%) | 595,767 (**−17.12%**) / 585,522 (−17.65%) | 595,080 (−37.53% / −17.22%) / 584,835 (−38.05%) |
| site-packages, 321 files, 6,998 stmts (requests, urllib3, pip, setuptools, click, httpx, werkzeug, …) | 1,253,450 / 1,253,430 | 918,110 / 919,705 | 1,172,836 (−6.43%) / 1,170,474 (−6.62%) | 1,108,884 (**−11.53%**) / 1,106,875 (−11.69%) | 776,270 (**−15.45%**) / 775,877 (−15.64%) | 698,605 (−44.27% / −23.91%) / 698,470 (−44.28%) |
| **all 469 files, 12,508 stmts** | 2,205,980 / 2,197,504 | 1,636,962 / 1,630,690 | 2,057,968 (−6.71%) / 2,044,689 (−6.95%) | 1,934,987 (**−12.28%**) / 1,922,147 (**−12.53%**) | 1,372,037 (**−16.18%**) / 1,361,399 (**−16.51%**) | 1,293,685 (**−41.36%** / −20.97%) / 1,283,305 (−41.60%) |

(o = o200k, c = cl100k.) LOSSLESS-NODOC measured against the with-doc baseline is −37.80% o200k — the figure the
earlier designs headlined; 21.6 points of it is docstring removal. Implicit `self` and `.x` are worth more on
OO-heavy application code than on this library corpus (the design review measured −18.3% on an OO-heavy stdlib subset).

python-minifier is run in whitespace-only mode (lossless, one-way) on the same files; its published −21% figure is
against *raw source including comments*, the `ast.unparse` baseline here already has comments removed, which is the
fair comparison for an AST-level encoding.

### 12.6 Fixed per-session cost

The cheat sheet in §15 (`pydense.CHEATSHEET`) is **418 o200k tokens**. At the shipped corpus rate (−15.85%
lossless-nodoc) it pays for itself after ~2.6k baseline tokens read or written; at the FULL rate (−12.04%) after
~3.5k. The v0.2 SKILL.md was 1279 tokens.

---

## 13. Diagnostics and lint rules

Errors carry `line:col`, the offending token and a one-line hint so a model can repair in one retry:

| situation | message |
|---|---|
| EOF with open blocks | `E001 unexpected end of input: 2 unclosed '{' (opened at 3:17 and 9:4)` — the dominant generation failure; always reports the position of each unmatched `{` |
| `}` with no open block | `E002 unmatched '}' at 12:1` |
| two simple statements without separator | `E003 expected newline, ';' or '}' before NAME 'y' at 4:9` |
| non-chain decorator | `E004 decorator must be a name/attribute/call/subscript chain; write @(a or b)` |
| ternary in f-string field | `E005 ':' here starts a format spec; parenthesise the ternary: f'{(c?a:b)}'` |
| stray `\` | `E006 '\' is only a line continuation` (a `\` glued to a name or `:`, i.e. the v0.2 lambda, is `E008 ... write lambda`) |
| `def!` outside a class | `E007 'def!' is only meaningful for methods` |
| v0.2 or candidate-design sigil at statement start (`?x{`, `~x:y{`, `^x`, `@f`, `@c`, `@i(`, `!E:e{`) | `E008 PyDense uses Python keywords: write if/for/return/def/class/__init__/except` |
| mixed `except` / `except*` | `E009 all handlers of a try must be except or except*` |

Warnings (lint, parse succeeds):

| id | trigger | why |
|---|---|---|
| W001 | a statement starting with `.NAME(` or `.NAME[` directly after a statement whose last token is `)` or `]` | `foo()⏎.bar()` is two statements (`self.bar()`); probably a split call chain — bracket it |
| W002 | class-level `def` (not `def!`) whose first written parameter is one of `this mcs metacls meta klass kls that me obj` | `self` would be injected in front of it; write `def!` or rename |
| W003 | `else`/`elif`/`except`/`finally` after a `}` that closed a display, not a block | impossible in valid input; points at the real error |
| W004 | `;` after `}` or before `}` | tolerated, not canonical |
| W005 | depth-0 newline immediately followed by a binary operator (`⏎+b`) | Python would also read this as a new statement (`+b` unary); probably a split expression |

---

## 14. Rosetta stone

| Python | PyDense (canonical) | tokens o200k (py → dpy) |
|---|---|---|
| `x = 1` / `a = b = c` | `x=1` / `a=b=c` | 4 → 3 / 5 → 3 |
| `x: int = 5` ; `x: int` ; `(x): int` | `x:int=5` ; `x:int` ; `(x):int` | 6 → 4 |
| `f(a, b)` / `{k: v}` | `f(a,b)` / `{k:v}` | 5 → 4 / 4 → 3 |
| `if a:` ⏎ `    x = 1` ⏎ `elif b:` ⏎ `    x = 2` ⏎ `else:` ⏎ `    x = 3` | `if a{` ⏎ `x=1}elif b{` ⏎ `x=2}else{` ⏎ `x=3}` | 25 → 19 |
| `for i, v in enumerate(xs):` ⏎ `    if v < 0: continue` ⏎ `    total += v` ⏎ `else:` ⏎ `    done = True` | `for i,v in enumerate(xs){` ⏎ `if v<0{` ⏎ `continue}` ⏎ `total+=v}else{` ⏎ `done=True}` | 29 → 22 |
| `while chunk := f.read(8):` ⏎ `    buf.append(chunk)` | `while chunk:=f.read(8){` ⏎ `buf.append(chunk)}` | walrus needs no parentheses in a header |
| `try:` … `except (ValueError, TypeError) as e:` … `else:` … `finally:` … | `try{` ⏎ `risky()}except(ValueError,TypeError)as e{` ⏎ `log(e)` ⏎ `raise}else{` ⏎ `ok=True}finally{` ⏎ `close()}` | 35 → 28 |
| `try: ...` ⏎ `except* OSError as eg: pass` | `try{` ⏎ `...}except*OSError as eg{}` | |
| `with open(p) as f, lock:` ⏎ `    data = f.read()` | `with open(p)as f,lock{` ⏎ `data=f.read()}` | 15 → 13 |
| `class A:` ⏎ `    def __init__(self, a, b=1):` ⏎ `        self.a = a; self.b = b` ⏎ `    def total(self):` ⏎ `        return self.a + self.b` | `class A{` ⏎ `def __init__(a,b=1){` ⏎ `.a=a` ⏎ `.b=b}` ⏎ `def total(){` ⏎ `return.a+.b}}` | 40 → 26 |
| `@classmethod` ⏎ `def make(cls, x): return cls(x)` | `@classmethod def make(x){` ⏎ `return cls(x)}` | 14 → 10 |
| `@staticmethod` ⏎ `def s(x): return x` | `@staticmethod def s(x){` ⏎ `return x}` | |
| `@property` ⏎ `@abstractmethod` ⏎ `def p(self): return self._p` | `@property@abstractmethod def p(){` ⏎ `return._p}` | |
| `def __new__(cls, *a): ...` (in class) | `def __new__(cls,*a){` ⏎ `...}` | |
| `def f(this, x): return this.x` (in class) | `def!f(this,x){` ⏎ `return this.x}` | 10 → 10 |
| `def f(a, b=1, /, c=2, *d, e, f=3, **g) -> None: pass` | `def f(a,b=1,/,c=2,*d,e,f=3,**g)->None{}` | 31 → 23 |
| `async def main():` ⏎ `    async with sess as s:` ⏎ `        async for x in s.stream():` ⏎ `            await handle(x)` | `async def main(){` ⏎ `async with sess as s{` ⏎ `async for x in s.stream(){` ⏎ `await handle(x)}}}` | 24 → 22 |
| `def gen():` ⏎ `    yield 1; yield from other(); x = yield; return x` | `def gen(){` ⏎ `yield 1` ⏎ `yield from other()` ⏎ `x=yield` ⏎ `return x}` | 21 → 18 |
| `raise ValueError("bad") from exc` | `raise ValueError('bad')from exc` | 8 → 8 |
| `assert x > 0, "msg"; del a[0], b.c; global g; nonlocal n` | `assert x>0,'msg'` ⏎ `del a[0],b.c` ⏎ `global g` ⏎ `nonlocal n` | |
| `import numpy as np` ⏎ `from ..pkg.mod import thing as t, other` ⏎ `from . import x` | `import numpy as np` ⏎ `from ..pkg.mod import thing as t,other` ⏎ `from . import x` | 20 → 20 (imports are already minimal) |
| `match cmd.split():` ⏎ `    case [action]: go(action)` ⏎ `    case Point(x=0, y=0) \| Point(x=1): origin()` ⏎ `    case {"k": v, **rest}: use(v)` ⏎ `    case [first, *others] if len(others) > 1: many()` ⏎ `    case str() as s: text(s)` ⏎ `    case 1 \| -2 \| 1+2j \| "s" \| None: lit()` ⏎ `    case _: pass` | `match cmd.split(){` ⏎ `case[action]{` ⏎ `go(action)}` ⏎ `case Point(x=0,y=0)\|Point(x=1){` ⏎ `origin()}` ⏎ `case {'k':v,**rest}{` ⏎ `use(v)}` ⏎ `case[first,*others]if len(others)>1{` ⏎ `many()}` ⏎ `case str()as s{` ⏎ `text(s)}` ⏎ `case 1\|-2\|1+2j\|'s'\|None{` ⏎ `lit()}` ⏎ `case _{}}` | 109 → 84 |
| `type Alias[T: int, *Ts, **P] = dict[T, P]` | `type Alias[T:int,*Ts,**P]=dict[T,P]` | |
| `class Box[T](Generic[T]):` ⏎ `    def get[U](self, default: U = None) -> T \| U: return self.item` | `class Box[T](Generic[T]){` ⏎ `def get[U](default:U=None)->T\|U{` ⏎ `return.item}}` | 30 → 24 |
| `y = a if c else b` ; `y = a if c else (d if e else f)` | `y=c?a:b` ; `y=c?a:e?d:f` | 7 → 4 |
| `f(lambda: 1, key=lambda x: x[1])` | `f(lambda:1,key=lambda x:x[1])` | 14 → 11 |
| `y = [x * 2 for x in it if x > 0 if x < 9]` ; `{k: v for k, v in d.items() if v is not None}` ; `(x async for x in aiter())` | `y=[x*2 for x in it if x>0 if x<9]` ; `{k:v for k,v in d.items()if v is not None}` ; `(x async for x in aiter())` | 22 → 18 (first item) |
| `f(*a, *b, **c, k=1)` ; `a[1:2], a[::2], a[1:2, 3], a[...], a[*idx]` | `f(*a,*b,**c,k=1)` ; `a[1:2],a[::2],a[1:2,3],a[...],a[*idx]` | |
| `(), (1,), [], {}, {1}, {*()}, {**a, 'b': 1}` | `(),(1,),[],{},{1},{*()},{**a,'b':1}` | |
| `1j, 0x1F, 1_000_000, 1e-5, 0.5, 100.0, -0.5, 1.0 .real` | `1j,31,1000000,1e-05,.5,100.,-.5,(1.).real` | |
| `b"\x00", rb"raw", u"uni", "a" "b"` | `b'\x00',b'raw',u'uni','ab'` | |
| `f"{x!r:>{w}.{p}f} {d['k']} {y=} {{lit}}"` ; `f"{self.name}: {a if c else b}"` | `f"{x!r:>{w}.{p}f} {d['k']} y={y!r} {{lit}}"` ; `f'{.name}: {(c?a:b)}'` | |
| `y = not a and not (b or c)` ; `(a or b) and c` ; `(-a) ** 2` ; `-a ** 2` ; `a < b <= c != d` ; `a not in b is not c` | `y=not a and not(b or c)` ; `(a or b)and c` ; `(-a)**2` ; `-a**2` ; `a<b<=c!=d` ; `a not in b is not c` | |
| `if x in {1, 2}: pass` ; `if x == {1}: go()` | `if x in {1,2}{}` ; `if x=={1}{` ⏎ `go()}` | 12 → 9; no parentheses needed |
| `s[1:-1 if n > 2 else None]` ; `{(a if c else b): v}` | `s[1:(n>2?-1:None)]` ; `{(c?a:b):v}` | parenthesised by the emitter; `s[1:n>2?-1:None]` also parses |

**Sample 1, LOSSLESS-NODOC (134 o200k tokens vs 206; FULL 148 vs 221):**
```
import math
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
return.mean,deviation}}
```
**Sample 4 (async, try/except, with, dict-comp, f-string), LOSSLESS (122 vs 145):**
```
import asyncio
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
return merged}
```
**Sample 5 (closures, decorators, star-args, ternaries), LOSSLESS (139 vs 169):**
```
def with_multiplier(scale:float=1.){
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
return clamped?sum(clamped)/len(clamped)*w_sum:0.}
```
The other samples are written by `python benchmarks/token_compression.py --dump DIR` as `sN.{full,nodoc,stripped}.dpy`.

---

## 15. Cheat sheet for LLMs (418 o200k tokens)

The source of truth is `pydense.skill.CHEATSHEET` (`pydense/skill.py`), shipped verbatim as `pydense.CHEATSHEET`, returned by the MCP tool `get_dpy_cheatsheet`, printed by `pydense skill` and written as the first section of `SKILL.md` by `pydense init-skill`. The text below is that string; any change must be made there and re-measured (`tests/test_tokens.py`).

> # PyDense (.dpy) — how to write it
>
> PyDense is Python with whitespace removed. Keep every keyword, operator, literal, import, decorator, comprehension, pattern and f-string exactly as in Python. Only five things change:
>
> 1. **Blocks** are `{...}`, one statement per line (or `;`); after `}` only `elif`/`else`/`except`/`finally`; empty body `{}`.
>    `if c{a}elif d{b}else{e}` `for x in y{}` `while c{}` `try{}except E as e{}finally{}` `with a as b{}` `def f(x)->T{}` `class A(B){}` `match x{case p{}}`
> 2. **No optional spaces**: `x=1` `f(a,b)` `{k:v}` `x:int=5`. One space only between two words (`return x`, `a in b`).
> 3. **`.x` means `self.x`**, and methods omit the receiver: `def update(value){.count+=1}`. `@classmethod def make(x)` gets `cls`; `@staticmethod` is untouched. Explicit `self`/`cls` is fine (`def __new__(cls,*a)` stays). First parameter not a receiver, or none: `def!f(this,x){}`.
> 4. **Ternary** `c?a:b` = `a if c else b` (Python form accepted). Parenthesize it in a slice bound, dict key or f-string field: `f'{(c?a:b)}'`.
> 5. **Floats** shortest: `1.` `.5` `0.` (`1.0` accepted).
>
> Traps: decorators and `def` on one line (`@a@b def f(){`); a decorator that is not a `name.attr(args)` chain is `@(expr)`. Never split a call chain across lines without parentheses. Balance every `{`.

---

## 16. Writability risks and mitigations

| risk | mitigation |
|---|---|
| C-order ternary `c?a:b` vs Python order | Python form accepted; emitter canonicalises |
| `return.mean`, `if.count==1{`, `return'x'`, `)as f{` look odd | all accepted with spaces (`--pretty` emits them, +0.6%) |
| forgetting `;` between two statements on one line | one statement per line is canonical and free, so natural line-based output works; error E003 names the token |
| `foo()⏎.bar()` silently = `self.bar()` | emitter never splits chains; W001 flags the pattern; invalid Python anyway so no valid program is misread |
| `def f(this,x)` in a class gains `self` | W002 on receiver-like names; `def!` is the escape; writing `self` explicitly is always right |
| `def` nested in `if`/`try` in a class body gets `self` | correct Python semantics; explicit `self` accepted |
| `{}` is an empty block after a header and an empty dict elsewhere | same position rule as C/JS; unambiguous (§6.1) |
| `1.` / `.5` floats | legal Python; `1.0` accepted |
| ternary / lambda inside an f-string field | E005 with the fix; same trap Python has for `lambda` in f-strings |
| exotic decorators | `@(expr)`; E004 says so |
| unbalanced braces (dominant generation failure) | E001 lists every unmatched `{` with its position; brace balance is the TOON-style truncation guardrail |
| comments lost on round trip | accepted on input; documented; CST emitter is the planned extension |
| non-ASCII identifiers | lexer uses `str.isidentifier` (PEP 3131) |
| residual learning load | 5 deltas, 418-token sheet; everything else is Python |

---

## 17. Conformance and CI gates for the implementation

1. `emit: ast.Module → str` as `Emitter(mode, pretty)`, a subclass of `ast._Unparser` (inherits precedence/quoting);
   `mode` selects FULL/NODOC/STRIPPED (§11) and `pretty` the keyword spacing of §10.2. There are no per-notation
   ablation flags in the shipped emitter; the ablation ladder of §12.2 is a design-time record.
2. `parse: str → ast.Module` hand-written lexer (nested f-strings, Unicode names, `nl_before` on every token) +
   recursive-descent/Pratt parser building `ast` nodes directly (no intermediate Python text); ≤2-token lookahead
   except §6.7 speculation; every error with line:col + hint; W001–W005 lint.
3. Oracle: `ast.dump(parse(emit(src))) == ast.dump(ast.parse(src))` in FULL mode, and the mode-adjusted references in
   NODOC/STRIPPED, over (a) the stdlib corpus of `benchmarks/corpus_fidelity.py` (the 469-file design-time corpus
   added 321 site-packages files that are not shipped), (b) the whole installed stdlib (`PYDENSE_FULL_CORPUS=1`
   in `tests/test_corpus.py`), (c) the union of the three candidate designs' edge batteries (edge cases, the
   170-construct matrix, 54 programs), (d) the review batteries (adversarial file, 549-case battery incl.
   `type X[*Ts=*tuple[int]]`, `π=1`, `x=a not b` hang probe with a timeout, 46-slip writability battery and 6-case
   one-statement-per-line OO test). (c) and (d) are checked in under `tests/batteries/` and run by
   `tests/test_roundtrip_batteries.py`.
   Required: 100% in every mode, no parse longer than 1 s per file.
4. Idempotence: `emit(parse(emit(x))) == emit(x)` on the whole corpus.
5. Token regression: the headline table (§12.1) regenerates from `benchmarks/token_compression.py` and the corpus
   table (§12.5) from `benchmarks/token_compression.py --corpus stdlib` / `benchmarks/corpus_fidelity.py`; any notation change must re-prove its delta on o200k **and** cl100k before merge. README/SKILL lead
   with the FULL and LOSSLESS-NODOC figures, state the docstring share of any with-doc figure, and label STRIPPED lossy.
6. Lenient-input battery (must parse, AST-identical): `a if c else b`; `lambda`; explicit `self`/`cls`; `self.x`;
   `1.0`; `{pass}`; `;` after `}`; `;}`; `if x:{`, `else:{`, `def f():{`; newline before `{`/`}`/`else`; comments;
   `\`⏎ continuation; `@a⏎@b⏎def`; `with(a as b){`; `import a⏎.x=1` (two statements); `f(x for x in y)`; `{x=}` f-string.
7. Rejected-input battery (must error with E008): `?x{`, `~x:y{`, `^x`, `@f f(){`, `@c A{`, `@i(x){`, `!E:e{`,
   `#T`, `%p(`, `$0`, `\x:x`, `c??a:b`, `import a=b`, `from m:a`, `&&`, `||`, `}:{`.

---

## 18. Summary of guarantees

* **Lossless**: FULL mode is an exact AST bijection for all of Python 3.10–3.13 module source (§9), verified on
  12,508 top-level statements; what is lost is exactly what `ast.unparse` loses (comments, formatting, literal spelling).
* **Deterministic**: hand-written recursive descent, ≤2-token lookahead except the `match` soft keyword (bounded
  speculation identical to CPython's), explicit disambiguation rules (§6), canonical form that is a fixed point (§10).
* **Measured**: samples −16.4% FULL / −19.4% LOSSLESS-NODOC / −24.0% STRIPPED (−36.8% vs the with-doc baseline);
  469-file corpus −12.04% FULL / −15.85% LOSSLESS-NODOC / −41.16% STRIPPED (vs with-doc, lossy), vs −6.71% for
  python-minifier on the same files (o200k; cl100k within 0.4 pt everywhere); every notation justified by a tiktoken count and every rejected one
  listed with its number (§12).
* **Writable**: Python plus five deltas, 418-token cheat sheet, every replaced Python spelling accepted on input,
  actionable errors and a brace-balance guardrail.
