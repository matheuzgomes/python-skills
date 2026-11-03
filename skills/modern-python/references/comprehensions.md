# Comprehensions, generators and the walrus operator

## List comprehension or generator expression?

| Situation | Use |
|---|---|
| Consumer stops early: `any`, `all`, `next`, `in` | generator expression |
| Data is large or streaming (file lines, network pages) | generator expression or generator function |
| You need `len()`, indexing, or more than one pass | list comprehension |
| Feeding `sorted`, `tuple`, `str.join`, `list` | list comprehension is fine; these build the whole result anyway |

Since 3.12 (PEP 709) list, dict and set comprehensions are inlined into the enclosing function, so
they no longer cost a function call. Generator expressions are not inlined.

```python
words = ["alpha", "beta", "gamma"]
has_long = any(len(w) > 4 for w in words)          # stops at the first match
lengths = [len(w) for w in words]                  # reused below, so materialize
assert has_long and max(lengths) == 5 and sum(lengths) == 14
```

**A generator expression as the only argument needs no extra parentheses:** `sum(x * x for x in xs)`.

## Generators are single-use

Iterating a generator twice silently yields nothing the second time. Materialize first, or write a
function that returns a fresh generator on each call.

```python
evens = (n for n in range(6) if n % 2 == 0)
assert sum(evens) == 6
assert sum(evens) == 0          # already exhausted: a silent bug
```

## When a comprehension is too much

Expand into a loop or a generator function when there are more than two `for` clauses, more than one
condition, or side effects. Never use a comprehension only for its side effects.

```python
# avoid
log: list[str] = []
[log.append(f"saw {x}") for x in range(3)]

# prefer
log = []
for x in range(3):
    log.append(f"saw {x}")
assert log == ["saw 0", "saw 1", "saw 2"]
```

## Built-ins instead of map, filter and reduce

- Comprehensions read better than `map`/`filter` with a `lambda`. `map(str, xs)` with an existing
  function is fine.
- Prefer `sum`, `any`, `all`, `min`, `max`, `math.prod`, `str.join` over `functools.reduce`. Keep
  `reduce` for real folds that none of these express.
- `itertools.batched(xs, n)` (3.12+) chunks an iterable into tuples. Pass `strict=True` (3.13+) when a
  short final batch is an error, and `strict=False` to say explicitly that it is allowed.
  `itertools.pairwise` (3.10+) gives consecutive pairs.

```python
import math
from itertools import batched, pairwise

assert math.prod([2, 3, 4]) == 24
assert list(batched("abcde", 2, strict=False)) == [("a", "b"), ("c", "d"), ("e",)]
assert [b - a for a, b in pairwise([1, 4, 9])] == [3, 5]
```

## The walrus operator `:=`

Use it to avoid computing a value twice, in a filter plus result or in a read loop. Don't depend on the
variable leaking out of a comprehension: that is legal but hard to read.

```python
import io

def parse(s: str) -> int | None:
    return int(s) if s.isdigit() else None

raw = ["1", "x", "3"]
# avoid: parse() runs twice per item
nums = [parse(s) for s in raw if parse(s) is not None]
# prefer
nums = [n for s in raw if (n := parse(s)) is not None]
assert nums == [1, 3]

stream = io.BytesIO(b"abcdef")
chunks = []
while chunk := stream.read(4):
    chunks.append(chunk)
assert chunks == [b"abcd", b"ef"]
```

Restrictions (all `SyntaxError`): `:=` cannot rebind the comprehension's iteration variable, cannot
appear in its iterable expression, and cannot be used in a comprehension inside a class body.

## Sources

- https://peps.python.org/pep-0709/
- https://peps.python.org/pep-0572/
- https://docs.python.org/3.13/library/itertools.html
- https://docs.python.org/3/whatsnew/3.12.html (PEP 709, `itertools.batched`)
- https://docs.python.org/3/whatsnew/3.10.html (`itertools.pairwise`)
