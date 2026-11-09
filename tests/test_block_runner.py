import atexit
import io
import json
import sys
import threading

import pytest

from block_runner import REPORT_PREFIX, Report, main, run

CLEAN = Report(raised=None, message=None, problems=[])


def test_a_clean_block_reports_nothing():
    assert run("x = 1 + 1") == CLEAN


def test_the_raised_exception_is_reported_by_qualified_type_and_one_line():
    assert run('raise ValueError("boom")') == Report(
        raised="builtins.ValueError", message="ValueError: boom", problems=[]
    )


def test_an_exception_without_a_message_is_reported_by_its_name():
    assert run("raise KeyError")["message"] == "KeyError"


def test_exit_with_zero_or_none_is_clean_and_any_other_code_is_raised():
    assert run("import sys\nsys.exit(0)") == CLEAN
    assert run("import sys\nsys.exit()") == CLEAN
    assert run("import sys\nsys.exit(3)") == Report(
        raised="builtins.SystemExit", message="SystemExit: 3", problems=[]
    )


def test_an_error_in_a_finalizer_is_a_problem():
    code = "class Leaky:\n    def __del__(self):\n        raise ValueError('in del')\nLeaky()"

    assert run(code)["problems"] == ["in a finalizer: ValueError: in del"]


def test_an_object_left_in_the_namespace_is_finalized_before_the_report():
    code = "class Leaky:\n    def __del__(self):\n        raise ValueError('at the end')\nkept = Leaky()"

    assert run(code)["problems"] == ["in a finalizer: ValueError: at the end"]


def test_a_finalizer_can_still_use_an_older_global_of_the_block():
    code = (
        "import logging\nlog = logging.getLogger('demo')\n"
        "class Resource:\n    def __del__(self):\n        log.info('closing')\n"
        "kept = Resource()"
    )

    assert run(code) == CLEAN


def test_a_cycle_the_block_dropped_is_finalized_while_its_globals_still_exist():
    code = (
        "log = []\n"
        "class Node:\n    def __init__(self):\n        self.me = self\n"
        "    def __del__(self):\n        log.append('gone')\n"
        "Node()"
    )

    assert run(code) == CLEAN


def test_the_names_of_the_module_itself_are_kept_for_the_finalizers():
    code = "class Resource:\n    def __del__(self):\n        assert __name__ == '__main__'\nkept = Resource()"

    assert run(code) == CLEAN


@pytest.mark.parametrize("name", ["__hidden", "__cache__"])
def test_a_name_the_block_defines_is_released_even_if_it_looks_like_a_module_name(name):
    code = f"class Leaky:\n    def __del__(self):\n        raise ValueError('released')\n{name} = Leaky()"

    assert run(code)["problems"] == ["in a finalizer: ValueError: released"]


def test_an_error_in_a_thread_is_a_problem():
    code = "import threading\nt = threading.Thread(target=lambda: 1 / 0)\nt.start()\nt.join()"

    assert run(code)["problems"] == ["in a thread: ZeroDivisionError: division by zero"]


def test_an_asyncio_error_is_a_problem_with_its_first_line_and_exception():
    code = (
        "import asyncio\n"
        "async def boom():\n    raise ValueError('x')\n"
        "async def main():\n    asyncio.get_running_loop().create_task(boom())\n    await asyncio.sleep(0.01)\n"
        "asyncio.run(main())"
    )

    assert run(code)["problems"] == ["in asyncio: Task exception was never retrieved (ValueError: x)"]


def test_an_asyncio_error_without_an_exception_keeps_only_its_first_line():
    code = "import logging\nlogging.getLogger('asyncio').error('loop broke\\nmore detail')"

    assert run(code)["problems"] == ["in asyncio: loop broke"]


def test_an_asyncio_error_logged_outside_an_exception_has_no_exception_part():
    code = "import logging\nlogging.getLogger('asyncio').error('no exception here', exc_info=True)"

    assert run(code)["problems"] == ["in asyncio: no exception here"]


def test_the_block_runs_in_a_fresh_main_module_without_the_runner_names():
    assert run("assert __name__ == '__main__'\nassert 'run' not in globals()") == CLEAN


def test_classes_of_the_block_can_be_pickled():
    code = "import pickle\nclass Point:\n    pass\nassert type(pickle.loads(pickle.dumps(Point()))) is Point"

    assert run(code) == CLEAN


def test_the_hooks_and_main_module_are_restored_afterwards():
    hooks = sys.unraisablehook, threading.excepthook, sys.modules["__main__"]

    run("raise ValueError('boom')")

    assert (sys.unraisablehook, threading.excepthook, sys.modules["__main__"]) == hooks


@pytest.fixture
def exit_steps(monkeypatch):
    """Stand-ins for the exit steps main() takes, which inside pytest would stop pytest's own
    threads and atexit callbacks. Each step records whether the block's globals still exist."""
    steps: list[tuple[str, bool]] = []

    def step(name):
        return lambda: steps.append((name, "kept" in sys.modules["__main__"].__dict__))

    monkeypatch.setattr(threading, "_shutdown", step("wait for threads"))
    monkeypatch.setattr(atexit, "_run_exitfuncs", step("atexit callbacks"))
    return steps


def test_run_alone_leaves_the_exit_steps_to_the_caller(exit_steps):
    run("kept = 1")

    assert exit_steps == []


def test_main_reads_the_block_from_stdin_and_writes_one_report_line(monkeypatch, capfd, exit_steps):
    monkeypatch.setattr(sys, "stdin", io.StringIO('raise ValueError("boom")'))

    assert main() == 1
    stderr = capfd.readouterr().err
    assert stderr.startswith(REPORT_PREFIX)
    assert json.loads(stderr.removeprefix(REPORT_PREFIX)) == run('raise ValueError("boom")')


def test_main_returns_0_for_a_clean_block_and_1_for_a_problem(monkeypatch, capfd, exit_steps):
    monkeypatch.setattr(sys, "stdin", io.StringIO("x = 1"))
    assert main() == 0

    monkeypatch.setattr(sys, "stdin", io.StringIO("class L:\n    def __del__(self):\n        1 / 0\nL()"))
    assert main() == 1
    capfd.readouterr()


def test_main_waits_for_threads_then_runs_atexit_callbacks_while_the_globals_exist(monkeypatch, capfd, exit_steps):
    monkeypatch.setattr(sys, "stdin", io.StringIO("kept = 1"))

    main()

    assert exit_steps == [("wait for threads", True), ("atexit callbacks", True)]
    capfd.readouterr()


def test_main_labels_an_error_raised_while_the_atexit_callbacks_run(monkeypatch, capfd, exit_steps):
    def failing_callback():
        class Leaky:
            def __del__(self):
                raise ValueError("at exit")

        Leaky()

    monkeypatch.setattr(atexit, "_run_exitfuncs", failing_callback)
    monkeypatch.setattr(sys, "stdin", io.StringIO("x = 1"))

    main()

    report = json.loads(capfd.readouterr().err.removeprefix(REPORT_PREFIX))
    assert report["problems"] == ["in an atexit callback: ValueError: at exit"]


def test_main_records_an_error_an_atexit_callback_hands_to_sys_excepthook(monkeypatch, capfd, exit_steps):
    def callback_reporting_like_weakref_finalize():
        try:
            raise ValueError("at exit")
        except ValueError:
            sys.excepthook(*sys.exc_info())

    monkeypatch.setattr(atexit, "_run_exitfuncs", callback_reporting_like_weakref_finalize)
    monkeypatch.setattr(sys, "stdin", io.StringIO("x = 1"))

    main()

    report = json.loads(capfd.readouterr().err.removeprefix(REPORT_PREFIX))
    assert report["problems"] == ["in an atexit callback: ValueError: at exit"]


def test_main_writes_the_report_to_the_real_stderr_even_if_the_block_replaced_it(monkeypatch, capfd, exit_steps):
    monkeypatch.setattr(sys, "stdin", io.StringIO("import io, sys\nsys.stderr = io.StringIO()"))
    monkeypatch.setattr(sys, "stderr", sys.stderr)  # restore it after the test

    main()

    assert capfd.readouterr().err.startswith(REPORT_PREFIX)
