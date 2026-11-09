# Writing for Python 3.10–3.12

Contents: what to use instead · generics · typing_extensions · standard library · exception
groups and TOML · asyncio · sources

The other references assume 3.13. When `requires-python` or the CI matrix says the project still
supports an older version, the code must run there too. Use the replacements below, and keep the
project's minimum: raising it is the project's decision, not a side effect of a change.

## What to use instead

| In these references | Since | On older versions |
|---|---|---|
| `def f[T]`, `class C[T]`, `type X = ...` | 3.12 | `TypeVar`, `Generic[T]`, `X: TypeAlias = ...` |
| `@override` | 3.12 | `typing_extensions.override` |
| `TypeIs`, `ReadOnly`, `TypeVar` defaults | 3.13 | `typing_extensions` |
| `@warnings.deprecated` | 3.13 | `typing_extensions.deprecated` |
| `Self`, `Never`, `assert_never`, `LiteralString`, `Required`, `NotRequired` | 3.11 | `typing_extensions` |
| `copy.replace` | 3.13 | `dataclasses.replace`, `NamedTuple._replace` |
| `itertools.batched` | 3.12 | a loop over `islice` |
| `Path.walk` | 3.12 | `os.walk` |
| the outer quotes reused inside an f-string (PEP 701) | 3.12 | different quotes inside |
| `sum()` of floats without drift | 3.12 | `math.fsum` |
| `asyncio.TaskGroup`, `asyncio.timeout` | 3.11 | `gather` with `wait_for`, or AnyIO task groups |
| `ExceptionGroup`, `except*` | 3.11 | the `exceptiongroup` backport and its `catch()` |
| `BaseException.add_note` | 3.11 | none; put the context in the message |
| `enum.StrEnum` | 3.11 | `class C(str, Enum)` and `.value` |
| `tomllib` | 3.11 | `tomli` |
| `datetime.UTC`, `fromisoformat` with `Z` | 3.11 | `timezone.utc`, `Z` replaced by `+00:00` |
| `contextlib.chdir`, `hashlib.file_digest` | 3.11 | `os.chdir` in `try`/`finally`, a read loop |
| `tarfile` with `filter="data"` | 3.12 | also in 3.10.12+ and 3.11.4+ |

`match`, `X | Y`, the dataclass options `slots=` and `kw_only=`, and parenthesized context
managers all work from 3.10.

## Generics

<!-- test: python>=3.10 -->
```python
from collections.abc import Sequence
from typing import Generic, TypeAlias, TypeVar

T = TypeVar("T")
Pair: TypeAlias = tuple[int, int]  # 3.12: type Pair = tuple[int, int]

def first(items: Sequence[T]) -> T:  # 3.12: def first[T](items: Sequence[T]) -> T
    return items[0]

class Box(Generic[T]):  # 3.12: class Box[T]:
    def __init__(self, item: T) -> None:
        self.item = item

origin: Pair = (0, 0)
assert first("abc") == "a" and Box(3).item == 3 and origin == (0, 0)
```

## typing_extensions

`typing_extensions` backports the newer names in `typing` to old versions, and on a version that
already has a name it usually re-exports it. Code that imports it at runtime needs it as a regular
dependency, not a dev-only one.

<!-- test: python>=3.10; deps=typing_extensions -->
```python
from typing_extensions import Self, TypeIs, deprecated, override

class Shape:
    def area(self) -> float:
        return 0.0

    def copy(self) -> Self:
        return self

class Square(Shape):
    def __init__(self, side: float) -> None:
        self.side = side

    @override
    def area(self) -> float:
        return self.side**2

def is_text(value: object) -> TypeIs[str]:
    return isinstance(value, str)

@deprecated("use Shape.area()")
def surface(shape: Shape) -> float:  # calling it emits a DeprecationWarning
    return shape.area()

assert Square(2).area() == 4 and is_text("a") and not is_text(1)
```

## Standard library

On 3.10, a `str` mixin enum formats as its value in an f-string, while from 3.11 it formats as
`Color.RED`, and `str()` gives `Color.RED` on every version. Read `.value` so the output stays the
same on all of them.

<!-- test: python>=3.10 -->
```python
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from itertools import islice
from typing import TypeVar

T = TypeVar("T")

def batched(items: Iterable[T], n: int) -> Iterator[tuple[T, ...]]:  # 3.12: itertools.batched
    iterator = iter(items)
    while batch := tuple(islice(iterator, n)):
        yield batch

@dataclass(frozen=True)
class Point:
    x: int
    y: int

class Color(str, Enum):  # 3.11: enum.StrEnum
    RED = "red"

assert list(batched("abcde", 2)) == [("a", "b"), ("c", "d"), ("e",)]
assert replace(Point(1, 2), y=5) == Point(1, 5)  # 3.13: copy.replace
stamp = datetime.fromisoformat("2026-11-08T12:00:00Z".replace("Z", "+00:00"))  # 3.11 reads Z
assert stamp.tzinfo == timezone.utc  # 3.11: datetime.UTC
assert Color.RED == "red" and Color.RED.value == "red"
```

## Exception groups and TOML

The `exceptiongroup` backport gives 3.10 `ExceptionGroup` and `catch()`, which does what
`except*` does. From 3.11 it re-exports the built-in classes. `except*` itself is syntax, so
3.10 can't parse a file that uses it.

<!-- test: python>=3.10; deps=exceptiongroup tomli -->
```python
import sys

from exceptiongroup import BaseExceptionGroup, ExceptionGroup, catch

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

assert tomllib.loads("port = 8080") == {"port": 8080}

failures: list[str] = []

def record(group: BaseExceptionGroup) -> None:
    failures.extend(str(exc) for exc in group.exceptions)

with catch({ValueError: record}):  # 3.11: except* ValueError as group
    raise ExceptionGroup("batch", [ValueError("row 1"), ValueError("row 2")])
assert failures == ["row 1", "row 2"]
```

## asyncio

On 3.10, bound the whole operation with `wait_for` and run the calls with `gather`. Unlike a
`TaskGroup`, `gather` doesn't cancel the other calls when one fails; they keep running unless you
cancel them. If the project already uses AnyIO, its task groups behave like `TaskGroup` on 3.10.

<!-- test: python>=3.10 -->
```python
import asyncio

async def fetch(n: int) -> int:
    await asyncio.sleep(0)
    return n * 2

async def main() -> list[int]:
    # 3.11: async with asyncio.timeout(1): async with asyncio.TaskGroup() as tg: ...
    return await asyncio.wait_for(asyncio.gather(fetch(1), fetch(2)), timeout=1)

assert asyncio.run(main()) == [2, 4]
```

## Sources

- https://docs.python.org/3/whatsnew/3.11.html · https://docs.python.org/3/whatsnew/3.12.html ·
  https://docs.python.org/3/whatsnew/3.13.html
- https://typing-extensions.readthedocs.io/ · https://docs.python.org/3.13/library/typing.html
- https://peps.python.org/pep-0695/ · https://peps.python.org/pep-0696/ · https://peps.python.org/pep-0701/
- https://pypi.org/project/exceptiongroup/ · https://pypi.org/project/tomli/
- https://docs.python.org/3.13/library/asyncio-task.html#asyncio.gather ·
  https://docs.python.org/3.13/library/enum.html#enum.StrEnum
- https://peps.python.org/pep-0706/ (tarfile filters, backported to 3.8.17+, 3.9.17+, 3.10.12+, 3.11.4+)
