# Concurrency: asyncio, threads, processes

## Which model

| Workload | Use |
|---|---|
| Many concurrent I/O waits (HTTP, DB, sockets) in code that is already async | `asyncio` |
| Blocking I/O in sync code, or a blocking library called from async | threads: `ThreadPoolExecutor`, `asyncio.to_thread` |
| CPU-bound pure Python | processes: `ProcessPoolExecutor`, `multiprocessing` |
| CPU-bound numeric work | a library that releases the GIL (NumPy and similar), then threads |

The free-threaded build of 3.13 (`python3.13t`, PEP 703) is **experimental**. It runs single-threaded
code noticeably slower, and importing an extension not marked compatible can turn the GIL back on. Don't
design production code around it; do write thread-safe code with explicit locks either way.

## Structured concurrency with TaskGroup (3.11+)

Start related tasks inside `async with asyncio.TaskGroup()`. When the block exits, every task has
finished. If one fails, the others are cancelled and the failures are raised together in an
`ExceptionGroup`.

```python
import asyncio

async def fetch(n: int) -> int:
    await asyncio.sleep(0.01)
    return n * 2

async def main() -> list[int]:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(fetch(n)) for n in range(3)]
    return [t.result() for t in tasks]

assert asyncio.run(main()) == [0, 2, 4]
```

```python
import asyncio

async def boom() -> None:
    raise ValueError("bad")

async def slow() -> None:
    await asyncio.sleep(10)            # cancelled when boom() fails

async def main() -> str:
    outcome = "ok"
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(boom())
            tg.create_task(slow())
    except* ValueError as group:
        outcome = f"{len(group.exceptions)} failed"   # no `return` allowed inside except*
    return outcome

assert asyncio.run(main()) == "1 failed"
```

**Why not `gather`.** With `gather`, the first exception propagates but the other awaitables keep
running. Use `gather(..., return_exceptions=True)` only when you really want results and errors mixed in
one list.

## Timeouts (3.11+)

```python
import asyncio

async def main() -> str:
    try:
        async with asyncio.timeout(0.05):
            await asyncio.sleep(1)
    except TimeoutError:               # catch it outside the timeout block
        return "timed out"
    return "done"

assert asyncio.run(main()) == "timed out"
```

Use `asyncio.timeout_at(when)` for an absolute deadline shared by several steps.

## Rules for async code

- One entry point: `asyncio.run(main())`.
- Never call blocking functions (`time.sleep`, `requests`, blocking file or DB drivers) inside a
  coroutine. Use the async library, or `await asyncio.to_thread(blocking_fn, *args)`.
- A task created with bare `asyncio.create_task` is held only by a weak reference in the event loop.
  Keep a reference until it finishes, or better, create it in a `TaskGroup`.
- Don't swallow `asyncio.CancelledError`. If you catch it for cleanup, re-raise it.
- Bound concurrency with `asyncio.Semaphore` rather than starting thousands of tasks at once.

```python
import asyncio
import time

def blocking_read() -> str:
    time.sleep(0.01)
    return "data"

async def main() -> str:
    return await asyncio.to_thread(blocking_read)    # event loop stays free

assert asyncio.run(main()) == "data"
```

## Threads and processes

- Prefer `concurrent.futures` executors over raw `threading.Thread`/`multiprocessing.Process`. Use them
  as context managers so workers are joined.
- Shared mutable state between threads needs a `threading.Lock`. Don't rely on the GIL making
  operations atomic.
- `queue.Queue` passes work between threads.
- Functions and values sent to a `ProcessPoolExecutor` must be picklable: define the functions at
  module level (no lambdas), and start the pool under `if __name__ == "__main__":`.

```python
from concurrent.futures import ThreadPoolExecutor

def square(n: int) -> int:
    return n * n

with ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(square, range(5)))
assert results == [0, 1, 4, 9, 16]
```

## Sources

- https://docs.python.org/3.13/library/asyncio-task.html
- https://docs.python.org/3.13/library/concurrent.futures.html
- https://docs.python.org/3.13/library/threading.html
- https://docs.python.org/3.13/howto/free-threading-python.html
- https://docs.python.org/3/whatsnew/3.11.html (TaskGroup, timeout) ·
  https://docs.python.org/3/whatsnew/3.13.html (free-threaded build)
- https://peps.python.org/pep-0703/
- https://docs.python.org/3.13/library/asyncio-exceptions.html (`CancelledError`)
