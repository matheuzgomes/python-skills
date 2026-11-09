# Python 3.14

Contents: when this applies · lazy annotations · template strings · syntax · standard library ·
free threading and interpreters · sources

Use this file only when the project requires 3.14 or later (`requires-python = ">=3.14"`). The other
references assume 3.13, and nothing below runs there.

## Annotations are evaluated lazily (PEP 649, PEP 749)

- An annotation is evaluated only when something reads it, so a class can name itself, or a class
  defined later, without quotes and without `from __future__ import annotations`. The future
  import still works, but new code doesn't need it.
- Read annotations with `annotationlib.get_annotations(obj, format=...)`. `Format.VALUE`, the
  default, raises `NameError` for a name that doesn't exist; `Format.FORWARDREF` returns a
  `ForwardRef` in its place; `Format.STRING` returns the source text. Don't read `__annotations__`
  directly.

<!-- test: python>=3.14 -->
```python
from annotationlib import ForwardRef, Format, get_annotations

class Node:
    def add(self, child: Node) -> Node:  # no quotes needed
        return child

def load(path: Missing) -> None: ...  # Missing is never defined

assert get_annotations(Node.add) == {"child": Node, "return": Node}
assert isinstance(get_annotations(load, format=Format.FORWARDREF)["path"], ForwardRef)
assert get_annotations(load, format=Format.STRING) == {"path": "Missing", "return": "None"}
```

## Template strings (PEP 750)

`t"..."` builds a `string.templatelib.Template`, not a `str`. It keeps the literal text and the
interpolated values apart, so a library can escape or bind each value instead of pasting it into
the text. Use one where a library accepts templates for SQL, HTML or shell commands. A template
is not an f-string: `str(template)` doesn't give the joined text.

<!-- test: python>=3.14 -->
```python
from string.templatelib import Interpolation, Template

def to_query(template: Template) -> tuple[str, list[object]]:
    text: list[str] = []
    params: list[object] = []
    for part in template:
        if isinstance(part, Interpolation):
            text.append("?")
            params.append(part.value)
        else:
            text.append(part)
    return "".join(text), params

name = "x'); DROP TABLE users; --"
query = to_query(t"SELECT * FROM users WHERE name = {name}")
assert query == ("SELECT * FROM users WHERE name = ?", [name])
```

## Syntax

- `except ValueError, TypeError:` works without parentheses (PEP 758) when there is no `as`. With
  `as`, the parentheses are still required.
- A `return`, `break` or `continue` that leaves a `finally` block emits a `SyntaxWarning`
  (PEP 765), because it silently drops the exception in flight.

<!-- test: python>=3.14 -->
```python
import warnings

try:
    int("x")
except ValueError, TypeError:
    pass

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    compile("def f():\n    try:\n        1 / 0\n    finally:\n        return 1\n", "<example>", "exec")
assert caught[0].category is SyntaxWarning
```

## Standard library

- `uuid.uuid7()` makes time-ordered UUIDs. They sort by creation time, which keeps database index
  inserts local; prefer them to `uuid4()` for primary keys.
- `compression.zstd` brings Zstandard (PEP 784). The `compression` package also holds `gzip`,
  `bz2`, `lzma` and `zlib`.
- `map(..., strict=True)` raises when the iterables differ in length, like `zip(strict=True)`.
- `Path.copy()`, `copy_into()`, `move()` and `move_into()` replace most uses of `shutil`.
- `functools.Placeholder` leaves a positional slot open in `partial`.
- `heapq.heapify_max`, `heappush_max` and `heappop_max` give a max-heap without negating values.
- `tarfile` extracts with the `data` filter by default (see `security.md`).
- `python -m asyncio ps PID` and `python -m asyncio pstree PID` show the tasks of a running process.

<!-- test: python>=3.14 -->
```python
import functools
import heapq
import uuid
from compression import zstd
from pathlib import Path

first, second = uuid.uuid7(), uuid.uuid7()
assert first < second and first.version == 7

data = b"line\n" * 1000
assert len(zstd.compress(data)) < len(data) and zstd.decompress(zstd.compress(data)) == data

try:
    list(map(pow, [2, 3], [1], strict=True))
except ValueError:
    pass
else:
    raise AssertionError("lengths differ")

square = functools.partial(pow, functools.Placeholder, 2)
assert square(5) == 25

scores = [3, 9, 4]
heapq.heapify_max(scores)
assert heapq.heappop_max(scores) == 9

Path("report.txt").write_text("ok", encoding="utf-8")
assert Path("report.txt").copy(Path("backup.txt")).read_text(encoding="utf-8") == "ok"
```

## Free threading and interpreters

- The free-threaded build (`python3.14t`) is officially supported (PEP 779) but is not the
  default. An extension that doesn't declare support turns the GIL back on when imported, so check
  `sys._is_gil_enabled()` and measure before relying on threads for CPU-bound work.
- `concurrent.interpreters` (PEP 734) runs isolated interpreters in one process, each with its own
  GIL, and `concurrent.futures.InterpreterPoolExecutor` uses them like a process pool.

## Sources

- https://docs.python.org/3/whatsnew/3.14.html
- https://peps.python.org/pep-0649/ · https://peps.python.org/pep-0749/ ·
  https://docs.python.org/3.14/library/annotationlib.html
- https://peps.python.org/pep-0750/ · https://docs.python.org/3.14/library/string.templatelib.html
- https://peps.python.org/pep-0758/ · https://peps.python.org/pep-0765/
- https://peps.python.org/pep-0784/ · https://docs.python.org/3.14/library/compression.zstd.html
- https://docs.python.org/3.14/library/uuid.html#uuid.uuid7 · https://docs.python.org/3.14/library/pathlib.html
- https://peps.python.org/pep-0779/ · https://peps.python.org/pep-0734/ ·
  https://docs.python.org/3.14/howto/free-threading-python.html
