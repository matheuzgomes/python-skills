# Modeling data: dataclass, NamedTuple, Enum

Contents: legacy → modern table · which builder · dataclass options · fields · post-init · hashing and
equality · modified copies · enums · parse at the edge · design smell · sources

## Legacy → modern

| Legacy | Modern | Since |
|---|---|---|
| `collections.namedtuple("P", "x y")` | `class P(NamedTuple): x: int; y: int` | — |
| Hand-written `__init__`/`__repr__`/`__eq__` | `@dataclass` | 3.7 |
| Manual `__slots__` on a dataclass | `@dataclass(slots=True)` | 3.10 |
| "Fields with defaults must come last" workarounds | `kw_only=True`, `field(kw_only=True)`, `KW_ONLY` | 3.10 |
| `obj._replace(...)` / `dataclasses.replace(...)` | `copy.replace(obj, ...)` (both still work) | 3.13 |
| `class Color(str, Enum)` | `class Color(StrEnum)` | 3.11 |
| `Optional[date]` field | `date \| None` | 3.10 |

## Which builder

| Need | Use |
|---|---|
| Value object: immutable, hashable, compared by value | `@dataclass(frozen=True, slots=True)` |
| Mutable entity with behavior | `@dataclass(slots=True)` (add `kw_only=True` with many fields) |
| Must behave as a tuple (unpacking, indexing, tuple APIs) | `typing.NamedTuple` |
| Fixed set of named constants | `Enum`, `StrEnum`, `IntEnum` |
| Untrusted input that must be validated | a validation library, or `__post_init__` checks |

**NamedTuple pitfall:** it *is* a tuple. `Point(1, 2) == (1, 2)` is `True`, and it unpacks and indexes.
Don't use it for domain values where that would hide bugs.

```python
from typing import NamedTuple

class Point(NamedTuple):
    x: int
    y: int

assert Point(1, 2) == (1, 2)          # equal to a plain tuple
```

## dataclass options (3.13 signature)

`dataclass(*, init=True, repr=True, eq=True, order=False, unsafe_hash=False, frozen=False,
match_args=True, kw_only=False, slots=False, weakref_slot=False)`

- `slots=True` returns a **new class**. Zero-argument `super()` in its methods raises `TypeError` up to
  3.13.13 (gh-90562: fixed in 3.14 and backported to 3.13.14). If older patch releases must work,
  write `super(Cls, self)`. Instances reject new attributes. Add `weakref_slot=True` if you need weak
  references.
- `order=True` compares fields as tuples **in declaration order**, so declare them in the intended
  sort order.
- `kw_only=True` removes the "no non-default after default" restriction, including in subclasses.

```python
from dataclasses import KW_ONLY, dataclass

@dataclass(frozen=True, slots=True)
class Money:
    amount: int
    currency: str = "BRL"

@dataclass(kw_only=True)
class Base:
    created_by: str = "system"

@dataclass(kw_only=True)
class Order(Base):
    id: int                            # required field after a defaulted one: fine with kw_only

@dataclass
class Query:
    text: str
    _: KW_ONLY
    limit: int = 10

assert Money(5) == Money(5, "BRL") and len({Money(5), Money(5)}) == 1
assert Order(id=1).created_by == "system"
assert Query("py", limit=5).limit == 5
```

## Fields

- Mutable defaults: always `field(default_factory=list)`. Since 3.11 any **unhashable** default raises
  `ValueError`, but mutable *hashable* objects (plain class instances) still slip through silently.
- `field(init=False)` for values computed in `__post_init__`.
- `field(repr=False)` for secrets; `field(compare=False)` for caches and metadata.
- `ClassVar[...]` for shared class-level state. An unannotated class attribute is not a field either,
  but `ClassVar` makes the intent explicit.
- `InitVar[...]` for constructor-only inputs that are not stored.
- Never name a field after its type (`date: date = None`): the default rebinds the name inside the class
  body and the annotation silently breaks. Import the module instead (`import datetime`).

```python
import datetime
from dataclasses import InitVar, dataclass, field
from typing import ClassVar

@dataclass
class Account:
    owner: str
    opened: datetime.date | None = None
    tags: list[str] = field(default_factory=list)
    token: str = field(default="", repr=False)
    balance: int = field(init=False, default=0)
    seed: InitVar[int] = 0
    instances: ClassVar[int] = 0

    def __post_init__(self, seed: int) -> None:
        self.balance = seed
        Account.instances += 1

a = Account("ana", seed=10)
assert a.balance == 10 and "token" not in repr(a) and Account.instances == 1
```

## __post_init__ and frozen classes

Validate and derive values in `__post_init__`. In a frozen dataclass, assign with
`object.__setattr__`, because plain assignment raises `FrozenInstanceError`.

```python
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class Range:
    start: int
    stop: int
    size: int = field(init=False)

    def __post_init__(self) -> None:
        if self.stop < self.start:
            raise ValueError("stop must be >= start")
        object.__setattr__(self, "size", self.stop - self.start)

assert Range(2, 5).size == 3
```

## Hashing and equality

| `eq` | `frozen` | `unsafe_hash` | `__hash__` |
|---|---|---|---|
| True (default) | False | False | set to `None`: instances are unhashable |
| True | True | False | generated from the fields |
| False | any | False | inherited from the base class (identity hash for `object`) |
| any | any | True | forced: don't use on mutable objects in sets or as dict keys |

A `__hash__` you write yourself is left alone in the first three rows; with `unsafe_hash=True` it is a
`TypeError`.

For hand-written classes: if you define `__eq__`, define `__hash__` over the same immutable state, or
the class becomes unhashable. A tuple is hashable only if every item is.

## Modified copies

`copy.replace(obj, **changes)` (3.13) works on dataclasses (frozen included), named tuples and any class
that defines `__replace__`. For dataclasses it calls `__init__`, so `__post_init__` validation runs
again. Passing an `init=False` field is an error: `TypeError` on 3.13+ (the 3.13 docs still say
`ValueError`, which is what 3.12 raised).

```python
import copy
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    host: str
    port: int = 80

prod = copy.replace(Config("dev.local"), host="prod.local")
assert prod == Config("prod.local", 80)
```

## Enums

```python
from enum import StrEnum, auto

class Status(StrEnum):
    ACTIVE = auto()            # value "active"
    BLOCKED = auto()

assert Status.ACTIVE == "active" and Status("blocked") is Status.BLOCKED
```

Compare members with `is` or `==`. In `match`, write `case Status.ACTIVE:` (a dotted name), never a bare
name.

## Parse at the edge

Convert outside data (a request body, a file, a queue message) into typed objects once, where it
enters the program, and reject it there with a clear error. Code past that point trusts its types
and never checks the same thing again. When the project uses pydantic, that model is the edge.

```python
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

@dataclass(frozen=True, slots=True)
class Coupon:
    code: str
    percent: Decimal

    def __post_init__(self) -> None:
        if not 0 < self.percent <= 100:
            raise ValueError(f"percent must be in (0, 100], got {self.percent}")

def parse_coupon(raw: Mapping[str, object]) -> Coupon:
    match raw:
        case {"code": str(code), "percent": str(percent)}:
            try:
                return Coupon(code, Decimal(percent))
            except InvalidOperation as exc:
                raise ValueError(f"percent is not a number: {percent!r}") from exc
        case _:
            raise ValueError("expected a code and a percent, both as strings")

assert parse_coupon({"code": "OFF10", "percent": "10"}) == Coupon("OFF10", Decimal("10"))
for bad in ({"code": "X"}, {"code": "X", "percent": "abc"}, {"code": "X", "percent": "150"}):
    try:
        parse_coupon(bad)
    except ValueError:
        continue
    raise AssertionError(bad)
```

## Design smell

A data class with no behavior, whose fields other modules keep manipulating, usually wants those
functions moved into it as methods. Plain data classes remain the right tool for DTOs, parsed payloads
and intermediate results.

## Sources

- https://docs.python.org/3.13/library/dataclasses.html
- https://docs.python.org/3.13/library/copy.html
- https://docs.python.org/3.13/library/enum.html
- https://docs.python.org/3.13/library/typing.html (NamedTuple, ClassVar)
- https://docs.python.org/3.13/library/collections.html (namedtuple)
- https://docs.python.org/3/whatsnew/3.10.html · https://docs.python.org/3/whatsnew/3.11.html ·
  https://docs.python.org/3/whatsnew/3.13.html
- https://docs.python.org/3.13/reference/datamodel.html (`__hash__` and `__eq__`)
- https://github.com/python/cpython/issues/90562 (slots and zero-argument `super()`)
