# Errors, resources and object lifetime

Contents: EAFP · catching · raising and chaining · custom exceptions · notes · exception groups ·
resources · object lifetime · sources

## EAFP over LBYL

Try the operation and handle the failure rather than checking first. In multi-threaded code a check
can race with the use (another thread changes the state in between), and it duplicates the lookup.

```python
config = {"port": "8080"}

# avoid
port = int(config["port"]) if "port" in config else 80
# prefer
try:
    port = int(config["port"])
except KeyError:
    port = 80
assert port == 8080
```

For a plain default, `config.get("port", "80")` is simpler still. EAFP is for real operations
(`open`, `int(...)`, attribute access on duck-typed objects).

## Catching

- Catch the narrowest exception type, and keep the `try` body to the line that can fail.
- Never bare `except:`. `except Exception:` only at a top-level boundary (request handler, worker loop),
  and log it there.
- Use `else:` for code that runs only when nothing failed; `finally:` for cleanup.
- `contextlib.suppress(FileNotFoundError)` for an intentionally ignored error.

## Raising and chaining

- Translating an error: `raise NewError(...) from exc` keeps the original as `__cause__` in the
  traceback.
- `from None` hides the original when it is pure noise for the caller.
- A bare `raise` inside `except` re-raises with the original traceback.

```python
class ConfigError(Exception):
    pass

def read_port(raw: dict[str, str]) -> int:
    try:
        return int(raw["port"])
    except (KeyError, ValueError) as exc:
        raise ConfigError("invalid or missing 'port'") from exc

try:
    read_port({"port": "abc"})
except ConfigError as err:
    assert isinstance(err.__cause__, ValueError)
```

## Custom exceptions

Subclass `Exception` (never `BaseException`). Give a library one base class so callers can catch all of
its errors, with specific subclasses beneath it.

```python
class StorageError(Exception): ...
class NotFound(StorageError): ...
class QuotaExceeded(StorageError): ...
```

## Notes (3.11+)

`add_note()` attaches context without wrapping the exception. Notes print after the message.

```python
def load(path: str) -> None:
    try:
        raise ValueError("bad header")
    except ValueError as exc:
        exc.add_note(f"while loading {path}")
        raise

try:
    load("data.csv")
except ValueError as exc:
    assert exc.__notes__ == ["while loading data.csv"]
```

## Exception groups and `except*` (3.11+)

Several independent failures (concurrent tasks, batch validation) are raised together in an
`ExceptionGroup`. `except*` handles each type in the group. Unmatched exceptions keep propagating in a
new group.

```python
def validate(row: dict[str, str]) -> None:
    errors: list[Exception] = []
    if "id" not in row:
        errors.append(KeyError("id"))
    if not row.get("name"):
        errors.append(ValueError("empty name"))
    if errors:
        raise ExceptionGroup("invalid row", errors)

seen: list[str] = []
try:
    validate({"name": ""})
except* KeyError as group:
    seen.append(f"{len(group.exceptions)} missing")
except* ValueError as group:
    seen.append(f"{len(group.exceptions)} bad value")
assert seen == ["1 missing", "1 bad value"]
```

Rules: a `try` uses either `except` or `except*`, not both. `break`, `continue` and `return` are not
allowed inside `except*`.

## Resources

- Release everything with `with`: files, locks, sockets, DB connections, temporary directories.
- Group several managers in one parenthesized `with (...)` (3.10+).
- Write your own with `contextlib.contextmanager`. Put the cleanup in `finally` so it runs on errors.
- `contextlib.ExitStack` when the number of resources is known only at runtime.

```python
import contextlib
import tempfile
from collections.abc import Iterator
from pathlib import Path

@contextlib.contextmanager
def scratch_file(name: str) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, name)
        try:
            yield path
        finally:
            path.unlink(missing_ok=True)

with (
    scratch_file("a.txt") as a,
    scratch_file("b.txt") as b,
):
    a.write_text("x"); b.write_text("y")
    assert a.read_text() + b.read_text() == "xy"
```

## Object lifetime

- Don't use `__del__` for cleanup. It is not guaranteed to run for objects still alive at exit, it can
  run at any moment from any thread, and reference cycles delay it until the cyclic collector runs.
- To run cleanup when an object dies, use `weakref.finalize(obj, func, *args)`. `func` and its args
  must not reference `obj`, so never pass a bound method of `obj`.
- Caches that must not keep objects alive: `weakref.WeakValueDictionary` / `WeakKeyDictionary`. Plain
  `list` and `dict` instances can't be weakly referenced (subclasses can); `int` and `tuple` can't even
  when subclassed. Classes with `__slots__` need a `"__weakref__"` slot.

```python
import shutil
import tempfile
import weakref
from pathlib import Path

class Workspace:
    def __init__(self) -> None:
        self.path = Path(tempfile.mkdtemp())
        self._cleanup = weakref.finalize(self, shutil.rmtree, self.path)

    def close(self) -> None:
        self._cleanup()                 # idempotent; also runs at exit if never called

ws = Workspace(); p = ws.path
ws.close()
assert not p.exists()
```

## Sources

- https://docs.python.org/3.13/library/exceptions.html
- https://docs.python.org/3.13/reference/compound_stmts.html (`try`, `except*`, `with`)
- https://docs.python.org/3.13/library/contextlib.html
- https://docs.python.org/3.13/library/weakref.html
- https://peps.python.org/pep-0654/ · https://peps.python.org/pep-0678/
- https://docs.python.org/3/whatsnew/3.10.html (parenthesized context managers) ·
  https://docs.python.org/3/whatsnew/3.11.html
- https://docs.python.org/3.13/reference/datamodel.html (`__del__`)
- https://peps.python.org/pep-0008/ (programming recommendations)
- https://docs.python.org/3.13/glossary.html (EAFP, LBYL)
