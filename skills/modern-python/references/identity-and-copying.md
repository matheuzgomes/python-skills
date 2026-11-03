# Identity, copying and slicing

## `is` versus `==`

- `is` only for `None`, sentinels, enum members, and exact-type checks (`type(x) is T`).
- `==` for values. Never `is` with `str`, `int` or tuple values: whether two equal values are the same
  object is an implementation detail (caching, interning, constant folding). Since 3.8, `is` with a
  string or number literal emits a `SyntaxWarning`.
- `x == None` is not only unidiomatic: a custom `__eq__` may return any value, not just a bool, so the
  result can be wrong. `is None` can't be overridden.
- Empty check: `if not items:`. Truth check: `if flag:`. Never compare to `True`, `False`, `[]` or `""`.

## Sentinels

When `None` is a valid value, use a private sentinel to mean "not given".

```python
from typing import Final

_MISSING: Final = object()

def get(d: dict[str, object], key: str, default: object = _MISSING) -> object:
    if key in d:
        return d[key]
    if default is _MISSING:
        raise KeyError(key)
    return default

assert get({"a": None}, "a") is None and get({}, "b", None) is None
```

When the sentinel must appear in type hints, make it an `Enum` member (the approach PEP 484
recommends) so checkers can narrow `int | Missing` in each branch.

## Assignment never copies

Names are references. `b = a` shares the object; mutating through one is visible through the other.

| Need | Use |
|---|---|
| Shallow copy of a list, dict or set | `list(x)`, `x.copy()`, `dict(x)`, `copy.copy(x)` |
| Independent nested copy | `copy.deepcopy(x)` |
| Modified copy of a record | `copy.replace(obj, field=value)` (3.13) |

A shallow copy shares nested mutables.

```python
import copy

grid = [[0, 0], [0, 0]]
shallow = list(grid)
deep = copy.deepcopy(grid)
grid[0][0] = 1
assert shallow[0][0] == 1 and deep[0][0] == 0

rows = [[0] * 2] * 2          # avoid: the same inner list twice
rows[0][0] = 9
assert rows == [[9, 0], [9, 0]]
rows = [[0] * 2 for _ in range(2)]   # prefer
```

- In CPython, `tuple(t)` and `t[:]` return the same tuple object, not a copy. That is fine for an
  immutable value, but a tuple holding lists is not a defensive copy.
- `id()` values can be reused after an object is freed. Never store them as keys for objects you don't
  keep alive.

## Slicing

- Slicing a list, `str` or tuple builds a new object, a shallow **copy** (except the CPython full-slice
  shortcut on immutables above). To avoid copying, use `memoryview` for binary data or
  `itertools.islice` for iterators.
- Out-of-range slice bounds clamp silently; a single out-of-range index raises `IndexError`.
- Name fixed-width field positions with `slice` objects instead of scattering magic numbers.
- `reversed(seq)` to iterate backwards (no copy); `lst.reverse()` to reverse in place; `seq[::-1]`
  creates a reversed copy.
- Slice assignment takes an iterable. With a step (extended slice), the right side must have exactly the
  same length.

```python
SKU = slice(0, 6)
PRICE = slice(6, 12)
line = "A1B2C3  9.99"
assert line[SKU] == "A1B2C3" and float(line[PRICE]) == 9.99

nums = list(range(6))
nums[1:3] = [10]               # length may change
assert nums == [0, 10, 3, 4, 5]
assert nums[10:20] == []       # clamps, no IndexError
```

## Sources

- https://docs.python.org/3.13/reference/expressions.html#is-not (identity comparisons)
- https://docs.python.org/3.13/library/copy.html
- https://docs.python.org/3.13/library/stdtypes.html (sequence operations, slicing)
- https://docs.python.org/3.13/library/functions.html#id
- https://peps.python.org/pep-0008/ (programming recommendations)
- https://docs.python.org/3/whatsnew/3.8.html (`is` with literals warns)
- https://docs.python.org/3.13/reference/datamodel.html (rich comparisons)
- https://peps.python.org/pep-0484/ (singleton types in unions)
