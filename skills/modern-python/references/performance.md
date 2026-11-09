# Performance

Contents: measure first · complexity · loops and built-ins · memory · caching · I/O ·
CPU-bound work · sources

Write the clear version first. Make it faster only where a measurement says the time goes, and
keep the measurement so the next change can be compared with it.

## Measure first

- `python -m timeit -s "setup" "statement"` times a small piece of code. It repeats the run and
  reports the best, which is the least disturbed by the rest of the machine.
- `python -m cProfile -s cumulative app.py` shows which functions take the time, counting what
  they call. Optimize the top entries only.
- `tracemalloc` shows where memory is allocated and how high it peaks.
- `python -X importtime -c "import app"` shows slow imports, which matter for CLIs and serverless
  starts.

Never assert a duration in a test: it fails on a slow CI machine. Assert the result, and check the
complexity with a count or a size, as in the memory example below.

## Complexity beats tricks

Most slow Python is the wrong algorithm, not slow syntax:

| Slow on large inputs | Instead | See |
|---|---|---|
| `x in a_list` inside a loop | build a `set` or `dict` once | `collections.md` |
| `list.pop(0)`, `list.insert(0, x)` | `collections.deque` | `collections.md` |
| a nested loop to match two lists | index one list in a `dict` by key | below |
| sorting again after each insert | `bisect.insort`, or sort once at the end | `collections.md` |
| `s += piece` in a loop | collect the pieces, then `"".join(pieces)` | |
| one query per item (N+1) | one query for all items | |

```python
from collections import defaultdict

orders = [(1, "pen"), (2, "ink"), (1, "pad")]   # (customer_id, item)
customers = [(1, "Ana"), (2, "Bruno")]

# avoid: len(customers) * len(orders) steps
#   [(name, item) for cid, name in customers for oid, item in orders if oid == cid]
items_by_customer: defaultdict[int, list[str]] = defaultdict(list)
for customer_id, item in orders:   # len(orders) steps
    items_by_customer[customer_id].append(item)
joined = [(name, item) for cid, name in customers for item in items_by_customer.get(cid, [])]
assert joined == [("Ana", "pen"), ("Ana", "pad"), ("Bruno", "ink")]
```

## Loops and built-ins

- Built-ins and the standard library run in C: `sum`, `min`, `max`, `any`, `all`, `sorted(key=)`,
  `str.join`, `itertools`, `collections.Counter`. A comprehension is faster than a loop that calls
  `append`.
- Move work that doesn't change out of the loop: a compiled pattern, a lookup table, a conversion
  of the same value.
- Don't trade clarity for tricks such as binding methods to locals, unless a profile shows the
  loop is the hot spot and a benchmark shows the gain.

## Memory

- Stream data you only read once: iterate a file line by line, pass a generator expression to
  `sum` or `max`, and read query results in batches. A list holds every item at the same time.
- Many small objects: `@dataclass(slots=True)` drops the per-instance `__dict__`.
- Large numeric data: `array.array`, `bytes`, or NumPy, instead of a list of Python ints.

```python
import tracemalloc

tracemalloc.start()
total = sum([n * n for n in range(100_000)])  # the list exists in full first
_, peak_list = tracemalloc.get_traced_memory()
tracemalloc.reset_peak()
assert sum(n * n for n in range(100_000)) == total  # one item at a time
_, peak_generator = tracemalloc.get_traced_memory()
tracemalloc.stop()
assert peak_list > 100 * peak_generator
```

## Caching

- `functools.cache` and `lru_cache(maxsize=...)` memoize a pure function of hashable arguments
  (see `functions-and-decorators.md`). Prefer a bounded `lru_cache` for long-running processes:
  `cache` never forgets.
- On a method, either one keeps every `self` alive for as long as the cache lives (B019). Cache a
  module-level function instead, or use `functools.cached_property` for a per-instance value.
- A cache of something that changes (a row, a file, a config) needs an expiry, or it serves stale
  data.

## I/O

Most slow services wait on I/O, not on Python:

- Batch: one query for many rows, `executemany`, bulk inserts, one HTTP call with many items.
- Reuse connections: a pool for the database and one HTTP client per process, not one per request.
- Run independent I/O concurrently with asyncio (see `concurrency.md`), and never block the event
  loop: ruff flags `time.sleep` (ASYNC251), blocking HTTP (ASYNC210), `subprocess` (ASYNC221) and
  `open` (ASYNC230) inside `async def`.

## CPU-bound work

On the default build, the GIL lets only one thread run Python code at a time, so threads don't
speed up pure-Python computation. Use processes (`concurrent.futures.ProcessPoolExecutor`), move
the hot loop into NumPy or a compiled extension, or try the free-threaded build when every
dependency supports it (see `concurrency.md`).

## Sources

- https://docs.python.org/3.13/library/timeit.html · https://docs.python.org/3.13/library/profile.html
- https://docs.python.org/3.13/library/tracemalloc.html ·
  https://docs.python.org/3.13/using/cmdline.html#cmdoption-X (`importtime`)
- https://wiki.python.org/moin/TimeComplexity
- https://docs.python.org/3.13/library/functools.html · https://docs.python.org/3.13/library/collections.html
- https://docs.python.org/3.13/library/concurrent.futures.html ·
  https://docs.python.org/3.13/howto/free-threading-python.html
- https://docs.astral.sh/ruff/rules/ (ASYNC, B019)
