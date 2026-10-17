#!/usr/bin/env python3
"""
PyDense (.pyd) Compiler, Decompiler & Execution Engine v0.2
Supports arbitrary decorators, optional type annotations, *args/**kwargs unpacking,
and full async/await AST bijection.
"""

from __future__ import annotations
import ast
import asyncio
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ============================================================================
# 1. MACRO & BUILTIN REGISTRIES
# ============================================================================

CONST_MACROS: Dict[str, str] = {
    "#T": "True",
    "#F": "False",
    "#N": "None",
}
REV_CONST_MACROS: Dict[str, str] = {v: k for k, v in CONST_MACROS.items()}

# Library macros: #alias -> (module_name, optional_attr, canonical_py_alias)
LIB_MACROS: Dict[str, Tuple[str, Optional[str], str]] = {
    "#np": ("numpy", None, "np"),
    "#pd": ("pandas", None, "pd"),
    "#sp": ("scipy", None, "sp"),
    "#os": ("os", None, "os"),
    "#sys": ("sys", None, "sys"),
    "#js": ("json", None, "json"),
    "#re": ("re", None, "re"),
    "#m": ("math", None, "math"),
    "#dt": ("datetime", None, "dt"),
    "#pl": ("pathlib", "Path", "Path"),
    "#as": ("asyncio", None, "asyncio"),
    "#dc": ("dataclasses", "dataclass", "dataclass"),
}

BUILTIN_MACROS: Dict[str, str] = {
    "%p": "print",
    "%l": "len",
    "%r": "range",
    "%e": "enumerate",
    "%z": "zip",
    "%s": "sum",
    "%m": "map",
    "%f": "filter",
    "%d": "dict",
    "%li": "list",
    "%st": "set",
    "%t": "type",
    "%i": "isinstance",
    "%a": "abs",
    "%mn": "min",
    "%mx": "max",
    "%rd": "round",
    "%o": "open",
}
REV_BUILTIN_MACROS: Dict[str, str] = {v: k for k, v in BUILTIN_MACROS.items()}


# ============================================================================
# 2. LEXER
# ============================================================================

@dataclass
class Token:
    kind: str
    val: str
    pos: int


TOKEN_SPEC = [
    ("COMMENT", r"//[^\n]*"),
    ("WS", r"[\t \f\r\n]+"),
    ("STRING", r"(?:[fFrRbBuU]{1,2})?(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"),
    ("NUMBER", r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"),
    (
        "MULTI",
        r"!@in|!@is|@in|@is|@aw|@wa|@af|@sf|@c|@f|@i|@w|"
        r"\^>|\^!|\^~|\^@|:\?|~\?|~@|!\*|\?\?|->|\.\.\.|"
        r"&&|\|\||//=|\*\*=|\+=|-=|\*=|/=|%=|&=|\|=|\^\||==|!=|<=|>=|<<|>>|//|\*\*",
    ),
    ("POS_ARG", r"\$\d+"),
    ("MACRO", r"#[A-Za-z_]\w*"),
    ("BUILTIN", r"%[A-Za-z_]\w*"),
    ("IDENT", r"[A-Za-z_]\w*"),
    ("PUNCT", r"[{}()\[\];:,.\?~!^><=+\-*/%&|\\@]"),
]

MASTER_RE = re.compile("|".join(f"(?P<{name}>{pat})" for name, pat in TOKEN_SPEC))

AUG_ASSIGN_OPS = {"+=", "-=", "*=", "/=", "//=", "%=", "**=", "&=", "|="}
EXPR_END_KINDS = {"IDENT", "NUMBER", "STRING", "POS_ARG", "MACRO", "BUILTIN"}
EXPR_END_VALS = {")", "]"}
DECL_KEYWORDS = {"@c", "@f", "@af", "@sf", "@i"}
BLOCK_KEYWORDS = DECL_KEYWORDS | {"?", "~", "~@", "~?", "!", "@w", "@wa"}


def tokenize_pyd(code: str) -> List[Token]:
    tokens: List[Token] = []
    pos = 0
    while pos < len(code):
        m = MASTER_RE.match(code, pos)
        if not m:
            snippet = code[pos : pos + 20]
            raise SyntaxError(f"Unexpected PyDense character at offset {pos}: {snippet!r}")
        kind = m.lastgroup
        val = m.group(kind)
        if kind not in ("WS", "COMMENT"):
            tokens.append(Token(kind, val, pos))
        pos = m.end()
    return tokens


# ============================================================================
# 3. FORWARD COMPILER (.pyd -> Python Source & AST)
# ============================================================================

class PyDenseCompiler:
    """Compiles whitespace-free .pyd code into standard Python source and ast.Module."""

    def __init__(self) -> None:
        self.used_macros: set[str] = set()
        self.class_depth: int = 0
        self.func_param_stack: List[List[str]] = []

    def compile_to_source(self, pyd_code: str, inject_imports: bool = True) -> str:
        self.used_macros.clear()
        self.class_depth = 0
        self.func_param_stack.clear()

        tokens = tokenize_pyd(pyd_code)
        body_lines = self._parse_stmt_list(tokens, indent=0)

        header_lines: List[str] = []
        if inject_imports and self.used_macros:
            for mac in sorted(self.used_macros):
                if mac in LIB_MACROS:
                    mod, attr, alias = LIB_MACROS[mac]
                    if attr:
                        header_lines.append(f"from {mod} import {attr} as {alias}")
                    else:
                        header_lines.append(f"import {mod} as {alias}")

        all_lines = header_lines + body_lines
        return "\n".join(all_lines) if all_lines else "pass"

    def compile_to_ast(self, pyd_code: str, filename: str = "<pydense>") -> ast.Module:
        py_src = self.compile_to_source(pyd_code, inject_imports=True)
        tree = ast.parse(py_src, filename=filename)
        ast.fix_missing_locations(tree)
        return tree

    # --- Structural Block & Statement Splitting ---

    def _parse_stmt_list(self, tokens: List[Token], indent: int) -> List[str]:
        stmts = self._split_statements(tokens)
        lines: List[str] = []
        for s in stmts:
            if s:
                lines.extend(self._parse_stmt(s, indent))
        if not lines:
            lines.append("    " * indent + "pass")
        return lines

    def _split_statements(self, tokens: List[Token]) -> List[List[Token]]:
        """Splits token stream on top-level ';' OR top-level block closing '}'."""
        stmts: List[List[Token]] = []
        curr: List[Token] = []
        depth = 0
        n = len(tokens)
        i = 0

        while i < n:
            t = tokens[i]
            if t.val in ("(", "["):
                depth += 1
                curr.append(t)
            elif t.val in (")", "]"):
                depth -= 1
                curr.append(t)
            elif t.val == "{":
                depth += 1
                curr.append(t)
            elif t.val == "}":
                depth -= 1
                curr.append(t)
                if depth == 0:
                    nxt = tokens[i + 1].val if i + 1 < n else None
                    if nxt not in (":?", ":", "!", "!*") and self._is_block_stmt(curr):
                        stmts.append(curr)
                        curr = []
            elif t.val == ";" and depth == 0:
                if curr:
                    stmts.append(curr)
                    curr = []
            else:
                curr.append(t)
            i += 1

        if curr:
            stmts.append(curr)
        return stmts

    def _is_block_stmt(self, stmt_tokens: List[Token]) -> bool:
        """Returns True if stmt_tokens represents a control/declaration block rather than a dict assignment."""
        if not stmt_tokens:
            return False
        if stmt_tokens[0].val in BLOCK_KEYWORDS or stmt_tokens[0].val == "@":
            return True
        return False

    def _extract_block(self, tokens: List[Token], start_idx: int) -> Tuple[List[Token], int]:
        if start_idx >= len(tokens) or tokens[start_idx].val != "{":
            raise SyntaxError(f"Expected '{{' at token {tokens[start_idx:]}")
        depth = 0
        for i in range(start_idx, len(tokens)):
            if tokens[i].val == "{":
                depth += 1
            elif tokens[i].val == "}":
                depth -= 1
                if depth == 0:
                    return tokens[start_idx + 1 : i], i + 1
        raise SyntaxError("Unclosed '{' block in PyDense code")

    def _find_top_level(self, tokens: List[Token], target_vals: set[str], start: int = 0) -> int:
        depth = 0
        for i in range(start, len(tokens)):
            v = tokens[i].val
            if v in ("(", "[", "{"):
                depth += 1
            elif v in (")", "]", "}"):
                depth -= 1
            elif depth == 0 and v in target_vals:
                return i
        return -1

    # --- Decorator Prefix Extractor ---

    def _extract_decorators(self, tokens: List[Token]) -> Tuple[List[str], List[Token]]:
        """
        Extracts leading @dec or @[dec1,dec2] chains before @c, @f, @af, @sf, @i.
        Returns (rendered_decorator_lines, remaining_tokens).
        """
        decorators: List[str] = []
        idx = 0
        n = len(tokens)

        while idx < n:
            tok = tokens[idx]
            # Bracketed decorator list: @[dec1, dec2(a)]
            if tok.val == "@" and idx + 1 < n and tokens[idx + 1].val == "[":
                close_b = self._find_matching_bracket(tokens, idx + 1, "[", "]")
                inner = tokens[idx + 2 : close_b]
                for item in self._split_top_level(inner, ","):
                    if item:
                        decorators.append(f"@{self._parse_expr(item)}")
                idx = close_b + 1
                continue

            # Single stacked decorator: @dec_expr followed by another @ or declaration keyword
            if tok.val == "@":
                depth = 0
                end_idx = -1
                for j in range(idx + 1, n):
                    v = tokens[j].val
                    if v in ("(", "[", "{"):
                        depth += 1
                    elif v in (")", "]", "}"):
                        depth -= 1
                    elif depth == 0 and (v == "@" or v in DECL_KEYWORDS):
                        end_idx = j
                        break
                if end_idx == -1:
                    raise SyntaxError(f"Decorator missing target class or function: {tokens[idx:]}")
                dec_expr = self._parse_expr(tokens[idx + 1 : end_idx])
                decorators.append(f"@{dec_expr}")
                idx = end_idx
                continue

            break

        return decorators, tokens[idx:]

    # --- Statement Parsers ---

    def _parse_stmt(self, tokens: List[Token], indent: int) -> List[str]:
        pad = "    " * indent

        # Extract any leading decorators (@dec or @[dec1,dec2])
        decorators: List[str] = []
        if tokens[0].val == "@":
            decorators, tokens = self._extract_decorators(tokens)
        dec_lines = [f"{pad}{d}" for d in decorators]

        first = tokens[0].val

        # 1. Class definition: @c Name(Bases){...}
        if first == "@c":
            name = tokens[1].val
            idx = 2
            bases_str = ""
            if idx < len(tokens) and tokens[idx].val == "(":
                close_p = self._find_top_level(tokens, {")"}, idx)
                inner_bases = tokens[idx + 1 : close_p]
                if inner_bases:
                    bases_str = "(" + self._parse_bracket_inner(inner_bases, "(") + ")"
                idx = close_p + 1
            body_toks, _ = self._extract_block(tokens, idx)
            self.class_depth += 1
            body_lines = self._parse_stmt_list(body_toks, indent + 1)
            self.class_depth -= 1
            return dec_lines + [f"{pad}class {name}{bases_str}:"] + body_lines

        # 2. Function / Method definition: @f, @af, @sf, @i with optional ->ReturnType
        if first in DECL_KEYWORDS:
            idx = 1
            if first == "@i":
                fn_name = "__init__"
            else:
                fn_name = tokens[idx].val
                idx += 1

            close_p = self._find_top_level(tokens, {")"}, idx)
            param_toks = tokens[idx + 1 : close_p]
            param_names, rendered_params = self._parse_params(param_toks)

            has_staticmethod_dec = any(d == "@staticmethod" for d in decorators)
            inject_self = self.class_depth > 0 and first != "@sf" and not has_staticmethod_dec
            full_params = (["self"] + rendered_params) if inject_self else rendered_params

            # Check for optional return type annotation: ->Type before '{'
            brace_idx = self._find_top_level(tokens, {"{"}, close_p + 1)
            ret_suffix = ""
            if close_p + 1 < brace_idx and tokens[close_p + 1].val == "->":
                ret_type_str = self._parse_expr(tokens[close_p + 2 : brace_idx])
                ret_suffix = f" -> {ret_type_str}"

            body_toks, _ = self._extract_block(tokens, brace_idx)
            self.func_param_stack.append(param_names)
            body_lines = self._parse_stmt_list(body_toks, indent + 1)
            self.func_param_stack.pop()

            lines: List[str] = list(dec_lines)
            if first == "@sf" and not has_staticmethod_dec:
                lines.append(f"{pad}@staticmethod")
            kw = "async def" if first == "@af" else "def"
            lines.append(f"{pad}{kw} {fn_name}({', '.join(full_params)}){ret_suffix}:")
            lines.extend(body_lines)
            return lines

        # 3. If / Elif / Else: ?cond{...}:?cond2{...}:{...}
        if first == "?":
            lines = []
            idx = 1
            kw = "if"
            while idx < len(tokens):
                brace_idx = self._find_top_level(tokens, {"{"}, idx)
                cond_str = self._parse_expr(tokens[idx:brace_idx])
                body_toks, next_idx = self._extract_block(tokens, brace_idx)
                lines.append(f"{pad}{kw} {cond_str}:")
                lines.extend(self._parse_stmt_list(body_toks, indent + 1))
                idx = next_idx
                if idx < len(tokens) and tokens[idx].val == ":?":
                    kw = "elif"
                    idx += 1
                elif idx < len(tokens) and tokens[idx].val == ":":
                    body_toks, idx = self._extract_block(tokens, idx + 1)
                    lines.append(f"{pad}else:")
                    lines.extend(self._parse_stmt_list(body_toks, indent + 1))
                    break
                else:
                    break
            return lines

        # 4. For & Async For loop: ~target:iter{...} | ~@target:iter{...}
        if first in ("~", "~@"):
            colon_idx = self._find_top_level(tokens, {":"}, 1)
            brace_idx = self._find_top_level(tokens, {"{"}, colon_idx + 1)
            target_str = self._parse_expr(tokens[1:colon_idx])
            iter_str = self._parse_expr(tokens[colon_idx + 1 : brace_idx])
            body_toks, _ = self._extract_block(tokens, brace_idx)
            body_lines = self._parse_stmt_list(body_toks, indent + 1)
            loop_kw = "async for" if first == "~@" else "for"
            return [f"{pad}{loop_kw} {target_str} in {iter_str}:"] + body_lines

        # 5. While loop: ~?cond{...}
        if first == "~?":
            brace_idx = self._find_top_level(tokens, {"{"}, 1)
            cond_str = self._parse_expr(tokens[1:brace_idx])
            body_toks, _ = self._extract_block(tokens, brace_idx)
            body_lines = self._parse_stmt_list(body_toks, indent + 1)
            return [f"{pad}while {cond_str}:"] + body_lines

        # 6. Try / Except / Finally: !{...}!Exc:e{...}!*{...}
        if first == "!" and len(tokens) > 1 and tokens[1].val == "{":
            lines = []
            try_toks, idx = self._extract_block(tokens, 1)
            lines.append(f"{pad}try:")
            lines.extend(self._parse_stmt_list(try_toks, indent + 1))
            while idx < len(tokens):
                if tokens[idx].val == "!*":
                    fin_toks, idx = self._extract_block(tokens, idx + 1)
                    lines.append(f"{pad}finally:")
                    lines.extend(self._parse_stmt_list(fin_toks, indent + 1))
                elif tokens[idx].val == "!":
                    idx += 1
                    brace_idx = self._find_top_level(tokens, {"{"}, idx)
                    header_toks = tokens[idx:brace_idx]
                    if not header_toks:
                        exc_clause = "except:"
                    else:
                        colon_idx = self._find_top_level(header_toks, {":"})
                        if colon_idx != -1:
                            exc_type = self._parse_expr(header_toks[:colon_idx])
                            exc_var = header_toks[colon_idx + 1].val
                            exc_clause = f"except {exc_type} as {exc_var}:"
                        else:
                            exc_type = self._parse_expr(header_toks)
                            exc_clause = f"except {exc_type}:"
                    exc_toks, idx = self._extract_block(tokens, brace_idx)
                    lines.append(f"{pad}{exc_clause}")
                    lines.extend(self._parse_stmt_list(exc_toks, indent + 1))
                else:
                    break
            return lines

        # 7. With & Async With statement: @w expr:v{...} | @wa expr:v{...}
        if first in ("@w", "@wa"):
            brace_idx = self._find_top_level(tokens, {"{"}, 1)
            header_toks = tokens[1:brace_idx]
            colon_idx = self._find_top_level(header_toks, {":"})
            with_kw = "async with" if first == "@wa" else "with"
            if colon_idx != -1:
                ctx_expr = self._parse_expr(header_toks[:colon_idx])
                var_expr = self._parse_expr(header_toks[colon_idx + 1 :])
                with_head = f"{with_kw} {ctx_expr} as {var_expr}:"
            else:
                ctx_expr = self._parse_expr(header_toks)
                with_head = f"{with_kw} {ctx_expr}:"
            body_toks, _ = self._extract_block(tokens, brace_idx)
            return [f"{pad}{with_head}"] + self._parse_stmt_list(body_toks, indent + 1)

        # 8. Imports: >pkg=alias | >pkg:a,b=c
        if first == ">":
            colon_idx = self._find_top_level(tokens, {":"}, 1)
            if colon_idx != -1:
                mod_name = "".join(t.val for t in tokens[1:colon_idx])
                targets_str = self._format_import_targets(tokens[colon_idx + 1 :])
                return [f"{pad}from {mod_name} import {targets_str}"]
            else:
                targets_str = self._format_import_targets(tokens[1:])
                return [f"{pad}import {targets_str}"]

        # 9. Returns, Yields & Flow Control
        if first == "^":
            if len(tokens) == 1:
                return [f"{pad}return"]
            return [f"{pad}return {self._parse_expr(tokens[1:])}"]
        if first == "^>":
            return [f"{pad}yield {self._parse_expr(tokens[1:])}"]
        if first == "^!":
            return [f"{pad}break"]
        if first == "^~":
            return [f"{pad}continue"]
        if first == "^@":
            if len(tokens) == 1:
                return [f"{pad}raise"]
            return [f"{pad}raise {self._parse_expr(tokens[1:])}"]

        # 10. Type-Annotated Assignments (AnnAssign), Augmented & Standard Assignments
        colon_idx = self._find_top_level(tokens, {":"})
        qq_idx = self._find_top_level(tokens, {"??"})
        assign_idx = self._find_top_level(tokens, {"="} | AUG_ASSIGN_OPS)

        # Check for AnnAssign: target:Type=val or target:Type (where ':' is not part of ternary or lambda)
        if (
            colon_idx != -1
            and first != "\\"
            and (qq_idx == -1 or colon_idx < qq_idx)
            and (assign_idx == -1 or colon_idx < assign_idx)
        ):
            target_str = self._parse_expr(tokens[:colon_idx])
            if assign_idx != -1 and tokens[assign_idx].val == "=":
                ann_str = self._parse_expr(tokens[colon_idx + 1 : assign_idx])
                val_str = self._parse_expr(tokens[assign_idx + 1 :])
                return [f"{pad}{target_str}: {ann_str} = {val_str}"]
            else:
                ann_str = self._parse_expr(tokens[colon_idx + 1 :])
                return [f"{pad}{target_str}: {ann_str}"]

        if assign_idx != -1:
            op = tokens[assign_idx].val
            if op == "=":
                # Support chained assignments: a = b = 0
                parts = self._split_top_level(tokens, "=")
                return [f"{pad}{' = '.join(self._parse_expr(p) for p in parts)}"]
            lhs = self._parse_expr(tokens[:assign_idx])
            rhs = self._parse_expr(tokens[assign_idx + 1 :])
            return [f"{pad}{lhs} {op} {rhs}"]

        # 11. Expression Statement
        return [f"{pad}{self._parse_expr(tokens)}"]

    def _format_import_targets(self, tokens: List[Token]) -> str:
        parts: List[str] = []
        curr: List[str] = []
        for t in tokens:
            if t.val == ",":
                parts.append("".join(curr))
                curr = []
            elif t.val == "=":
                curr.append(" as ")
            else:
                curr.append(t.val)
        if curr:
            parts.append("".join(curr))
        return ", ".join(parts)

    def _parse_params(self, tokens: List[Token]) -> Tuple[List[str], List[str]]:
        """
        Parses parameter list supporting type annotations, defaults, *args, **kwargs, and bare '*'.
        Returns (positional_param_names_for_$0_$1, rendered_python_param_strings).
        """
        if not tokens:
            return [], []
        groups = self._split_top_level(tokens, ",")
        param_names: List[str] = []
        rendered: List[str] = []
        after_star = False

        for g in groups:
            if not g:
                continue
            eq_idx = self._find_top_level(g, {"="})
            lhs_toks = g[:eq_idx] if eq_idx != -1 else g
            def_str = self._parse_expr(g[eq_idx + 1 :]) if eq_idx != -1 else None

            colon_idx = self._find_top_level(lhs_toks, {":"})
            if colon_idx != -1:
                name_toks = lhs_toks[:colon_idx]
                type_str = self._parse_expr(lhs_toks[colon_idx + 1 :])
            else:
                name_toks = lhs_toks
                type_str = None

            p_name = "".join(t.val for t in name_toks)
            if p_name == "*":
                after_star = True
                rendered.append("*")
                continue

            # Track positional parameter names for $0, $1 binding (excluding *args, **kwargs, kw-only)
            if not p_name.startswith("*") and not after_star:
                param_names.append(p_name)
            elif p_name.startswith("*") and not p_name.startswith("**"):
                after_star = True

            param_out = p_name
            if type_str is not None:
                param_out += f": {type_str}"
            if def_str is not None:
                param_out += f" = {def_str}" if type_str is not None else f"={def_str}"
            rendered.append(param_out)

        return param_names, rendered

    # --- Expression & Comprehension Parser ---

    def _parse_expr(self, tokens: List[Token]) -> str:
        if not tokens:
            return ""

        # 1. Check top-level lambda: \a,b:expr
        if tokens[0].val == "\\":
            colon_idx = self._find_top_level(tokens, {":"}, 1)
            param_names, rendered_params = self._parse_params(tokens[1:colon_idx])
            self.func_param_stack.append(param_names)
            body_str = self._parse_expr(tokens[colon_idx + 1 :])
            self.func_param_stack.pop()
            return f"(lambda {', '.join(rendered_params)}: {body_str})"

        # 2. Check top-level ternary: cond ?? true_val : false_val
        q_idx = self._find_top_level(tokens, {"??"})
        if q_idx != -1:
            depth = 0
            nested_q = 0
            colon_idx = -1
            for i in range(q_idx + 1, len(tokens)):
                v = tokens[i].val
                if v in ("(", "[", "{"):
                    depth += 1
                elif v in (")", "]", "}"):
                    depth -= 1
                elif depth == 0:
                    if v == "??":
                        nested_q += 1
                    elif v == ":":
                        if nested_q == 0:
                            colon_idx = i
                            break
                        nested_q -= 1
            if colon_idx != -1:
                cond_s = self._parse_expr(tokens[:q_idx])
                true_s = self._parse_expr(tokens[q_idx + 1 : colon_idx])
                false_s = self._parse_expr(tokens[colon_idx + 1 :])
                return f"({true_s} if {cond_s} else {false_s})"

        # 3. Linear & Bracket-Recursive Token Transformation
        out: List[str] = []
        n = len(tokens)
        i = 0

        while i < n:
            t = tokens[i]
            prev = tokens[i - 1] if i > 0 else None

            # Handle brackets & comprehensions: [...], {...}, (...)
            if t.val in ("[", "{", "("):
                open_b = t.val
                close_b = "]" if open_b == "[" else ("}" if open_b == "{" else ")")
                close_idx = self._find_matching_bracket(tokens, i, open_b, close_b)
                inner = tokens[i + 1 : close_idx]
                rendered_inner = self._parse_bracket_inner(inner, open_b)
                out.append(f"{open_b}{rendered_inner}{close_b}")
                i = close_idx + 1
                continue

            # Implicit self attribute: .attr -> self.attr
            if t.val == "." and i + 1 < n and tokens[i + 1].kind == "IDENT":
                is_attr_access = prev is not None and (
                    prev.kind in EXPR_END_KINDS or prev.val in EXPR_END_VALS
                )
                if not is_attr_access:
                    out.append(f"self.{tokens[i + 1].val}")
                    i += 2
                    continue

            # Positional parameter shorthand: $0, $1
            if t.kind == "POS_ARG":
                arg_idx = int(t.val[1:])
                if self.func_param_stack and arg_idx < len(self.func_param_stack[-1]):
                    out.append(self.func_param_stack[-1][arg_idx])
                else:
                    out.append(f"_arg{arg_idx}")
                i += 1
                continue

            # Macro references: #T, #np, #dc, etc.
            if t.kind == "MACRO":
                if t.val in CONST_MACROS:
                    out.append(CONST_MACROS[t.val])
                elif t.val in LIB_MACROS:
                    self.used_macros.add(t.val)
                    out.append(LIB_MACROS[t.val][2])
                else:
                    raise SyntaxError(f"Unknown PyDense macro: {t.val}")
                i += 1
                continue

            # Builtin references: %l, %p, etc.
            if t.kind == "BUILTIN":
                if t.val in BUILTIN_MACROS:
                    out.append(BUILTIN_MACROS[t.val])
                else:
                    raise SyntaxError(f"Unknown PyDense builtin: {t.val}")
                i += 1
                continue

            # Operators & Keywords
            if t.val == "&&":
                out.append(" and ")
            elif t.val == "||":
                out.append(" or ")
            elif t.val == "!":
                out.append(" not ")
            elif t.val == "@in":
                out.append(" in ")
            elif t.val == "!@in":
                out.append(" not in ")
            elif t.val == "@is":
                out.append(" is ")
            elif t.val == "!@is":
                out.append(" is not ")
            elif t.val == "@aw":
                out.append("await ")
            elif t.val == "^|":
                out.append(" ^ ")
            elif t.val == ",":
                out.append(", ")
            else:
                if out and out[-1] and out[-1][-1].isalnum() and t.val[0].isalnum():
                    out.append(" ")
                out.append(t.val)
            i += 1

        return "".join(out).strip()

    def _find_matching_bracket(self, tokens: List[Token], start: int, open_b: str, close_b: str) -> int:
        depth = 0
        for i in range(start, len(tokens)):
            if tokens[i].val == open_b:
                depth += 1
            elif tokens[i].val == close_b:
                depth -= 1
                if depth == 0:
                    return i
        raise SyntaxError(f"Unclosed bracket '{open_b}' in PyDense expression")

    def _parse_bracket_inner(self, inner: List[Token], open_b: str) -> str:
        if not inner:
            return ""

        # Check if this bracket contains a comprehension: top-level '~' or '~@' followed by ':'
        comp_indices: List[Tuple[int, bool]] = []
        depth = 0
        for idx, tok in enumerate(inner):
            if tok.val in ("(", "[", "{"):
                depth += 1
            elif tok.val in (")", "]", "}"):
                depth -= 1
            elif depth == 0 and tok.val in ("~", "~@"):
                if self._find_top_level(inner, {":"}, idx + 1) != -1:
                    comp_indices.append((idx, tok.val == "~@"))

        if comp_indices:
            first_tilde, _ = comp_indices[0]
            elt_toks = inner[:first_tilde]

            if open_b == "{":
                colon_idx = self._find_top_level(elt_toks, {":"})
                if colon_idx != -1:
                    k_str = self._parse_expr(elt_toks[:colon_idx])
                    v_str = self._parse_expr(elt_toks[colon_idx + 1 :])
                    elt_str = f"{k_str}: {v_str}"
                else:
                    elt_str = self._parse_expr(elt_toks)
            else:
                elt_str = self._parse_expr(elt_toks)

            clauses: List[str] = []
            for c_i, (t_pos, is_async) in enumerate(comp_indices):
                end_pos = comp_indices[c_i + 1][0] if c_i + 1 < len(comp_indices) else len(inner)
                clause_toks = inner[t_pos + 1 : end_pos]
                colon_pos = self._find_top_level(clause_toks, {":"})
                target_str = self._parse_expr(clause_toks[:colon_pos])

                rest_toks = clause_toks[colon_pos + 1 :]
                q_pos = self._find_top_level(rest_toks, {"?"})
                for_kw = "async for" if is_async else "for"
                if q_pos != -1:
                    iter_str = self._parse_expr(rest_toks[:q_pos])
                    cond_str = self._parse_expr(rest_toks[q_pos + 1 :])
                    clauses.append(f"{for_kw} {target_str} in {iter_str} if {cond_str}")
                else:
                    iter_str = self._parse_expr(rest_toks)
                    clauses.append(f"{for_kw} {target_str} in {iter_str}")

            return f"{elt_str} {' '.join(clauses)}"

        # Dict or Set literal (including **kwargs dict unpacking)
        if open_b == "{":
            items = self._split_top_level(inner, ",")
            rendered_items: List[str] = []
            for item in items:
                if not item:
                    continue
                c_idx = self._find_top_level(item, {":"})
                if c_idx != -1:
                    k_s = self._parse_expr(item[:c_idx])
                    v_s = self._parse_expr(item[c_idx + 1 :])
                    rendered_items.append(f"{k_s}: {v_s}")
                else:
                    rendered_items.append(self._parse_expr(item))
            return ", ".join(rendered_items)

        # List literal or subscript/slice (including *args unpacking)
        if open_b == "[":
            items = self._split_top_level(inner, ",")
            rendered_items = []
            for item in items:
                if not item:
                    continue
                if self._find_top_level(item, {":"}) != -1:
                    parts = self._split_top_level(item, ":")
                    rendered_items.append(":".join(self._parse_expr(p) for p in parts))
                else:
                    rendered_items.append(self._parse_expr(item))
            return ", ".join(rendered_items)

        # Parentheses (...) — function call args, tuples (including 1-tuple `(x,)`), or grouping
        items = self._split_top_level(inner, ",")
        if len(items) == 1:
            return self._parse_expr(items[0])
        if len(items) == 2 and not items[1]:
            return f"{self._parse_expr(items[0])},"

        rendered_args: List[str] = []
        for item in items:
            if not item:
                continue
            eq_idx = self._find_top_level(item, {"="})
            if eq_idx != -1:
                k_s = self._parse_expr(item[:eq_idx])
                v_s = self._parse_expr(item[eq_idx + 1 :])
                rendered_args.append(f"{k_s}={v_s}")
            else:
                rendered_args.append(self._parse_expr(item))
        return ", ".join(rendered_args)

    def _split_top_level(self, tokens: List[Token], sep: str) -> List[List[Token]]:
        parts: List[List[Token]] = []
        curr: List[Token] = []
        depth = 0
        for t in tokens:
            if t.val in ("(", "[", "{"):
                depth += 1
                curr.append(t)
            elif t.val in (")", "]", "}"):
                depth -= 1
                curr.append(t)
            elif t.val == sep and depth == 0:
                parts.append(curr)
                curr = []
            else:
                curr.append(t)
        parts.append(curr)
        return parts


# ============================================================================
# 4. REVERSE DECOMPILER (Python AST -> .pyd)
# ============================================================================

class PyDenseDecompiler(ast.NodeVisitor):
    """Compresses standard Python AST into canonical, zero-whitespace PyDense (.pyd)."""

    def __init__(self, use_positional_args: bool = True, preserve_types: bool = True) -> None:
        self.use_positional_args = use_positional_args
        self.preserve_types = preserve_types
        self.class_depth = 0
        self.param_map_stack: List[Dict[str, str]] = []
        self.import_macro_map: Dict[str, str] = {}

        self.mod_to_macro: Dict[Tuple[str, Optional[str]], str] = {}
        for mac, (mod, attr, _) in LIB_MACROS.items():
            self.mod_to_macro[(mod, attr)] = mac

    def decompile(self, py_code: str) -> str:
        self.class_depth = 0
        self.param_map_stack.clear()
        self.import_macro_map.clear()
        tree = ast.parse(py_code)
        return self.visit_Module(tree)

    def _visit_block(self, stmts: List[ast.stmt]) -> str:
        parts = [self.visit(s) for s in stmts]
        parts = [p for p in parts if p]
        out = ""
        for idx, p in enumerate(parts):
            if idx > 0 and not out.endswith("}"):
                out += ";"
            out += p
        return "{" + out + "}"

    def _visit_bare_tuple_or_expr(self, node: ast.AST) -> str:
        """Emits tuple elements without outer parentheses for assignment/loop/return targets."""
        if isinstance(node, ast.Tuple):
            return ",".join(self.visit(e) for e in node.elts)
        return self.visit(node)

    def visit_Module(self, node: ast.Module) -> str:
        parts = [self.visit(s) for s in node.body]
        parts = [p for p in parts if p]
        out = ""
        for idx, p in enumerate(parts):
            if idx > 0 and not out.endswith("}"):
                out += ";"
            out += p
        return out

    def visit_Import(self, node: ast.Import) -> str:
        kept: List[str] = []
        for alias in node.names:
            asname = alias.asname or alias.name
            if (alias.name, None) in self.mod_to_macro:
                self.import_macro_map[asname] = self.mod_to_macro[(alias.name, None)]
            else:
                kept.append(f"{alias.name}={alias.asname}" if alias.asname else alias.name)
        return f">{','.join(kept)}" if kept else ""

    def visit_ImportFrom(self, node: ast.ImportFrom) -> str:
        mod = node.module or ""
        kept: List[str] = []
        for alias in node.names:
            asname = alias.asname or alias.name
            if (mod, alias.name) in self.mod_to_macro:
                self.import_macro_map[asname] = self.mod_to_macro[(mod, alias.name)]
            else:
                kept.append(f"{alias.name}={alias.asname}" if alias.asname else alias.name)
        return f">{mod}:{','.join(kept)}" if kept else ""

    def visit_ClassDef(self, node: ast.ClassDef) -> str:
        dec_prefix = "".join(f"@{self.visit(d)}" for d in node.decorator_list)
        bases = [self.visit(b) for b in node.bases]
        kw_bases = [f"{k.arg}={self.visit(k.value)}" if k.arg else f"**{self.visit(k.value)}" for k in node.keywords]
        all_bases = ",".join(bases + kw_bases)
        base_str = f"({all_bases})" if all_bases else ""
        self.class_depth += 1
        body_str = self._visit_block(node.body)
        self.class_depth -= 1
        return f"{dec_prefix}@c {node.name}{base_str}{body_str}"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> str:
        return self._handle_func(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> str:
        return self._handle_func(node, is_async=True)

    def _handle_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> str:
        is_static = any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in node.decorator_list)
        other_decs = [
            d for d in node.decorator_list
            if not (not is_async and isinstance(d, ast.Name) and d.id == "staticmethod")
        ]
        dec_prefix = "".join(f"@{self.visit(d)}" for d in other_decs)

        args = list(node.args.posonlyargs) + list(node.args.args)
        if self.class_depth > 0 and not is_static and args and args[0].arg == "self":
            args = args[1:]

        num_defaults = len(node.args.defaults)
        default_start = len(args) - num_defaults
        param_strs: List[str] = []
        param_map: Dict[str, str] = {}

        for i, arg in enumerate(args):
            if self.use_positional_args:
                param_map[arg.arg] = f"${i}"
            ann_s = f":{self.visit(arg.annotation)}" if (self.preserve_types and arg.annotation) else ""
            if i >= default_start:
                def_val = self.visit(node.args.defaults[i - default_start])
                param_strs.append(f"{arg.arg}{ann_s}={def_val}")
            else:
                param_strs.append(f"{arg.arg}{ann_s}")

        if node.args.vararg:
            va = node.args.vararg
            ann_s = f":{self.visit(va.annotation)}" if (self.preserve_types and va.annotation) else ""
            param_strs.append(f"*{va.arg}{ann_s}")
        elif node.args.kwonlyargs:
            param_strs.append("*")

        for kw_arg, kw_def in zip(node.args.kwonlyargs, node.args.kw_defaults):
            ann_s = f":{self.visit(kw_arg.annotation)}" if (self.preserve_types and kw_arg.annotation) else ""
            if kw_def is not None:
                param_strs.append(f"{kw_arg.arg}{ann_s}={self.visit(kw_def)}")
            else:
                param_strs.append(f"{kw_arg.arg}{ann_s}")

        if node.args.kwarg:
            ka = node.args.kwarg
            ann_s = f":{self.visit(ka.annotation)}" if (self.preserve_types and ka.annotation) else ""
            param_strs.append(f"**{ka.arg}{ann_s}")

        is_init = self.class_depth > 0 and node.name == "__init__" and not is_async and not is_static
        ret_str = ""
        if self.preserve_types and node.returns and not is_init:
            ret_str = f"->{self.visit(node.returns)}"

        self.param_map_stack.append(param_map)
        body_str = self._visit_block(node.body)
        self.param_map_stack.pop()

        params_joined = ",".join(param_strs)
        if is_init:
            return f"{dec_prefix}@i({params_joined}){body_str}"
        kw = "@af" if is_async else ("@sf" if is_static else "@f")
        return f"{dec_prefix}{kw} {node.name}({params_joined}){ret_str}{body_str}"

    def visit_Return(self, node: ast.Return) -> str:
        return f"^{self._visit_bare_tuple_or_expr(node.value)}" if node.value else "^"

    def visit_Delete(self, node: ast.Delete) -> str:
        return ""

    def visit_Assign(self, node: ast.Assign) -> str:
        targets = "=".join(self._visit_bare_tuple_or_expr(t) for t in node.targets)
        return f"{targets}={self._visit_bare_tuple_or_expr(node.value)}"

    def visit_AnnAssign(self, node: ast.AnnAssign) -> str:
        target_s = self.visit(node.target)
        if self.preserve_types or (node.value is None and self.class_depth > 0):
            ann_s = self.visit(node.annotation)
            if node.value is not None:
                return f"{target_s}:{ann_s}={self.visit(node.value)}"
            return f"{target_s}:{ann_s}"
        if node.value is None:
            return ""
        return f"{target_s}={self.visit(node.value)}"

    def visit_AugAssign(self, node: ast.AugAssign) -> str:
        op = self._binop_symbol(node.op) + "="
        return f"{self.visit(node.target)}{op}{self.visit(node.value)}"

    def visit_If(self, node: ast.If) -> str:
        out = f"?{self.visit(node.test)}{self._visit_block(node.body)}"
        curr_orelse = node.orelse
        while curr_orelse:
            if len(curr_orelse) == 1 and isinstance(curr_orelse[0], ast.If):
                elif_node = curr_orelse[0]
                out += f":?{self.visit(elif_node.test)}{self._visit_block(elif_node.body)}"
                curr_orelse = elif_node.orelse
            else:
                out += f":{self._visit_block(curr_orelse)}"
                break
        return out

    def visit_For(self, node: ast.For) -> str:
        return f"~{self._visit_bare_tuple_or_expr(node.target)}:{self.visit(node.iter)}{self._visit_block(node.body)}"

    def visit_AsyncFor(self, node: ast.AsyncFor) -> str:
        return f"~@{self._visit_bare_tuple_or_expr(node.target)}:{self.visit(node.iter)}{self._visit_block(node.body)}"

    def visit_While(self, node: ast.While) -> str:
        return f"~?{self.visit(node.test)}{self._visit_block(node.body)}"

    def visit_Break(self, node: ast.Break) -> str:
        return "^!"

    def visit_Continue(self, node: ast.Continue) -> str:
        return "^~"

    def visit_Raise(self, node: ast.Raise) -> str:
        return f"^@{self.visit(node.exc)}" if node.exc else "^@"

    def visit_Try(self, node: ast.Try) -> str:
        out = f"!{self._visit_block(node.body)}"
        for h in node.handlers:
            exc_t = self.visit(h.type) if h.type else ""
            exc_n = f":{h.name}" if h.name else ""
            out += f"!{exc_t}{exc_n}{self._visit_block(h.body)}"
        if node.finalbody:
            out += f"!*{self._visit_block(node.finalbody)}"
        return out

    def visit_With(self, node: ast.With) -> str:
        item = node.items[0]
        ctx = self.visit(item.context_expr)
        opt = f":{self._visit_bare_tuple_or_expr(item.optional_vars)}" if item.optional_vars else ""
        return f"@w {ctx}{opt}{self._visit_block(node.body)}"

    def visit_AsyncWith(self, node: ast.AsyncWith) -> str:
        item = node.items[0]
        ctx = self.visit(item.context_expr)
        opt = f":{self._visit_bare_tuple_or_expr(item.optional_vars)}" if item.optional_vars else ""
        return f"@wa {ctx}{opt}{self._visit_block(node.body)}"

    def visit_Expr(self, node: ast.Expr) -> str:
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return ""
        return self.visit(node.value)

    def visit_Yield(self, node: ast.Yield) -> str:
        return f"^>{self.visit(node.value)}" if node.value else "^>"

    def visit_Await(self, node: ast.Await) -> str:
        return f"@aw {self.visit(node.value)}"

    def visit_Starred(self, node: ast.Starred) -> str:
        return f"*{self.visit(node.value)}"

    # --- Expressions ---

    def visit_Lambda(self, node: ast.Lambda) -> str:
        args = ",".join(a.arg for a in node.args.args)
        return f"\\{args}:{self.visit(node.body)}"

    def visit_IfExp(self, node: ast.IfExp) -> str:
        return f"{self.visit(node.test)}??{self.visit(node.body)}:{self.visit(node.orelse)}"

    def visit_BoolOp(self, node: ast.BoolOp) -> str:
        op = "&&" if isinstance(node.op, ast.And) else "||"
        return op.join(self.visit(v) for v in node.values)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> str:
        if isinstance(node.op, ast.Not):
            return f"!{self.visit(node.operand)}"
        if isinstance(node.op, ast.USub):
            return f"-{self.visit(node.operand)}"
        if isinstance(node.op, ast.UAdd):
            return f"+{self.visit(node.operand)}"
        if isinstance(node.op, ast.Invert):
            return f"~{self.visit(node.operand)}"
        return self.visit(node.operand)

    def visit_BinOp(self, node: ast.BinOp) -> str:
        op = self._binop_symbol(node.op)
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.left, ast.BinOp) and self._prec(node.left.op) < self._prec(node.op):
            left = f"({left})"
        if isinstance(node.right, ast.BinOp) and self._prec(node.right.op) <= self._prec(node.op):
            right = f"({right})"
        return f"{left}{op}{right}"

    def _binop_symbol(self, op: ast.operator) -> str:
        return {
            ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
            ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
            ast.BitAnd: "&", ast.BitOr: "|", ast.BitXor: "^|",
            ast.LShift: "<<", ast.RShift: ">>", ast.MatMult: "@",
        }[type(op)]

    def _prec(self, op: ast.operator) -> int:
        if isinstance(op, ast.Pow):
            return 4
        if isinstance(op, (ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.MatMult)):
            return 3
        if isinstance(op, (ast.Add, ast.Sub)):
            return 2
        return 1

    def visit_Compare(self, node: ast.Compare) -> str:
        out = self.visit(node.left)
        op_map = {
            ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
            ast.Gt: ">", ast.GtE: ">=", ast.In: "@in", ast.NotIn: "!@in",
            ast.Is: "@is", ast.IsNot: "!@is",
        }
        for op, comp in zip(node.ops, node.comparators):
            out += f"{op_map[type(op)]}{self.visit(comp)}"
        return out

    def visit_Call(self, node: ast.Call) -> str:
        fn = self.visit(node.func)
        args = [self.visit(a) for a in node.args]
        kwargs = [f"{k.arg}={self.visit(k.value)}" if k.arg else f"**{self.visit(k.value)}" for k in node.keywords]
        return f"{fn}({','.join(args + kwargs)})"

    def visit_Attribute(self, node: ast.Attribute) -> str:
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            return f".{node.attr}"
        return f"{self.visit(node.value)}.{node.attr}"

    def visit_Subscript(self, node: ast.Subscript) -> str:
        slice_str = self._visit_bare_tuple_or_expr(node.slice)
        return f"{self.visit(node.value)}[{slice_str}]"

    def visit_Slice(self, node: ast.Slice) -> str:
        lo = self.visit(node.lower) if node.lower else ""
        up = self.visit(node.upper) if node.upper else ""
        st = f":{self.visit(node.step)}" if node.step else ""
        return f"{lo}:{up}{st}"

    def visit_Name(self, node: ast.Name) -> str:
        name = node.id
        if self.param_map_stack and name in self.param_map_stack[-1]:
            return self.param_map_stack[-1][name]
        if name in self.import_macro_map:
            return self.import_macro_map[name]
        if name in REV_BUILTIN_MACROS:
            return REV_BUILTIN_MACROS[name]
        if name in REV_CONST_MACROS:
            return REV_CONST_MACROS[name]
        return name

    def visit_Constant(self, node: ast.Constant) -> str:
        if node.value is True:
            return "#T"
        if node.value is False:
            return "#F"
        if node.value is None:
            return "#N"
        if node.value is Ellipsis:
            return "..."
        return repr(node.value)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> str:
        return ast.unparse(node)

    def visit_List(self, node: ast.List) -> str:
        return "[" + ",".join(self.visit(e) for e in node.elts) + "]"

    def visit_Tuple(self, node: ast.Tuple) -> str:
        if not node.elts:
            return "()"
        if len(node.elts) == 1:
            return f"({self.visit(node.elts[0])},)"
        return "(" + ",".join(self.visit(e) for e in node.elts) + ")"

    def visit_Set(self, node: ast.Set) -> str:
        return "{" + ",".join(self.visit(e) for e in node.elts) + "}"

    def visit_Dict(self, node: ast.Dict) -> str:
        pairs = [
            f"**{self.visit(v)}" if k is None else f"{self.visit(k)}:{self.visit(v)}"
            for k, v in zip(node.keys, node.values)
        ]
        return "{" + ",".join(pairs) + "}"

    def visit_ListComp(self, node: ast.ListComp) -> str:
        return "[" + self.visit(node.elt) + self._comp_generators(node.generators) + "]"

    def visit_SetComp(self, node: ast.SetComp) -> str:
        return "{" + self.visit(node.elt) + self._comp_generators(node.generators) + "}"

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> str:
        return "(" + self.visit(node.elt) + self._comp_generators(node.generators) + ")"

    def visit_DictComp(self, node: ast.DictComp) -> str:
        kv = f"{self.visit(node.key)}:{self.visit(node.value)}"
        return "{" + kv + self._comp_generators(node.generators) + "}"

    def _comp_generators(self, generators: List[ast.comprehension]) -> str:
        clauses: List[str] = []
        for g in generators:
            conds = "&&".join(self.visit(c) for c in g.ifs)
            q_part = f"?{conds}" if conds else ""
            tilde = "~@" if g.is_async else "~"
            target_s = self._visit_bare_tuple_or_expr(g.target)
            clauses.append(f"{tilde}{target_s}:{self.visit(g.iter)}{q_part}")
        return "".join(clauses)


# ============================================================================
# 5. DIRECT EXECUTION RUNNER & COMPACT TRACEBACK HOOK
# ============================================================================

class PyDenseRunner:
    """Compiles and executes PyDense code directly in memory with single-line AI tracebacks."""

    def __init__(self) -> None:
        self.compiler = PyDenseCompiler()

    def execute(self, pyd_code: str, env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ns: Dict[str, Any] = env if env is not None else {}
        try:
            tree = self.compiler.compile_to_ast(pyd_code)
            code_obj = compile(tree, filename="<pydense>", mode="exec")
            exec(code_obj, ns)
            return ns
        except Exception as exc:
            raise RuntimeError(self.format_compact_error(exc)) from None

    @staticmethod
    def format_compact_error(exc: BaseException) -> str:
        tb = exc.__traceback__
        frame_name = "<module>"
        lineno = 1
        while tb is not None:
            if tb.tb_frame.f_code.co_filename == "<pydense>":
                frame_name = tb.tb_frame.f_code.co_name
                lineno = tb.tb_lineno
            tb = tb.tb_next
        return f"!Err[{frame_name}:L{lineno}]: {type(exc).__name__}({exc})"


# ============================================================================
# 6. SELF-TEST SUITE (DECORATORS, TYPES, UNPACKING & ASYNC)
# ============================================================================

def run_verification_suite() -> None:
    compiler = PyDenseCompiler()
    decompiler = PyDenseDecompiler(use_positional_args=True, preserve_types=True)
    runner = PyDenseRunner()

    print("=" * 74)
    print("TEST 1: Decorators (@dc, custom @scale, @[d1,d2]) & Type Annotations")
    print("=" * 74)
    pyd_dec_types = (
        "@f scale_ret(factor:float){@f dec(fn){@f wrap(*a,**kw){^$0(*a,**kw)*factor};^wrap};^dec};"
        "@#dc(frozen=#T)@c Quote{sym:str;bid:float;ask:float;tags:tuple[str,...]=()};"
        "@[scale_ret(10000.0)]@f mid_bps(q:Quote,offset:float=0.0)->float{"
        "m=($0.bid+$0.ask)/2.0;^(($0.ask-$0.bid)/m)+$1};"
        "q=Quote('BTCUSDT',60000.0,60030.0,('perp','tier1'));"
        "bps=mid_bps(q)"
    )
    print(f"Input .pyd ({len(pyd_dec_types)} chars):\n  {pyd_dec_types}\n")
    compiled_py = compiler.compile_to_source(pyd_dec_types)
    print("Compiled Python AST Source:")
    for line in compiled_py.splitlines():
        print(f"  {line}")

    ns = runner.execute(pyd_dec_types)
    print(f"\nExecution Output -> Quote={ns['q']}, mid_bps={ns['bps']:.4f} bps")
    assert abs(ns["bps"] - 4.99875) < 1e-4

    print("\n" + "=" * 74)
    print("TEST 2: Unpacking (*args, **kwargs, Iterable & Dict Unpacking) Round-Trip")
    print("=" * 74)
    py_unpack_src = '''
def merge_configs(base: dict[str, int], *overrides: dict[str, int], scale: int = 1, **extra: int) -> tuple[int, list[int], dict[str, int]]:
    merged: dict[str, int] = {**base, **extra}
    for ov in overrides:
        merged = {**merged, **ov}
    vals = [v * scale for v in merged.values()]
    first, *middle, last = [0, *vals, 999]
    return first + last, middle, merged
'''.strip()

    pyd_unpack = decompiler.decompile(py_unpack_src)
    pyd_stripped = PyDenseDecompiler(preserve_types=False).decompile(py_unpack_src)
    print(f"Original Python ({len(py_unpack_src)} chars)")
    print(f"Decompiled .pyd (with types: {len(pyd_unpack)} chars):\n  {pyd_unpack}")
    print(f"Decompiled .pyd (types stripped: {len(pyd_stripped)} chars):\n  {pyd_stripped}\n")

    ns_u = runner.execute(
        pyd_unpack + ";r=merge_configs({'a':1,'b':2},{'b':20,'c':30},scale=2,d=40)"
    )
    print(f"Unpacking Execution Result -> {ns_u['r']}")
    assert ns_u["r"] == (999, [2, 40, 60, 80], {"a": 1, "b": 20, "c": 30, "d": 40})

    print("\n" + "=" * 74)
    print("TEST 3: Full Async Suite (@af, @aw, ~@ async for, @wa async with)")
    print("=" * 74)
    pyd_async = (
        "@c AsyncStream{@i(n:int){.n=$0}@af __aenter__(){^self}@af __aexit__(*a){^#F}"
        "@af gen(){~i:%r(.n){@aw #as.sleep(0);^>i*10}}};"
        "@af collect(limit:int)->list[int]{out:list[int]= [];"
        "@wa AsyncStream($0):st{~@v:st.gen(){out.append(v)}};^out};"
        "async_res=#as.run(collect(4))"
    )
    print(f"Async .pyd ({len(pyd_async)} chars):\n  {pyd_async}")
    ns_a = runner.execute(pyd_async)
    print(f"Async Execution Result -> {ns_a['async_res']} (Expected: [0, 10, 20, 30])")
    assert ns_a["async_res"] == [0, 10, 20, 30]


if __name__ == "__main__":
    run_verification_suite()