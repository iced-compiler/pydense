---
name: pydense
description: Write and execute ultra-compact, zero-whitespace Python-isomorphic code (.pyd) to reduce output tokens by 50%.
---

# PyDense (.pyd) Language Specification

You are fluent in **PyDense**, a whitespace-free, 1-to-1 AST-isomorphic compression of Python. When asked to write PyDense (or inside `.pyd` blocks/tool calls), emit ONLY valid PyDense with zero unnecessary spaces or newlines.

## 1. Core Syntax Mapping (Python -> PyDense)
- **Scope & Delimiters**: No indentation. Wrap all blocks in `{...}`. Separate statements in a block with `;`. Omit trailing `;` before `}`.
- **Classes & Methods**:
  - `class A(B):` -> `@c A(B){...}`
  - `def __init__(self, a, b=1):` -> `@i(a,b=1){...}` (`self` is implicit in all `@c` methods)
  - `def fn(a, b):` -> `@f fn(a,b){...}` | `async def` -> `@af` | `@staticmethod` -> `@sf`
  - `self.x` -> `.x` | Positional arg shorthand: `$0`, `$1`, `$2` map to the function's 1st, 2nd, 3rd parameters.
  - `lambda a, b: a + b` -> `\a,b:a+b`
  - `return x` -> `^x` | `yield x` -> `^>x` | `break` -> `^!` | `continue` -> `^~` | `raise e` -> `^@e`
- **Control Flow & Logic**:
  - `if c: ... elif c2: ... else: ...` -> `?c{...}:?c2{...}:{...}`
  - `x if c else y` (ternary) -> `c??x:y`
  - `for x in it:` -> `~x:it{...}`
  - `while c:` -> `~?c{...}`
  - `try: ... except E as e: ... finally: ...` -> `!{...}!E:e{...}!*{...}`
  - `with expr as v:` -> `@w expr:v{...}`
  - Logical ops: `and` -> `&&` | `or` -> `||` | `not x` -> `!x` | `in` -> `@in` | `is` -> `@is`
- **Comprehensions**:
  - `[f(x) for x in it if c]` -> `[f(x)~x:it?c]`
  - `{k:v for k,v in it if c}` -> `{k:v~k,v:it?c}`
- **Imports**:
  - `import pkg as p` -> `>pkg=p` | `from pkg import a, b` -> `>pkg:a,b`

## 2. Pre-Bound Macros (Auto-Imported)
- **Constants**: `#T`=`True`, `#F`=`False`, `#N`=`None`
- **Libraries**: `#np`=`numpy`, `#pd`=`pandas`, `#sp`=`scipy`, `#os`=`os`, `#sys`=`sys`, `#js`=`json`, `#re`=`re`, `#m`=`math`, `#dt`=`datetime`, `#pl`=`pathlib.Path`, `#as`=`asyncio`
- **Builtins**: `%p`=`print`, `%l`=`len`, `%r`=`range`, `%e`=`enumerate`, `%z`=`zip`, `%s`=`sum`, `%m`=`map`, `%f`=`filter`, `%d`=`dict`, `%li`=`list`, `%st`=`set`, `%t`=`type`, `%i`=`isinstance`, `%a`=`abs`, `%mn`=`min`, `%mx`=`max`, `%rd`=`round`, `%o`=`open`

## 3. Rosetta Stone Examples

**Ex 1: Class, Init, Pos-Args & Numpy**
Python:
```python
import numpy as np
class EWMA:
    def __init__(self, span: int = 20):
        self.alpha = 2.0 / (span + 1.0)
        self.state = None
    def update(self, val: float) -> float:
        if self.state is None:
            self.state = val
        else:
            self.state = self.alpha * val + (1.0 - self.alpha) * self.state
        return self.state
