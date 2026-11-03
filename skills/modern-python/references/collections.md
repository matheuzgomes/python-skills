# Choosing and using collections

Contents: choosing a container · sets · dicts · sorted data · numeric data · sources

## Choosing a container

| Need | Use | Not |
|---|---|---|
| Ordered, growing, same kind of items | `list` | — |
| Fixed-size record, dict key, "this never changes" | `tuple`, `NamedTuple`, frozen dataclass | `list` |
| Repeated membership tests, dedupe, set algebra | `set` | `x in some_list` inside a loop |
| Constant lookup table, set inside a set, set as dict key | `frozenset` | `set` (unhashable) |
| Queue or stack used from both ends, bounded buffer | `collections.deque` (`maxlen=n`) | `list.pop(0)`, `list.insert(0, x)` |
| Counting occurrences | `collections.Counter` | a dict-increment loop |
| Grouping values by key | `collections.defaultdict(list)` | `d.get(k, [])` plus reassignment |
| Layered lookups (CLI args > env > defaults) | `collections.ChainMap` | merging dicts by hand on every read |
| Millions of numbers of one C type | `array.array` or NumPy | `list[float]` |
| Kept sorted while inserting | `bisect.insort` on a list | `append` then `sort()` each time |

**Why tuple vs list is about meaning first.** A tuple says "fixed shape, position matters"; a list says
"many of the same thing". Pick by meaning; the smaller footprint is a side effect.

**deque caveats.** O(1) at both ends, but indexing into the middle is O(n). Use a list for random access.

```python
from collections import deque

recent = deque(maxlen=3)
for event in ["a", "b", "c", "d"]:
    recent.append(event)          # oldest item drops off automatically
assert list(recent) == ["b", "c", "d"]
```

## Sets

- Build the set **once**, outside the loop, then test membership against it.
- `{}` is an empty **dict**. Write `set()` for an empty set.
- Never rely on set iteration order. It is arbitrary and can change between runs.
- Operators (`& | - ^`) need set operands. Methods accept any iterables, several at once.
- `{*a, *b}` merges any iterables into a new set.

```python
allowed = frozenset({"read", "write"})          # constant lookup table
requested = ["read", "delete", "write"]
denied = [p for p in requested if p not in allowed]
assert denied == ["delete"]

tags = {"py"}.union(["typing"], ("async",))      # methods take any iterables
assert tags == {"py", "typing", "async"}
```

**Order-preserving dedupe** of hashable items: `list(dict.fromkeys(items))`.

```python
assert list(dict.fromkeys([3, 1, 3, 2, 1])) == [3, 1, 2]
```

**frozenset augmented assignment rebinds.** `fs |= other` creates a new frozenset and rebinds the name.
Other references still see the old object.

## Dicts

- Insertion order is guaranteed. Use `OrderedDict` only for `move_to_end`, `popitem(last=False)`, or
  order-sensitive equality.
- Grouping: `defaultdict(list)` when you create the dict; `d.setdefault(k, []).append(v)` when you don't.
- `defaultdict` creates a missing key on `d[k]`. Read without inserting via `k in d` or `d.get(k)`.
- Compare key sets with view operators: `a.keys() & b.keys()`, `a.keys() - b.keys()`. They accept any
  iterable on the right. `items()` views need hashable values; `values()` is not set-like.
- Never persist or compare `hash()` of `str` or `bytes` across processes: it is randomized per process.

```python
from collections import defaultdict

# avoid
index: dict[str, list[int]] = {}
for n, word in enumerate(["a", "b", "a"]):
    lines = index.get(word, [])
    lines.append(n)
    index[word] = lines

# prefer
grouped: defaultdict[str, list[int]] = defaultdict(list)
for n, word in enumerate(["a", "b", "a"]):
    grouped[word].append(n)
assert grouped == {"a": [0, 2], "b": [1]}
```

```python
from collections import Counter

votes = Counter(["py", "rs", "py", "go", "py"])
assert votes.most_common(1) == [("py", 3)]
assert votes.total() == 5                        # 3.10+
```

```python
old = {"host": "a", "port": 1, "debug": True}
new = {"host": "b", "port": 1, "timeout": 5}
assert old.keys() - new.keys() == {"debug"}      # removed keys
assert new.keys() - old.keys() == {"timeout"}    # added keys
```

## Sorted data

- `bisect.insort` keeps a list sorted. The search is O(log n) but the insert shifts items, O(n). For
  heavy insert workloads use a sorted-collection library.
- `key=` exists on bisect functions since 3.10. The key is **not** applied to the searched value, so
  pass the value already in key form.
- For exact-value lookups a dict is faster than bisect. Use bisect for ranges and "nearest" queries.

```python
import bisect

scores = [10, 20, 30]
bisect.insort(scores, 25)
assert scores == [10, 20, 25, 30]

limits = [1, 5, 20]                 # kg thresholds, sorted
fees = [10.0, 18.0, 35.0, 60.0]
def shipping_fee(weight: float) -> float:
    return fees[bisect.bisect_left(limits, weight)]
assert shipping_fee(0.5) == 10.0 and shipping_fee(5) == 18.0 and shipping_fee(21) == 60.0
```

## Numeric data

- `array.array` stores packed machine values. Check `array(code).itemsize` rather than assuming C
  widths: the typecode table lists minimum sizes only.
- Use typecode `'w'` (3.13+) for Unicode characters. `'u'` is deprecated.
- `tofile`/`fromfile` (with `with open(..., "rb")`) for fast binary I/O; `fromfile` raises `EOFError` if
  fewer items exist, but keeps the ones it read.
- `memoryview` slices without copying.
- `zip(a, b, strict=True)` when the inputs must have equal length.

```python
from array import array

samples = array("d", (i / 10 for i in range(5)))
view = memoryview(samples)
assert view.nbytes == len(samples) * samples.itemsize
assert list(zip("ab", [1, 2], strict=True)) == [("a", 1), ("b", 2)]
```

## Sources

- https://docs.python.org/3.13/library/collections.html
- https://docs.python.org/3.13/library/bisect.html
- https://docs.python.org/3.13/library/array.html
- https://docs.python.org/3.13/library/stdtypes.html
- https://docs.python.org/3/whatsnew/3.10.html (PEP 618, `zip(strict=True)`)
- https://docs.python.org/3/whatsnew/3.13.html (array `'w'`)
- https://docs.python.org/3.13/reference/datamodel.html (hash randomization)
