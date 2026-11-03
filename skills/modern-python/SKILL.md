---
name: modern-python
description: Idiomatic, modern Python for 3.13+ - choosing collections, comprehensions and generators, decorators, typing with PEP 695 generics, dataclasses, pattern matching, exceptions and asyncio, with the legacy idioms each one replaces. Use when writing, reviewing or refactoring Python code, choosing a data structure, writing decorators, type hints, dataclasses, match statements or async code.
---

# Modern Python (3.13+)

Write Python the way 3.13 allows, not the way older tutorials taught. Most mistakes come from
habits that predate 3.10–3.13, so the rules below focus on decisions and version changes, not basics.

**Target version.** These rules assume `requires-python >= 3.13`. If the project declares an older
minimum (`pyproject.toml`, `setup.cfg`, CI matrix), follow the project and skip features it can't use.

## Always-on rules

1. **Unions and optionals:** `int | None`, `str | bytes`. Never `Optional[...]` or `Union[...]`.
2. **Generic containers:** `list[int]`, `dict[str, int]`, and abstract types from `collections.abc`
   (`Iterable`, `Sequence`, `Mapping`, `Callable`). Never `typing.List`, `typing.Dict`, `typing.Callable`.
3. **Generics:** `def first[T](xs: Sequence[T]) -> T`, `class Box[T]:`, `type Pair[T] = tuple[T, T]`.
   No module-level `TypeVar`, `Generic[T]` or `TypeAlias` in new code.
4. **Mutable defaults:** never `def f(items=[])`. Use `None` and build inside, or
   `field(default_factory=list)` in a dataclass.
5. **Decorators:** every wrapper uses `@functools.wraps(func)` and is typed with ParamSpec:
   `def deco[**P, R](func: Callable[P, R]) -> Callable[P, R]`.
6. **Records:** `@dataclass(frozen=True, slots=True)` for value objects; `copy.replace(obj, x=1)` for a
   modified copy.
7. **Identity:** `is` only for `None`, sentinels, enum members and `type(x) is T`. Use `==` for values. Test
   emptiness with `if not seq:` and never compare to `True`/`False`.
8. **Membership:** for repeated `in` checks on a large collection, build a `set` or `frozenset` once.
   Queues are `deque`, never `list.pop(0)`.
9. **Errors:** catch the narrowest exception, chain with `raise NewError(...) from exc`, and release
   resources with `with`, never `__del__`.
10. **Async:** run concurrent tasks inside `async with asyncio.TaskGroup()` and bound them with
    `async with asyncio.timeout(s)`. Avoid bare `create_task` and `gather` for structured work.

## Read the matching reference before writing that kind of code

Each file is short and self-contained. Read only the ones the task needs.

| When you are about to... | Read |
|---|---|
| pick a container, dedupe, count, group, keep data sorted, use dict or set operations | [references/collections.md](references/collections.md) |
| write a comprehension, generator, `:=`, or replace `map`/`filter`/`reduce` | [references/comprehensions.md](references/comprehensions.md) |
| design function parameters, write a closure, a decorator, or memoize | [references/functions-and-decorators.md](references/functions-and-decorators.md) |
| annotate types: generics, aliases, Protocol, TypedDict, narrowing, overrides | [references/typing.md](references/typing.md) |
| model data with dataclass, NamedTuple or Enum; define hashing or equality | [references/modeling.md](references/modeling.md) |
| write a `match` statement | [references/pattern-matching.md](references/pattern-matching.md) |
| raise, catch or group exceptions; manage resources or object lifetime | [references/errors-and-resources.md](references/errors-and-resources.md) |
| write asyncio, threads or processes | [references/concurrency.md](references/concurrency.md) |
| compare with `is`, copy objects, slice sequences, use sentinels | [references/identity-and-copying.md](references/identity-and-copying.md) |

## When reviewing code

Flag legacy idioms using the substitution tables at the top of `typing.md` and `modeling.md`. Suggest
the modern form only when the project's minimum Python version supports it. Don't rewrite working code
that is out of scope for the task.
