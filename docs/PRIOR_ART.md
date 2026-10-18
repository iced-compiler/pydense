# PyDense prior-art survey: token-efficient / compressed / minified code for LLM agents

Compiled 2026-10-18 for the PyDense redesign. Every token count in this document is a real tiktoken
measurement (o200k_base primary, cl100k_base secondary) made with
`python3.13`, or a number quoted from the cited source with its
tokenizer named. The measurements that drove the final grammar are reproduced by `benchmarks/token_compression.py`
and `benchmarks/corpus_fidelity.py`; the figures in §12 of `docs/SPEC.md` supersede the survey-time ones below.

---

## 0. Executive summary

1. **The field has converged on the same conclusion PyDense's own measurements reached: syntax-level
   rewrites of Python are worth 10-20%, not 50%.** SimPy (ISSTA'24) measures 10.4% on GPT-4's
   tokenizer and 13.5% on CodeLlama's; Token Sugar (ASE'25) 12.9-15.1%; ShortCoder 18.1% (output
   tokens, after fine-tuning); the ICSE'26 formatting study finds only 4.0-6.5% from stripping Python
   whitespace vs 25-35% for brace languages. GlyphLang's "45% fewer than Python" was retracted to 35%
   after an HN commenter re-ran tiktoken.
2. **Off-the-shelf python-minifier already captures most of the lossless win.** Measured here on 150
   CPython stdlib files (1.06M o200k tokens): whitespace-only minification (comments dropped, nothing
   renamed or removed) = **-21.3% o200k / -21.7% cl100k with 0 failures**. Dropping docstrings and
   annotations = -36.1%; everything incl. global renaming = -37.7%. PyDense v0.2 reaches 37.1% on the
   same corpus while corrupting 42% of statements, i.e. it currently adds nothing over `pyminify`.
3. **The remaining lossless headroom after minification is bounded.** In minified stdlib output,
   pure-whitespace tokens are 6.8% of all tokens and newline-bearing tokens 4.4%; `self`/` self`
   tokens are 1.1% (undercount: `(self` merges). So brace-blocks + `;` can add roughly 4-7 points and
   implicit self 1-3 points (more on OO-heavy code). A realistic, honest lossless target for PyDense
   is **~25-30% on real code, ~40-50% only when comments/docstrings/annotations are stripped (lossy
   mode)**. The README's "~50%" claim needs to be re-scoped to the lossy mode.
4. **Alien sigils are the documented failure mode.** Token Sugar shows GPT-4.1 Pass@1 collapsing
   from 94.5% to 51.2% on sugared code without training (54.9% with in-prompt examples). SimPy's
   authors added 78 new vocabulary tokens and did continued pre-training; SimPy-only training lagged
   the Python control on 2 of 3 models. GlyphLang's HN thread and Jason Hall's TBIR experiment (Claude
   spontaneously replaced symbol opcodes with English keywords) reach the same conclusion. PyDense
   cannot fine-tune frontier models, so it must stay inside the token-vocabulary and syntax
   distribution the models already know: Python keywords, braces, semicolons, `.attr`.
5. **Nobody owns the "lossless, bijective, agent-writes-dense / repo-stays-clean" niche.** SimPy's
   DualCode describes exactly this architecture but shipped no tool; the ICSE'26 study built a
   bidirectional formatter but only for whitespace; python-minifier is one-way; TOON does it for
   JSON, not code; Aider/Headroom/lean-ctx are lossy skeletonizers for reading only. A production
   `.py <-> dense` bijection with an MCP write-dense/commit-clean loop, measured honestly, is the
   open position.
6. **Tokenizer facts that must drive the grammar** (measured, o200k; cl100k agrees unless noted):
   `\n` + any indent = exactly 2 tokens at every depth (`'\n', '   ', ' x'` - the 4th space merges into
   the identifier); one tab indent = 1 token (`'\tx'`), two tabs = 2; `;`=1, `{`=1, `){`=1, `:{`=1,
   `}}`=1, `}}}`=2 (cl100k: 1), `};`=1; `.value`=1 after punctuation but `return .value`=3 (`' .'`
   splits) vs `return self.value`=3 - so `.x` only saves when preceded by `=`,`(`,`+`,`;`,`{`, not
   after a space-separated keyword; `x if c else y`=5 vs `c?x:y`=4 (the second `?` in `??` buys
   nothing); `a and not b`=4 vs `a&&!b`=3; `!x`=2 = `not x`=2 (no gain); `x!=None`=3 = `x is None`=3.

---

## 1. Minifiers (Python, non-LLM origin)

### 1.1 python-minifier (dflook) - https://github.com/dflook/python-minifier , docs https://dflook.github.io/python-minifier/
- **What it does.** AST-based (parses with the running interpreter, has its own printer). Transforms:
  Combine Imports, Remove Pass, Hoist Literals, Remove Annotations, Rename Locals, Remove Object
  Base, Convert Positional-Only Arguments to Arguments, Preserve Shebang, Remove Explicit Return
  None, Remove Builtin Exception Brackets, Constant Folding, Remove Dead Branches, Remove Literal
  Statements (docstrings), Rename Globals, Remove Asserts, Remove Debug, Prefer Single Line.
  Output uses tab indentation and `;`-joined simple statements; always strips comments and optional
  whitespace. Supports Python 2.7 and 3.3-3.15. Built for AWS CloudFormation's 4 KiB inline-Lambda
  limit, i.e. optimizes *bytes*, not tokens.
- **Measured savings (this survey, 150 stdlib files, o200k/cl100k).** Whitespace-only -21.3%/-21.7%
  (chars -31.6%); defaults (rename locals, hoist) -21.9%/-22.3%; + remove docstrings + annotations
  -36.1%/-36.6%; + rename globals/asserts/debug -37.7%/-38.1% (chars -52.5%). 0 parse failures in
  every configuration. Renaming locals buys only +0.6 token points despite -5 char points, because
  short identifiers are already 1 token.
- **Relevance.** This is the bar to beat and the obvious thing a reviewer will run. It is also a
  candidate *dependency or reference implementation* for PyDense's whitespace/hoisting passes.
- **Differentiation.** python-minifier is one-way (no decompile), keeps Python's newline+indent
  structure (2 tokens per line), keeps `self`, and its lossy transforms are not reversible.
  PyDense's edge must be: (a) bijective round-trip with proof (ast.dump equality), (b) brace/`;`
  blocks that remove the per-line 2-token tax, (c) implicit self, (d) a decompiler for reading,
  (e) the MCP workflow. Target: beat -21% losslessly and match -37% in lossy mode with 100% fidelity.

### 1.2 pyminifier (liftoff) - https://github.com/liftoff/pyminifier , docs https://pythonhosted.org/pyminifier/
- **What it does.** Tokenize-module-based minifier + obfuscator (`-O` renames classes/functions/
  variables) + optional gzip/bz2/lzma self-extracting container (pyminifier3 fork). GPLv3. Example:
  tumult.py 1358 -> 640 bytes. Last push 2023, 110 open issues; known gaps: no identifier exclusion,
  no config, no de-obfuscation map.
- **Measured savings.** Bytes only; none in tokens. Obfuscation is irreversible.
- **Relevance / differentiation.** Shows the risk of token-stream rewriting without a real parser
  (same architecture class as PyDense v0.2's regex lexer, same corruption class). PyDense should move
  to an `ast`-driven compiler/decompiler and keep a reversible name map if it ever renames.

### 1.3 kakn/python-code-minifier - https://github.com/kakn/python-code-minifier
- **What it does.** Explicitly for "LLM token limits": strips docstrings/comments/blank lines/type
  hints/error handling/assertions/decorators, shortens names, `--structure-only` keeps signatures.
  Presets `--safe`, `--moderate`, `--extreme`. One commit; no measurements; lossy and irreversible;
  removing `try/except` changes semantics.
- **Relevance.** Evidence that users want exactly this knob set, and that the naive approach is lossy.
  PyDense should offer the same presets but keep them in a *separate, explicitly lossy* "strip" layer
  on top of a lossless core.

### 1.4 "Code Tabification" (Qodo/CodiumAI blog, 2023) - https://www.qodo.ai/post/reduce-your-costs-by-30-when-using-gpt-3-for-python-code
- **Claim.** Replacing 4-space indentation with tabs cut one class from 215 to 151 GPT-3 tokens (~30%).
- **Measured here.** On o200k/cl100k the same trick is **-0.5% / -0.6%** (slightly *negative*):
  `\n    x` = `'\n','   ',' x'` = 3 tokens vs `\n\tx` = `'\n','\tx'` = 2 at depth 1, but 2 tabs
  (`'\n','\t','\tx'`) = 3, so it only helps at depth 1 and loses on nested code. The 2023 claim was
  specific to the GPT-3 r50k tokenizer. **Lesson: every tokenizer trick must be re-measured per
  tokenizer; cl100k/o200k already fold runs of spaces into one token.**

---

## 2. AI-oriented grammars for Python (academic, closest prior art)

### 2.1 SimPy / "AI Coders Are Among Us" (Sun et al., ISSTA 2024) - https://arxiv.org/abs/2404.16333
- **What it does.** Revises Python 3.12's grammar *terminals only* so the AST is identical and
  conversion is exact both ways: keywords/operators become placeholder tokens (`<def_stmt>`,
  `<class_stmt>`, `<true>`, `<ge>`, `<arrow>`), NEWLINE+INDENT -> `<block_start>`, DEDENT ->
  `<block_end>`, NEWLINE between simple statements -> optional `<line_sep>`, parameter parentheses and
  header colons dropped where unambiguous, `import` dropped from `from ... import`, `with` commas
  become spaces (plus `<concat>` to disambiguate string concat). Single-char symbols `.`, `(`, `=` are
  deliberately *kept* because BPE already merges them with the following token. 78 new vocabulary
  tokens added; models (CodeGen-NL 350M, TinyLlama 1.1B, Pythia 1B) continued-pretrained on 624k
  StarCoder Python files converted to SimPy. **DualCode** = input converter Python->SimPy for the
  model, output converter SimPy->Python for the human; <1 ms per 500-token snippet.
- **Measured savings (Table 2).** GPT-4/GPT-3.5 tokenizer 10.4%; CodeLlama/WizardCoder 13.5%;
  DeepSeek-Coder 12.9%; CodeT5 13.8%; StarCoder 8.6%; GPT-2/CodeBERT 34.7% (worst tokenizers gain
  most).
- **Accuracy (HumanEval only).** SimPy-only training < Python control for CodeGen (2.93 vs 4.51
  Pass@1) and TinyLlama (5.91 vs 10.00); Python->SimPy sequential training matched/beat control on
  Pass@10 for all three. Limitations: <=1B models, needs grammatically complete input, extra training.
- **Relevance.** This is PyDense's intellectual ancestor and will be the first thing a knowledgeable
  reviewer cites. It validates: AST-isomorphic grammar, bidirectional converter, "agent never sees
  Python" deployment, and the finding that `.`/`(`/`=` need no replacement.
- **Differentiation.** SimPy *requires* vocabulary surgery + training: it is unusable with closed
  frontier models. PyDense's constraint is the opposite - zero training, so it must spend only
  tokens that already exist (`{`, `}`, `;`, keywords) and keep syntax inside the Python/JS/C
  distribution. SimPy also has no `.attr`/implicit-self, no MCP tooling, no measured round-trip on
  real repos, and no public code. PyDense can be "SimPy for frontier models, shipped".

### 2.2 Token Sugar (ASE 2025) - https://arxiv.org/abs/2512.08266
- **What it does.** Mines 799 frequent AST subtrees (idioms like `for p0 in range(p1): p2.append(p3)`)
  from LeetCode solutions, assigns each a special token, replaces occurrences bijectively
  (`p0<1001>p1;p2;p3`), desugars with a rule-based converter (~1.3 ms/sugar). Continued pre-training
  of Pythia-1.4B, Llama-3.2-1B, Qwen-2.5-1.5B with 25% unmodified data to limit forgetting.
- **Measured savings.** Source: 15.1% (LeetCode), 12.9% (HumanEval); SimPy 15.3%/13.3%; combined
  22.4%/20.0%. Generated tokens: 7.7-11.2%. Pass@1 unchanged within noise (26.2 -> 25.6 Qwen).
- **The warning shot.** Untrained GPT-4.1 on sugared prefixes: Pass@1 94.5% -> 51.2%; with examples
  in prompt 54.9%. "Dedicated training is needed."
- **Relevance / differentiation.** Shows the ceiling of combined syntax+idiom tricks even with
  training (~22%). PyDense's `%p`/`#np`/`$0` macros are a crude, hand-picked Token Sugar - and
  the v0.2 measurements (now `docs/SPEC.md` §12.3) show most are token-negative on o200k. Drop them. If any macro layer survives, it must
  be (a) measured positive on both tokenizers, (b) frequency-mined from a real corpus, (c) opt-in.

### 2.3 ShortCoder (2026) - https://arxiv.org/abs/2601.09703
- **What it does.** Ten *semantic-preserving Python idiom* rules (chained assignment, drop redundant
  return parens, `+=`, ternaries, `elif` flattening, comprehensions, `del a, b`, `dict.get`,
  `str.format`, `with open`), a ShorterCodeBench corpus, LoRA fine-tune of CodeLlama-7B-Instruct.
- **Measured savings.** HumanEval generated tokens 197.8 -> 162.0 (18.1%); Pass@1 0.474 -> 0.612
  (confounded by instruction tuning).
- **Relevance.** These are *rewrites*, not encodings: they change the AST and are not bijective.
  Out of scope for a lossless core, but a possible optional "canonicalize" pass if the user accepts
  AST change. Mainly useful as a citation that "conciseness-aware" output prompting works.

### 2.4 "How Code Formatting Silently Consumes Your LLM Budget" (Pan et al., ICSE 2026) - https://arxiv.org/abs/2508.13666
- **What it does.** FIM code completion across Java/Python/C++/C#, 10 LLMs. Removes indentation,
  whitespace, newlines; bidirectional tool (extended Uncrustify for C-family, YAPF-based for
  Python) with 100% AST equivalence on McEval, 76 ms/sample, bracket-matching repair for partial code.
- **Measured savings (GPT-4o tokenizer).** Input: Java 34.9%, C++ 31.1%, C# 25.3%, **Python 6.5%**
  (Stack v2 preliminary: Java 14.7%, C# 13.2%, C++ 13.2%, Python 4.0%). Average 24.5%. Output tokens
  barely change when input is unformatted (2.5% avg); prompting GPT-4o with a detailed prompt cut
  output 27.2% (Java 36.1%); QLoRA fine-tune 24.8-35.9%. Pass@1 "maintained" (worst drop Phi-3.5 C++
  -4.2 pts; GPT-4o Python *rose* 66.4 -> 71.5).
- **Relevance.** The cleanest independent measurement that **Python's grammar is the bottleneck**:
  you cannot remove its newlines/indents without changing the grammar. That is precisely PyDense's
  brace-block thesis, with an upper bound: Java gets ~35% because braces let you remove *all*
  layout; Python with braces would approach that minus the tokens braces themselves cost.
  Also: models do not emit compact output unless told to - the SKILL.md/prompt matters as much as
  the grammar. The output-side result also warns that some models (Gemini-1.5) broke syntax when
  pushed to compress output (C++ Pass@1 67.2 -> 11.1).
- **Differentiation.** Their tool is whitespace-only and stays Python; PyDense goes one step further
  (brace grammar, implicit self) and provides the write-side (compile) path plus REPL/MCP.

---

## 3. Prompt-compression methods (model-based, lossy)

### 3.1 LLMLingua / LongLLMLingua / LLMLingua-2 (Microsoft) - https://github.com/microsoft/LLMLingua , https://www.microsoft.com/en-us/research/project/llmlingua/
- **What it does.** Drops tokens by small-LM perplexity (LLMLingua), question-aware coarse-to-fine
  (LongLLMLingua), BERT token classifier distilled from GPT-4 (LLMLingua-2, 3-6x faster).
- **Measured savings.** Up to 20x on GSM8K/BBH with ~1.5 pt loss; LongLLMLingua +21.4% accuracy at
  ~4x on NaturalQuestions, 94% cost cut on LooGLE, 1.4-2.6x latency. On *code* (RepoQA, per
  LongCodeZip) LLMLingua and LLMLingua-2 "perform poorly" because token-level pruning breaks syntax;
  LongLLMLingua does better.
- **Relevance / differentiation.** Orthogonal and lossy: these pick *which* tokens to keep; PyDense
  changes *how* kept tokens are spelled. Important positioning point: PyDense output remains
  executable and round-trippable; LLMLingua output does not. They compose (compress the dense form).

### 3.2 LongCodeZip (ASE 2025) - https://arxiv.org/abs/2510.00446 , code https://github.com/YerbaPage/LongCodeZip
- **What it does.** Function-level chunks ranked by instruction-conditioned perplexity, then
  block-level selection under an adaptive token budget; plug-and-play, 0.5B compressor suffices.
- **Measured savings.** Up to 5.6x compression / 77% fewer input tokens without degrading completion,
  summarization, QA; latency 15.7 s -> 6.6 s.
- **Relevance.** State of the art for *selecting* code context. PyDense should not compete here;
  it should present itself as the encoding layer under any selector (Aider map, LongCodeZip, grep).

### 3.3 Stingy Context (Ostby, 2026 preprint) - https://arxiv.org/abs/2601.19929
- **Claim.** Hierarchical "TREEFRAG" tree compression, 239k -> 11k tokens (18:1), 94-97% success on
  40 issues across 12 models. Single-author, CC BY-NC-SA, unreplicated. Treat as marketing-grade.
- **Relevance.** Cautionary example of unverifiable compression claims; PyDense's credibility depends
  on publishing a reproducible corpus benchmark (stdlib + popular repos) with fidelity numbers.

---

## 4. Token-oriented data formats

### 4.1 TOON - Token-Oriented Object Notation - https://github.com/toon-format/toon
- **What it does.** Lossless encoding of the JSON data model: YAML-ish indentation for objects,
  CSV-ish rows with a declared header `[N]{fields}` for uniform arrays, inline primitive arrays,
  list fallback. Explicit design principle: "translation layer, not a replacement - use JSON
  programmatically, encode as TOON for LLM input." Guardrails (`[N]`, field widths) make truncation
  detectable (100% vs 0% in truncation test).
- **Measured savings (o200k).** -43.6% to -66.5% on uniform data (GitHub repos 41.7%, time series
  59.0%), -32.9% nested e-commerce, -15.0% semi-uniform logs; **+1.6% vs compact JSON** on the mixed
  track and +19.9% worse on event logs; CSV beats it by 5-10% on flat tables. Retrieval accuracy
  72.2% vs JSON 71.4% with 42.6% fewer tokens across 4 models/244 Qs (differences mostly inside CIs);
  independent arXiv 2603.03306 found plain JSON more accurate for *generation* and a "prompt tax"
  from explaining TOON in short contexts.
- **Relevance.** TOON is the most successful recent "LLM-side encoding" and its playbook is directly
  reusable: (1) lossless by construction, deterministic round-trip; (2) honest, per-dataset benchmark
  tables including the cases where it *loses*; (3) positioned as a transport layer with the canonical
  format on disk; (4) structural guardrails for truncation detection. Its weakness - savings vanish on
  non-uniform data - mirrors PyDense's: savings vanish on code that is mostly identifiers/strings.
- **Differentiation.** PyDense is TOON-for-Python-source. Adopt the same messaging ("your repo stays
  .py; the agent sees .dpy") and the same benchmark honesty. Consider a cheap guardrail analogue:
  balanced-brace check means truncated agent output is detectable before compile.

### 4.2 "A Token Efficient Language for LLMs" (Matt Rickard, 2023) - https://mattrickard.com/a-token-efficient-language-for-llms
- Config formats on one object (OpenAI tokenizer): JSON indented 162, YAML 85, minified JSON 64,
  Tok-son 61; LLaMA tokenizer reorders results. Observes brackets already merge into efficient tokens
  and that long punctuation runs are often 1 token. Takeaway reused above: minified familiar syntax
  beats invented syntax, and rankings are tokenizer-specific.

---

## 5. "AI-native" / LLM-first programming languages

### 5.1 GlyphLang (Show HN, 2026) - https://news.ycombinator.com/item?id=46571166
- **What it does.** Standalone language (Go lexer/parser/bytecode VM) replacing keywords with symbols
  (`@` route, `$` var, `>` return); planned `.glyphx` human layer with `expand`/`compact`.
- **Measured savings.** Claimed ~45% fewer tokens than Python / 63% than Java; a commenter re-ran
  tiktoken on the README example (36 -> 30 tokens, -17%), author admitted method was "incorrect" and
  revised to 35% / 56%. No generation-quality evals.
- **HN consensus (relevant verbatim).** "short symbols cause collisions with other tokens in the LLM's
  vocabulary"; "the vocabulary of tokens isn't conserved inside model families"; "any deviation from
  the syntax LLMs are trained on is not productive"; "golfing for the wrong metric"; "treating token
  count as the only bottleneck rather than comprehension fidelity"; teaching a new language costs
  "millions of tokens" of docs per prompt.
- **Relevance / differentiation.** This is exactly the critique PyDense v0.2 (`@f`, `^>`, `~?`, `%p`)
  would receive. PyDense should differentiate by *not being a new language*: same keywords, same
  AST, same precedence; only layout (`{};`) and the `self` boilerplate change; every construct's
  token delta published; bijection proven on CPython's own stdlib.

### 5.2 ll-lang - https://dev.to/neftedollar/why-we-built-ll-lang-a-statically-typed-functional-language-for-llms-2hg8
- Statically typed functional language, no braces/semicolons, small keyword set, compiles to F#/TS/
  Python/Java/C#; pitch is compile-time feedback loops for agents more than token count. No numbers.

### 5.3 Nanolang (HN 2026) - https://news.ycombinator.com/item?id=46684958
- "Tiny experimental language designed to be targeted by coding LLMs"; explicitly *not* about token
  efficiency (per thread). Low relevance.

### 5.4 Jason Hall, "A programming language for LLMs" (2026) - https://github.com/ImJasonH/ImJasonH/blob/main/articles/llm-programming-language.md
- Experiments: Gemini's B-IR (dense Unicode opcodes) failed to bootstrap; Claude's TBIR used
  single-byte opcodes and then *spontaneously switched to short English keywords* because symbols
  hindered it. Conclusion: maximal token compression is not the answer; what helps LLMs is
  unambiguous scoping, no significant whitespace ("exact counts, which LLMs handle poorly"), comments
  kept, tests near code, clear short error codes mapped to fix prompts ("Loom" sketch).
- **Relevance.** Independent confirmation of PyDense's two defensible pillars - braces instead of
  indentation (robustness, not just tokens) and compact error reporting (PyDense's one-line
  tracebacks) - and of abandoning sigils.

### 5.5 "Blocky", "Zig for LLMs" - not found
- Searches for a "Blocky" LLM language and for any Zig proposal to redesign syntax for LLMs returned
  nothing relevant (only Zig-written LLM runtimes and a blog on Zig's churn hurting LLMs). The D
  language blog (https://blog.dlang.org/2026/08/10/language-plasticity-is-more-important-than-ever/)
  discusses the ICSE'26 formatting study (24.5% avg, Java 35%, Python ~6%, Pass@1 drop < 4.2 pts) as
  motivation for *language plasticity*, not a new language.

### 5.6 "Which programming languages are most token-efficient?" (HN 2026) - https://news.ycombinator.com/item?id=46582728
- Benchmark chart topped by J (APL family); C and JavaScript near bottom. Commenters: popularity in
  training data matters because BPE merges common sequences; "extra tokens may give the model room
  to reason"; static typing reduces iterations and therefore total tokens. Ruby pitched elsewhere as
  "second most token-efficient mainstream language"
  (https://www.ivanturkovic.com/2026/01/17/ruby-token-efficiency-llm-ai-friendly-language/).
  Relevance: frame PyDense's metric as *tokens per completed task*, not tokens per file.

---

## 6. Tree-sitter skeletonization / repo outlines (lossy, read-side)

### 6.1 Aider repo map - https://aider.chat/docs/repomap.html , https://aider.chat/2023/10/22/repomap.html
- Tree-sitter `tags.scm` queries extract definitions/references; graph ranking (files as nodes,
  dependency edges; PageRank-style per third parties) picks the most-referenced identifiers;
  emits file list + signatures + "critical lines" with `⋮` elisions; trimmed to `--map-tokens`
  (default 1k). No published accuracy numbers. Derivatives: RepoMapper MCP server, repomap-cli.
- **Relevance / differentiation.** Complementary, not competing: the map answers "what exists",
  PyDense answers "how do I read/write a given file cheaply". A PyDense `read_file_as_pydense` with a
  `signatures_only`/`depth` option would unify both; the dense form makes a *full* file fit where
  Aider has to elide.

### 6.2 Headroom CodeCompressor - https://instagit.com/chopratejas/headroom/how-headrooms-codecompressor-uses-ast-treesitter-code-compression
- Tree-sitter for 8 languages; keeps imports/types/signatures/decorators/comments, truncates bodies
  by an importance score within a global line budget, re-parses output and falls back to original
  on error nodes. Lossy; no token numbers published.

### 6.3 lean-ctx - https://github.com/yvgude/lean-ctx
- MCP "context gateway": read modes `full|map|signatures|diff|lines:N-M|density:X` (keep highest-
  entropy lines to X% tokens), 27 tree-sitter languages, shell-output compression. Withdrew its own
  savings table as "workload-specific"; quality "unknown"; lossy with expand-on-demand.

### 6.4 contx, sqz-cli, car-ast, Codebase-Memory (arXiv 2603.27277)
- Symbol/signature extractors and tree-sitter knowledge graphs served over MCP. All lossy outlines.
- **Lesson for PyDense.** The MCP-server-for-context category is crowded and *all* entrants are
  lossy summarizers. PyDense's unique claim is "the full file, losslessly, in fewer tokens" plus
  the write path; it should say so and should also offer the skeleton mode so agents need only one
  server.

---

## 7. Brace-Python and implicit-self precedents

### 7.1 Bython / PyBraces / CurlyPy
- Bython (https://github.com/mathialo/bython, PyPI `Bython`): `.by` files with `{}` blocks,
  preprocessor to Python, plus `py2by` reverse converter; Unix-only; MIT. PyBraces (`pyb`) for
  one-liners; CurlyPy adds optional `;` separators. All are string/regex preprocessors (no AST),
  none mention tokens.
- **Relevance.** Prior art for `{}` blocks and `;` in Python - PyDense is not the first; it must
  show the *token* motivation and a real parser. Avoid their failure (regex preprocessing breaks on
  braces inside strings/dicts/f-strings) by lexing properly and disambiguating dict/set literals from
  blocks grammatically (block only after a header `):`/`:`/`else`/`try`...).

### 7.2 Implicit `self` / `.attr` in Python
- PEP 3099 ("explicit self will not change"); python-list 2008 ".member in place of self.member";
  python-ideas 2015 "Mitigating self. method pollution"; discuss.python.org 2025 "Implicit self in
  Python 4.x" (rejected; pointed to Guido's "Why explicit self has to stay"). Objections: readability,
  monkey-patching, local/attribute confusion, decorators/classmethods.
- **Relevance.** `.x` has repeatedly been proposed and is immediately readable to Pythonistas (and
  to Swift/Kotlin users). The documented objections are exactly PyDense's bug list (classmethod,
  nested functions, non-`self` first param). The compiler must decide implicit-self *per function
  def* from decorators and position (plain method in class body, not `@staticmethod`/`@classmethod`,
  not nested), and the decompiler must only emit `.x` when the first parameter is literally `self`
  and the method is eligible; otherwise emit the explicit form.

---

## 8. Tokenizer behaviour (measured locally + literature)

### 8.1 tiktoken pre-tokenizer regexes (from `tiktoken` 0.x, read via `enc._pat_str`)
- o200k_base: `[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?|...|\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n/]*|\s*[\r\n]+|\s+(?!\S)|\s+`
- cl100k_base: `'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s`
- Consequences (all verified with tiktoken for this survey; `docs/SPEC.md` §12.4 has the kept probes):
  * `[^\r\n\p{L}\p{N}]?` + letters: **one non-alnum char can prefix a word** - `.value`, `(a`, `,b`,
    `:x`, `=x`, `\x` are single tokens. This is why `.x`, `f(a,b)` and `\x:` are cheap, and why
    `@f update` is 3 tokens (`@`,`f`,` update`) - the prefix slot is taken by the space.
  * `\s+(?!\S)`: a run of whitespace is one token *except the last space*, which attaches to the next
    word. Hence `\n` + indent = 2 tokens at any depth; blank lines `\n\n` = 1 token.
  * Punctuation runs `[^\s\p{L}\p{N}]+` merge: `){`, `:{`, `};`, `}}`, `&&!`, `!=` are 1 token; but
    merging stops at letters/digits, so `}else{` = 2 (`}else`,`{`) and `}}}` = 2 in o200k.
  * Digits chunk by 3 (`\p{N}{1,3}`): `1.0`=3 tokens, `0`=1 - numeric literals are expensive and
    PyDense cannot help.
- Design rules that follow: (1) keep Python keywords - `def`/`return`/`if` are 1 token and the
  following space is free; (2) spend punctuation only where it merges with a neighbour (`){`, `};`);
  (3) prefer `.x` after punctuation, not after keywords; (4) never introduce `symbol+letter` sigils
  (`@f`, `#np`, `%p`) - the symbol steals the prefix slot and splits the identifier.

### 8.2 Cross-tokenizer caveats
- Claude's tokenizer is unpublished; only `count_tokens` gives exact numbers. Third-party notes:
  letters absorb a preceding space but digits/punctuation often do not, and Claude cannot begin
  output with a space (bad for indentation-led continuation; good for brace syntax). Estimates put
  Claude 15-20% above OpenAI counts on English, more on code (unverified). o200k vs cl100k agree on
  every probe above except `}}}` (2 vs 1). SimPy's spread (8.6%-34.7%) and GlyphLang's retraction show
  savings are tokenizer-specific: PyDense must report o200k and cl100k side by side and add
  Anthropic `count_tokens` when an API key is available.

---

## 9. Local measurements (this survey)

Corpus: first 150 `*.py` files of the CPython 3.13 stdlib (`os.path.dirname(os.__file__)`), 1,057,687
o200k / 1,048,559 cl100k tokens, 4.46M chars. Survey-time measurement; `benchmarks/token_compression.py --corpus stdlib`
reproduces the python-minifier and `ast.unparse` columns on the shipped corpus.

| Transform | o200k | cl100k | chars | failures | lossless? |
|---|---:|---:|---:|---:|---|
| original | 0.0% | 0.0% | 0.0% | 0 | yes |
| `ast.unparse` (drops comments, keeps docstrings) | -15.1% | -15.3% | -17.7% | 0 | no (comments) |
| unparse + drop docstrings | -35.7% | -36.0% | -39.6% | 0 | no |
| tabify indentation (4 spaces -> tab) | +0.5% | +0.6% | -14.7% | 0 | yes |
| python-minifier, whitespace only | -21.3% | -21.7% | -31.6% | 0 | comments lost, AST kept |
| python-minifier defaults (rename locals, hoist) | -21.9% | -22.3% | -36.4% | 0 | AST changed |
| python-minifier + remove docstrings + annotations | -36.1% | -36.6% | -50.2% | 0 | no |
| python-minifier everything (+rename globals, asserts, debug) | -37.7% | -38.1% | -52.5% | 0 | no |
| PyDense v0.2 (`benchmarks/corpus_fidelity.py --backend legacy`, same corpus class, types stripped) | -37.1% | n/a | n/a | 42% stmts corrupted | no |

Headroom after whitespace-only minification (832,734 o200k tokens, 36,303 lines): pure-whitespace
tokens 57,040 (6.8%), newline-bearing tokens 36,303 (4.4%), `self`/` self` tokens 9,315 (1.1%,
undercounts merged `(self`). Replacing every newline+indent pair with one `;`/`{`/`}` token can
therefore add at most ~4-7 points; implicit self ~1-3 points on stdlib-style code (more on OO-heavy
application code such as the reference samples).

Single-construct deltas (o200k, survey-time probes): `def f(a, b):\n    return a + b\n` 12 ->
`def f(a,b){return a+b}` 9 -> `def f(a,b):return a+b` 8; `class A:\n    def __init__(self, x):\n
self.x = x\n` 18 -> `class A{def __init__(self,x){self.x=x}}` 14 -> `class A{def __init__(x){.x=x}}` 13;
`for i in range(10):\n    total += i` 11 -> `for i in range(10){total+=i}` 11 (no gain on one-line
bodies: `){` costs what `:\n` + indent cost minus the free space); `x = foo(a, b, c)` 9 -> `x=foo(a,b,c)` 7.

---

## 10. What the field has learned (synthesis)

1. Whitespace is the cheap, safe win everywhere; for Python it is capped by grammar (4-6.5% in the
   ICSE'26 study, ~21% when comments also go). Brace blocks are the only way past that cap.
2. Keyword substitution with symbols is net-negative on modern tokenizers and net-negative for
   model accuracy without training (Token Sugar 94.5 -> 51.2; GlyphLang critique; TBIR reversal).
3. Idiom/macro tokens (Token Sugar, PyDense `%p`/`#np`) need vocabulary surgery + training to pay off;
   with frozen frontier tokenizers they are mostly neutral or negative.
4. Models maintain Pass@1 on unformatted/compressed *input* but do not spontaneously emit compact
   *output*; the output side needs explicit instruction (and some models break syntax when pushed).
5. Lossless, deterministic, round-trip, "transport layer not storage format" is the winning
   positioning (TOON, SimPy DualCode, ICSE'26 tool). Lossy skeletonizers own the read-side map
   niche (Aider et al.) and are complementary.
6. Credibility comes from honest per-dataset tables that include the losses (TOON) and from
   fidelity proofs; unverifiable headline ratios (Stingy Context, early GlyphLang) get discounted.

## 11. How PyDense differentiates (what shipped in v1.0)

1. **Lossless bijection as the headline guarantee, proven.** FULL mode satisfies
   `ast.dump(parse(encode(src))) == ast.dump(ast.parse(src))` for every module construct of Python 3.10–3.13;
   verified 469/469 files (148 stdlib + 321 site-packages modules, 12,508 top-level statements) at design time, and
   re-run on the stdlib corpus by `benchmarks/corpus_fidelity.py` in CI with `--fail-under 100`. Comments are not
   kept (exactly as `ast.unparse`; `docs/SPEC.md` §11). The lossy layers are separate, labelled modes: NODOC
   (docstrings) and STRIPPED (docstrings + annotations), each reported against its own baseline.
2. **Brace blocks, Python keywords unchanged.** `{}` blocks with one statement per line (the `;` single-line
   variant measured 2 tokens worse on the samples), `.x` for `self.x`, `c?a:b`, shortest-form floats and `{}` for
   `pass`; nothing else differs from Python. `??`, `&&`, `||`, `!`, the `\` lambda and every v0.2 sigil were
   re-measured and rejected (`docs/SPEC.md` §12.3); a legacy sigil at statement start is error E008.
3. **Implicit self done right.** Eligibility is decided per `def` from the AST (class body, `@classmethod`,
   `@staticmethod`, nesting) by the exact rule of `docs/SPEC.md` §7, with `def!` as the escape hatch; on the
   corpus 94.0% of methods drop the receiver and 0.5% need `def!`.
4. **Every sigil the evidence showed negative is gone** (`@f`, `@c`, `@i`, `^`, `^>`, `^!`, `^~`, `^@`, `~?`,
   `@in`, `@is`, `@aw`, `#T/#F/#N`, `%p`…, `#np`…, `$n`), for the reasons SimPy ("keep `.`, `(`, `=`") and Token
   Sugar (untrained GPT-4.1 collapse) give.
5. **MCP write-dense / commit-clean as the product.** `pydense-mcp` ships `read_file_as_dpy` (FULL by default;
   NODOC/STRIPPED as read-only views), `write_dpy_file` (parses, writes `ast.unparse` Python, refuses to drop
   docstrings unless `allow_docstring_loss=True`), `execute_dpy` (stateful REPL with one-line `!Err[...]`
   tracebacks, Hall's "short error codes" point), `transpile_dpy`, `check_dpy` and `get_dpy_cheatsheet`; E001
   lists every unmatched `{` as the brace-balance guardrail (TOON's `[N]` analogue). A skeleton/signatures-only
   read mode is not shipped.
6. **Benchmarked like TOON, not like GlyphLang.** `README.md` and `docs/SPEC.md` §12 report o200k and cl100k side
   by side, per corpus (7 reference samples, 148-file stdlib, 321-file site-packages), lossless and lossy rows,
   with `ast.unparse` and python-minifier whitespace-only as baselines in the same table and fidelity columns.
   The "~50%" claim is replaced by the measured −12.04% FULL / −15.85% NODOC (corpus) and −41.16% STRIPPED
   (lossy, vs with-doc).
7. **Accuracy evidence.** Not shipped: no held-out task set compares agent pass rates on dense vs plain Python.
   This remains the open question the literature (ICSE'26, Token Sugar) says reviewers will ask.
8. **Naming.** The suffix is `.dpy`; `.pyd` (CPython's Windows extension-module suffix) is no longer used anywhere.

## 12. Sources

- python-minifier: https://github.com/dflook/python-minifier ; https://dflook.github.io/python-minifier/ ; https://pypi.org/project/python-minifier/
- pyminifier: https://github.com/liftoff/pyminifier ; https://pythonhosted.org/pyminifier/ ; https://pyminifier3.readthedocs.io
- kakn/python-code-minifier: https://github.com/kakn/python-code-minifier
- Qodo tabification: https://www.qodo.ai/post/reduce-your-costs-by-30-when-using-gpt-3-for-python-code
- SimPy: https://arxiv.org/abs/2404.16333 ; https://arxiv.org/html/2404.16333v2 ; https://2024.issta.org/details/issta-2024-papers/90/
- Token Sugar: https://arxiv.org/abs/2512.08266 ; https://arxiv.org/html/2512.08266v1
- ShortCoder: https://arxiv.org/abs/2601.09703 ; https://arxiv.org/html/2601.09703
- Code formatting budget (ICSE'26): https://arxiv.org/abs/2508.13666 ; https://arxiv.org/html/2508.13666v1
- D blog on plasticity: https://blog.dlang.org/2026/08/10/language-plasticity-is-more-important-than-ever/
- LLMLingua family: https://github.com/microsoft/LLMLingua ; https://www.microsoft.com/en-us/research/project/llmlingua/ ; https://www.microsoft.com/en-us/research/blog/llmlingua-innovating-llm-efficiency-with-prompt-compression/ ; LongLLMLingua https://arxiv.org/abs/2310.06839 ; LLMLingua-2 https://arxiv.org/abs/2403.12968
- LongCodeZip: https://arxiv.org/abs/2510.00446 ; https://github.com/YerbaPage/LongCodeZip
- Stingy Context: https://arxiv.org/abs/2601.19929
- Empirical study on prompt compression: https://arxiv.org/pdf/2505.00019 ; PCToolkit https://arxiv.org/pdf/2403.17411
- TOON: https://github.com/toon-format/toon ; benchmark paper https://arxiv.org/pdf/2603.03306
- Matt Rickard: https://mattrickard.com/a-token-efficient-language-for-llms
- GlyphLang: https://news.ycombinator.com/item?id=46571166
- ll-lang: https://dev.to/neftedollar/why-we-built-ll-lang-a-statically-typed-functional-language-for-llms-2hg8
- Nanolang: https://news.ycombinator.com/item?id=46684958
- Jason Hall essay: https://github.com/ImJasonH/ImJasonH/blob/main/articles/llm-programming-language.md
- Token-efficient languages thread: https://news.ycombinator.com/item?id=46582728 ; Ruby post https://www.ivanturkovic.com/2026/01/17/ruby-token-efficiency-llm-ai-friendly-language/
- Aider repo map: https://aider.chat/docs/repomap.html ; https://aider.chat/2023/10/22/repomap.html ; RepoMapper https://github.com/Cryect/RepoMapper
- Headroom CodeCompressor: https://instagit.com/chopratejas/headroom/how-headrooms-codecompressor-uses-ast-treesitter-code-compression
- lean-ctx: https://github.com/yvgude/lean-ctx ; contx https://github.com/yugaaank/contx ; Codebase-Memory https://arxiv.org/pdf/2603.27277
- Bython: https://github.com/mathialo/bython ; https://pypi.org/project/Bython/ ; PyBraces https://pypi.org/project/pybraces/ ; CurlyPy https://pypi.org/project/curlypy/
- Implicit self history: https://www.python.org/pipermail/python-ideas/2015-July/034602.html ; https://discuss.python.org/t/proposal-implicit-self-in-python-4-x-reduce-boilerplate-in-instance-methods/96791 ; https://www.python.org/pipermail/python-list/2008-July/491422.html
- Obfuscated-code comprehension: https://arxiv.org/abs/2504.10557 ; JsDeObsBench https://arxiv.org/abs/2506.20170
- tiktoken: https://github.com/openai/tiktoken ; https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken ; Claude tokenizer notes https://tokencontributions.substack.com/p/the-mystery-of-the-claude-3-tokenizer
