"""Run one code block from stdin and report how it ended, for check_skills.py.

Python prints an error raised in a finalizer, a thread, an atexit callback or an asyncio callback
and carries on, so a block can exit with 0 after one. This runner records those errors and the
exception the block raised, then writes one JSON line to stderr, after REPORT_PREFIX.

Every Python in [tool.check-skills] runs this file, so it must work on the oldest of them.
"""

import atexit
import contextlib
import gc
import json
import logging
import sys
import threading
import types
from collections.abc import Iterator
from typing import TypedDict

REPORT_PREFIX = "@@check-skills "
MODULE_NAMES = frozenset(vars(types.ModuleType("__main__"))) | {"__builtins__"}  # exec adds __builtins__


class Report(TypedDict):
    raised: str | None  # qualified type, as in "json.decoder.JSONDecodeError"
    message: str | None
    problems: list[str]


def run(code: str, *, exiting: bool = False) -> Report:
    """Run code as a fresh __main__ module and describe how it ended. With exiting, first do what
    the interpreter does on exit, which only a process that is about to end may do."""
    problems: list[str] = []
    raised = message = None
    with (
        _recording_unraisable(problems, "in a finalizer"),
        _recording_thread_errors(problems),
        _recording_asyncio_errors(problems),
        _fresh_main() as module,
    ):
        try:
            exec(compile(code, "<block>", "exec"), module.__dict__)  # noqa: S102 - this repo's own example
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raised, message = _qualified_name(type(exc)), _describe(type(exc), exc)
        except BaseException as exc:  # any exception is the block's result, even KeyboardInterrupt
            raised, message = _qualified_name(type(exc)), _describe(type(exc), exc)
        if exiting:
            _exit_steps(problems)
        _release(module.__dict__)
    return Report(raised=raised, message=message, problems=problems)


def _exit_steps(problems: list[str]) -> None:
    """Wait for the block's threads, then run its atexit callbacks, as the interpreter does on
    exit, but while the hooks still listen. Later the interpreter finds nothing left to do.
    Daemon threads are not waited for, as on any exit."""
    threading._shutdown()  # noqa: SLF001 - the call the interpreter makes on exit
    where = "in an atexit callback"
    # weakref.finalize runs the finalizers of live objects here and reports through sys.excepthook.
    with _recording_unraisable(problems, where), _recording_excepthook(problems, where):
        atexit._run_exitfuncs()  # noqa: SLF001 - the same


def _release(namespace: dict[str, object]) -> None:
    """Finalize what the block left behind while the hooks still listen. Its names go newest
    first and the module's own names stay, so a finalizer can still use an older global."""
    gc.collect()  # first the cycles the block already dropped
    for name in reversed(list(namespace)):
        if name not in MODULE_NAMES:
            del namespace[name]
    gc.collect()


def _recording_unraisable(problems: list[str], where: str) -> contextlib.AbstractContextManager[None]:
    """Record the errors Python reports through sys.unraisablehook, as in a finalizer."""

    def hook(args: "sys.UnraisableHookArgs") -> None:  # the type exists at runtime only on 3.14+
        problems.append(f"{where}: {_describe(args.exc_type, args.exc_value)}")

    return _replaced(sys, "unraisablehook", hook)


def _recording_excepthook(problems: list[str], where: str) -> contextlib.AbstractContextManager[None]:
    def hook(exc_type: type[BaseException], exc: BaseException, _: types.TracebackType | None) -> None:
        problems.append(f"{where}: {_describe(exc_type, exc)}")

    return _replaced(sys, "excepthook", hook)


def _recording_thread_errors(problems: list[str]) -> contextlib.AbstractContextManager[None]:
    def hook(args: threading.ExceptHookArgs) -> None:
        problems.append(f"in a thread: {_describe(args.exc_type, args.exc_value)}")

    return _replaced(threading, "excepthook", hook)


@contextlib.contextmanager
def _replaced(owner: types.ModuleType, name: str, hook: object) -> Iterator[None]:
    previous = getattr(owner, name)
    setattr(owner, name, hook)
    try:
        yield
    finally:
        setattr(owner, name, previous)


@contextlib.contextmanager
def _recording_asyncio_errors(problems: list[str]) -> Iterator[None]:
    logger, handler = logging.getLogger("asyncio"), _AsyncioErrors(problems)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)


class _AsyncioErrors(logging.Handler):
    def __init__(self, problems: list[str]) -> None:
        super().__init__(logging.ERROR)
        self.problems = problems

    def emit(self, record: logging.LogRecord) -> None:
        text = f"in asyncio: {record.getMessage().splitlines()[0]}"
        exc_type, exc, _ = record.exc_info or (None, None, None)
        if exc_type is not None:
            text += f" ({_describe(exc_type, exc)})"
        self.problems.append(text)


@contextlib.contextmanager
def _fresh_main() -> Iterator[types.ModuleType]:
    """A new, empty __main__: the block sees none of the runner's names, and pickle still
    finds the classes the block defines."""
    previous = sys.modules["__main__"]
    module = sys.modules["__main__"] = types.ModuleType("__main__")
    try:
        yield module
    finally:
        sys.modules["__main__"] = previous


def _qualified_name(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _describe(exc_type: type[BaseException], exc: BaseException | None) -> str:
    text = str(exc) if exc is not None else ""
    return f"{exc_type.__name__}: {text}" if text else exc_type.__name__


def main() -> int:
    report = run(sys.stdin.read(), exiting=True)
    print(REPORT_PREFIX + json.dumps(report), file=sys.__stderr__)  # the block may have replaced sys.stderr
    return 1 if report["raised"] or report["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
