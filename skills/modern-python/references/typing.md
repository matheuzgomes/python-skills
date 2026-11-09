# Type hints in Python 3.13

Contents: legacy → modern table · generics · aliases · choosing parameter and return types · Protocol ·
narrowing · Literal, NewType and overload · classes · TypedDict · deprecation · runtime facts · sources

## Legacy → modern

| Legacy | Modern | Preferred since |
|---|---|---|
| `List[int]`, `Dict[str, int]`, `Tuple[int, ...]`, `Set`, `FrozenSet`, `Type[C]` | `list[int]`, `dict[str, int]`, `tuple[int, ...]`, `set`, `frozenset`, `type[C]` | 3.9 |
| `typing.Callable`, `Iterable`, `Iterator`, `Sequence`, `Mapping`, `Generator`, `Awaitable` … | same names from `collections.abc` | 3.9 |
| `typing.DefaultDict`, `Deque`, `Counter`, `OrderedDict`, `ChainMap` | the `collections` classes | 3.9 |
| `typing.ContextManager` | `contextlib.AbstractContextManager` | 3.9 |
| `typing.Hashable`, `typing.Sized` | `collections.abc.Hashable`, `Sized` | 3.12 |
| `typing.Text` | `str` | 3.11 |
| `Optional[X]`, `Union[A, B]` | `X \| None`, `A \| B` | 3.10 |
| `T = TypeVar("T")` + `Generic[T]` | `class C[T]:`, `def f[T](...)` | 3.12 |
| `Alias: TypeAlias = ...` | `type Alias = ...` | 3.12 |
| `TypeVar("T", default=int)` | `class C[T = int]:` | 3.13 |
| `TypeGuard` for "is this an X" checks | `TypeIs` | 3.13 |
| `AnyStr` | `def f[S: (str, bytes)](x: S) -> S` | 3.13 (deprecated) |
| Hand-written `DeprecationWarning` | `@warnings.deprecated("...")` | 3.13 |

The old `typing` aliases still work without warnings, but new code should not use them.

## Generics (PEP 695)

Type parameters live in brackets after the name and are scoped to that definition.

```python
from collections.abc import Hashable, Sequence

def first[T](items: Sequence[T]) -> T:
    return items[0]

def dedupe[K: Hashable](items: list[K]) -> list[K]:        # bound
    return list(dict.fromkeys(items))

def concat[S: (str, bytes)](a: S, b: S) -> S:               # constrained
    return a + b

class Stack[T]:
    def __init__(self) -> None:
        self._items: list[T] = []
    def push(self, item: T) -> None:
        self._items.append(item)
    def pop(self) -> T:
        return self._items.pop()

class Response[T = str]:                                     # default (3.13)
    def __init__(self, body: T) -> None:
        self.body = body

assert first("abc") == "a" and concat("a", "b") == "ab"
s = Stack[int](); s.push(1); assert s.pop() == 1
```

Parameters without a default cannot follow ones with a default (`SyntaxError`). Variance is inferred,
so there are no `covariant=`/`contravariant=` flags.

## Type aliases

```python
type JSON = dict[str, JSON] | list[JSON] | str | int | float | bool | None   # recursive, lazy
type Pair[T] = tuple[T, T]

def swap[T](p: Pair[T]) -> Pair[T]:
    return (p[1], p[0])

assert swap((1, 2)) == (2, 1)
```

The value of a `type` alias is evaluated lazily, so forward and recursive references need no quotes.

## Choosing parameter and return types

- Accept the most abstract type you need (`Iterable`, `Sequence`, `Mapping`), return a concrete one
  (`list`, `dict`).
- "Accepts anything": use `object`, not `Any`. `Any` switches checking off; `object` keeps it on.
- `X | None` makes a value nullable; the default `= None` is what makes the parameter optional. They
  are independent.
- Functions that never return: `-> Never` (3.11+). Exhaustiveness: `typing.assert_never(x)`.
- Methods returning their own class (fluent APIs, alternate constructors): `-> Self` (3.11+).

```python
from collections.abc import Iterable, Mapping

def total(prices: Mapping[str, float], items: Iterable[str]) -> float:
    return sum(prices[i] for i in items)

assert total({"a": 1.5}, ["a", "a"]) == 3.0
```

## Protocol for duck typing

```python
from typing import Protocol

class SupportsClose(Protocol):
    def close(self) -> None: ...

def shutdown(resources: list[SupportsClose]) -> None:
    for r in resources:
        r.close()

class Conn:                                 # no inheritance needed
    closed = False
    def close(self) -> None:
        self.closed = True

c = Conn(); shutdown([c]); assert c.closed
```

`@runtime_checkable` lets `isinstance` check that the members exist, not their signatures. That check
can be surprisingly slow; in performance-sensitive code use `hasattr()` instead.

## Narrowing helpers

`TypeIs` (3.13) narrows in both branches and intersects with the known type. Use `TypeGuard` only when
the narrowed type is not a subtype of the input (for example `list[object]` → `list[str]`).

```python
from typing import TypeIs

def is_str(value: object) -> TypeIs[str]:
    return isinstance(value, str)

def describe(value: int | str) -> str:
    if is_str(value):
        return value.upper()        # str here
    return str(value + 1)           # int here

assert describe("a") == "A" and describe(1) == "2"
```

## Literal, NewType and overload

- `Literal["open", "paid"]` is a closed set of values, for strings that come from outside, such as
  JSON, when an `Enum` would only add conversions. With `assert_never` in the last `case`, the
  checker reports a value that a `match` doesn't handle.
- `NewType("UserId", int)` makes ids of different things different types for the checker, at no
  cost at runtime, so passing an `OrderId` where a `UserId` goes is an error.
- `@overload` describes a return type that depends on the arguments. Only the undecorated
  implementation at the end runs.

```python
from typing import Literal, NewType, assert_never, overload

UserId = NewType("UserId", int)
OrderId = NewType("OrderId", int)
type Status = Literal["open", "paid", "cancelled"]

def label(status: Status) -> str:
    match status:
        case "open" | "paid":
            return status.title()
        case "cancelled":
            return "Cancelled"
        case _:
            assert_never(status)  # a checker error here when a new status is not handled

def cancel(order: OrderId, by: UserId) -> Status:  # cancel(user, order) is a checker error
    return "cancelled"

@overload
def first_or(items: list[str], default: None = None) -> str | None: ...
@overload
def first_or(items: list[str], default: str) -> str: ...
def first_or(items: list[str], default: str | None = None) -> str | None:
    return items[0] if items else default

assert type(UserId(7)) is int and label(cancel(OrderId(10), UserId(7))) == "Cancelled"
assert first_or([], "none") == "none" and first_or([]) is None
```

## Classes

```python
from typing import Self, override

class Base:
    def render(self) -> str:
        return "base"
    def with_name(self, name: str) -> Self:
        self.name = name
        return self

class Child(Base):
    @override                         # checker errors if Base has no render (3.12+)
    def render(self) -> str:
        return "child"

assert Child().with_name("x").render() == "child"
```

## TypedDict

- `ReadOnly[...]` (3.13) marks items the checker must not let you write.
- `NotRequired[...]`/`Required[...]` (3.11) mark individual keys.
- Type `**kwargs` precisely with `**kwargs: Unpack[Options]`.

```python
from typing import NotRequired, ReadOnly, TypedDict, Unpack

class Options(TypedDict):
    id: ReadOnly[int]
    retries: NotRequired[int]

def connect(**kwargs: Unpack[Options]) -> int:
    return kwargs.get("retries", 0)

assert connect(id=1, retries=3) == 3
```

## Deprecating an API

```python
import warnings
from warnings import deprecated

@deprecated("Use load_v2() instead")
def load() -> int:
    return 1

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    load()
assert caught[0].category is DeprecationWarning
```

Checkers also flag every use. At runtime the default filters hide `DeprecationWarning` outside
`__main__`, so tests should run with warnings enabled.

## Runtime facts

- Annotations are not enforced at runtime. Validate at trust boundaries and run a type checker (mypy or
  pyright) in CI.
- In 3.13 function and class annotations are still evaluated when the `def`/`class` runs. A name defined
  later in the module needs quotes or `from __future__ import annotations`. `type` aliases and
  type-parameter bounds are lazy and do not.
- Read annotations with `inspect.get_annotations()` (the documented best practice for 3.10–3.13), or
  `typing.get_type_hints()` when you need resolved types. Avoid touching `__annotations__` directly.

## Sources

- https://docs.python.org/3.13/library/typing.html
- https://docs.python.org/3.13/reference/compound_stmts.html (type parameter lists)
- https://docs.python.org/3.13/library/warnings.html
- https://peps.python.org/pep-0585/ · https://peps.python.org/pep-0604/ · https://peps.python.org/pep-0695/
- https://peps.python.org/pep-0696/ · https://peps.python.org/pep-0698/ · https://peps.python.org/pep-0702/
- https://peps.python.org/pep-0705/ · https://peps.python.org/pep-0742/
- https://peps.python.org/pep-0586/ (Literal) · https://docs.python.org/3.13/library/typing.html#newtype ·
  https://docs.python.org/3.13/library/typing.html#typing.overload
- https://docs.python.org/3/whatsnew/3.11.html · https://docs.python.org/3/whatsnew/3.12.html ·
  https://docs.python.org/3/whatsnew/3.13.html
- https://docs.python.org/3/howto/annotations.html
- https://docs.python.org/3/whatsnew/3.14.html (lazy annotations arrive in 3.14)
