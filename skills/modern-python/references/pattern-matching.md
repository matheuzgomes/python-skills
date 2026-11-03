# Structural pattern matching (`match`)

## When to use it

Use `match` to dispatch on the **shape** of data: commands, parsed JSON, AST nodes, tagged tuples. For
plain value dispatch, `if`/`elif` or a dict of handlers is just as clear.

```python
def handle(command: list[str]) -> str:
    match command:
        case ["go", direction]:
            return f"moving {direction}"
        case ["drop", *items] if items:          # guard
            return f"dropping {len(items)}"
        case ["quit" | "exit"]:                  # OR pattern
            return "bye"
        case _:
            return "unknown"

assert handle(["go", "north"]) == "moving north"
assert handle(["drop", "a", "b"]) == "dropping 2"
assert handle(["exit"]) == "bye"
```

Order cases from specific to general. An irrefutable case (`case _:` or a bare name) must be last.

## Bare names capture, dotted names compare

The most common bug: a bare name in a `case` binds the subject instead of comparing to a constant.

```python
from enum import Enum

class Color(Enum):
    RED = 1
    BLUE = 2

def is_red(c: Color) -> bool:
    match c:
        case Color.RED:          # dotted name: compared with ==
            return True
        case _:
            return False

assert is_red(Color.RED) and not is_red(Color.BLUE)
```

Writing `case RED:` with a module-level `RED = 1` matches **every** value and rebinds `RED`. If such a
case is not the last one, the whole `match` is a `SyntaxError` (it makes the remaining patterns
unreachable).

## What sequence patterns don't match

- `str`, `bytes` and `bytearray` never match sequence patterns. Wrap them first, e.g. `match tuple(s):`.
- Iterators and generators are not sequences. Materialize them with `list(...)` first.

## Type checks inside patterns

`str(name)`, `int(n)`, `float(x)` check the type; they don't convert. `float(x)` rejects an `int`, so
allow both explicitly.

```python
def as_number(value: object) -> float | None:
    match value:
        case bool():                       # bool is an int subclass: exclude it first
            return None
        case int(n) | float(n):
            return float(n)
        case _:
            return None

assert as_number(3) == 3.0 and as_number(2.5) == 2.5 and as_number(True) is None
```

## Mapping and class patterns

- Mapping patterns match if the listed keys are present; extra keys are ignored. `**rest` captures the
  remainder.
- Class patterns with positional sub-patterns use `__match_args__`. Dataclasses generate it from the
  non-keyword-only fields (`match_args=True` by default).

```python
from dataclasses import dataclass

@dataclass
class Point:
    x: int
    y: int

def locate(p: Point) -> str:
    match p:
        case Point(0, 0):
            return "origin"
        case Point(x, 0):
            return f"on x axis at {x}"
        case Point(x=x, y=y):
            return f"at {x},{y}"
    raise AssertionError("unreachable")

def route(event: dict[str, object]) -> str:
    match event:
        case {"type": "click", "pos": [x, y], **rest}:
            return f"click {x},{y} +{len(rest)}"
        case {"type": str(kind)}:
            return kind
        case _:
            return "invalid"

assert locate(Point(3, 0)) == "on x axis at 3"
assert route({"type": "click", "pos": [1, 2], "id": 7}) == "click 1,2 +1"
assert route({"type": "scroll"}) == "scroll"
```

## Sources

- https://docs.python.org/3.13/reference/compound_stmts.html#the-match-statement
- https://peps.python.org/pep-0634/ · https://peps.python.org/pep-0636/
- https://docs.python.org/3.13/library/dataclasses.html (`match_args`)
