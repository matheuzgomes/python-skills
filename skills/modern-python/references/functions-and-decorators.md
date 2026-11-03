# Functions, closures and decorators

Contents: parameters · mutable defaults · scope and closures · decorators · caching · callables · sources

## Parameters

- Flags and options go after `*` so callers must name them: `def export(data, *, overwrite=False)`.
- A keyword-only parameter without a default is a required named argument. Prefer it to a positional
  boolean.
- Put parameters before `/` when their names are not part of the API (you may rename them later), or so
  `**kwargs` can accept keys that clash with them.

```python
def export(rows: list[dict[str, str]], path: str, /, *, overwrite: bool = False) -> int:
    return len(rows)

assert export([{"a": "1"}], "out.csv", overwrite=True) == 1
```

## Mutable defaults

A default is evaluated once, when the `def` runs, and is shared by every call.

```python
# avoid
def add_bad(item: str, bucket: list[str] = []) -> list[str]:
    bucket.append(item)
    return bucket
assert add_bad("a") == ["a"] and add_bad("b") == ["a", "b"]   # shared state leaks

# prefer
def add(item: str, bucket: list[str] | None = None) -> list[str]:
    bucket = [] if bucket is None else bucket
    bucket.append(item)
    return bucket
assert add("a") == ["a"] and add("b") == ["b"]
```

When `None` is a meaningful value, use a private sentinel instead: `_MISSING = object()` and
`if value is _MISSING:`. Copy mutable arguments you store (`self.items = list(items)`) unless sharing is the documented intent.

## Scope and closures

- **Any assignment** to a name anywhere in a function makes it local to the whole function. Reading it
  before the assignment raises `UnboundLocalError`.
- Rebinding a variable from an enclosing function (`=`, `+=`) needs `nonlocal`, whatever the type.
  Mutating it through a method (`items.append`) does not.
- Use a closure for one or two pieces of state. Use a class with `__call__` when the state has several
  fields, needs methods, or must be inspected in tests.

```python
from collections.abc import Callable

def make_counter() -> Callable[[], int]:
    count = 0
    def step() -> int:
        nonlocal count          # needed: `count += 1` rebinds
        count += 1
        return count
    return step

tick = make_counter()
tick(); assert tick() == 2
```

## Decorators

- Always wrap with `@functools.wraps(func)`. It copies `__name__`, `__doc__`, `__annotations__`,
  `__type_params__` (3.12+) and sets `__wrapped__`.
- Type with ParamSpec so the decorated function keeps its signature for type checkers.
- A decorator runs when the decorated `def` executes: at import time for module-level functions. Keep
  that step free of side effects other than registration.
- Measure durations with `time.perf_counter()`, not `time.time()`.

```python
import functools
import logging
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

def timed[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            log.debug("%s took %.6fs", func.__qualname__, time.perf_counter() - start)
    return wrapper

@timed
def double(x: int) -> int:
    """Return twice x."""
    return x * 2

assert double(4) == 8 and double.__name__ == "double" and double.__doc__ == "Return twice x."
```

**Decorator with arguments**: one more level, a factory returning the decorator.

```python
import functools
from collections.abc import Callable

def retry[**P, R](times: int) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(times):
                try:
                    return func(*args, **kwargs)
                except ConnectionError:
                    if attempt == times - 1:
                        raise
            raise AssertionError("unreachable")
        return wrapper
    return decorate

calls = 0
@retry(times=3)
def flaky() -> str:
    global calls
    calls += 1
    if calls < 3:
        raise ConnectionError
    return "ok"

assert flaky() == "ok" and calls == 3
```

**Reduce duplication with a registry decorator** instead of an if/elif chain of handlers.

```python
from collections.abc import Callable

HANDLERS: dict[str, Callable[[str], str]] = {}

def handles(kind: str) -> Callable[[Callable[[str], str]], Callable[[str], str]]:
    def register(func: Callable[[str], str]) -> Callable[[str], str]:
        HANDLERS[kind] = func
        return func                     # return the original: no wrapper needed
    return register

@handles("upper")
def to_upper(s: str) -> str:
    return s.upper()

assert HANDLERS["upper"]("hi") == "HI"
```

For dispatch on the type of the first argument, use `functools.singledispatch` instead.

## Caching

- `functools.cache` for unbounded memoization, `lru_cache(maxsize=n)` for bounded. Arguments must be
  hashable. Don't hand-roll a memo dict or a callable class for this.
- `lru_cache`/`cache` on a method put `self` in the cache key, so instances stay alive until evicted;
  with unbounded `cache`, forever. For argument-less methods use `cached_property` (its value lives
  and dies with the instance); otherwise use a bounded `lru_cache(maxsize=n)`.
- `cached_property` needs an instance `__dict__` (not compatible with `__slots__`/`slots=True`) and has
  no lock since 3.12.

```python
from functools import cache

@cache
def fib(n: int) -> int:
    return n if n < 2 else fib(n - 1) + fib(n - 2)

assert fib(80) == 23416728348467685
```

## Small callables

- Don't assign a `lambda` to a name; write a `def` (it gets a real name in tracebacks).
- Prefer `operator.itemgetter`/`attrgetter` and `functools.partial` to trivial lambdas.
- To type a callable with keyword arguments or overloads, use a `Protocol` with `__call__`.

```python
from functools import partial
from operator import itemgetter

rows = [("b", 2), ("a", 1)]
assert sorted(rows, key=itemgetter(1)) == [("a", 1), ("b", 2)]
parse_bin = partial(int, base=2)
assert parse_bin("101") == 5
```

## Sources

- https://docs.python.org/3.13/library/functools.html
- https://docs.python.org/3.13/reference/executionmodel.html
- https://docs.python.org/3.13/reference/compound_stmts.html (function definitions, type parameters)
- https://peps.python.org/pep-0612/ (ParamSpec)
- https://peps.python.org/pep-0695/
- https://docs.python.org/3.13/tutorial/controlflow.html (special parameters `/` and `*`)
- https://docs.python.org/3.13/faq/programming.html (caching methods, shared defaults)
- https://docs.python.org/3.13/library/time.html (`perf_counter`)
