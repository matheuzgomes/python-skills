import re
import time
from pathlib import Path

import pytest

from check_skills import (
    Block,
    Config,
    Result,
    SkillDefaults,
    SpecError,
    Status,
    check_blocks,
    exit_code,
    extract_blocks,
    interpreter_version,
    load_config,
    main,
    report,
    run_block,
    skill_problems,
)

SKILL = Path("skills/demo/SKILL.md")


def blocks_of(markdown: str, defaults: SkillDefaults = SkillDefaults()) -> list[Block]:
    return extract_blocks(markdown, SKILL, defaults)


def only_block(code: str) -> Block:
    [block] = blocks_of(f"```python\n{code}\n```\n")
    return block


# Unit A: extract and run blocks, report and exit code


def test_extracts_each_python_block_with_the_line_of_its_fence():
    markdown = "# Title\n\n```python\nx = 1\n```\n\n```bash\necho no\n```\n\n```python\ny = 2\n```\n"

    blocks = blocks_of(markdown)

    assert [(b.line, b.code) for b in blocks] == [(3, "x = 1\n"), (11, "y = 2\n")]
    assert blocks[0].where == "skills/demo/SKILL.md:3"


def test_counts_lines_from_the_very_start_of_the_file():
    [block] = blocks_of("\n\n```python\nx = 1\n```\n")

    assert block.line == 3


def test_dedents_a_block_indented_inside_a_list_item():
    markdown = "- item\n\n    ```python\n    if True:\n        x = 1\n    ```\n"

    [block] = blocks_of(markdown)

    assert block.code == "if True:\n    x = 1\n"


def test_a_block_that_raises_fails_with_its_location_version_and_error():
    result = run_block(only_block('raise ValueError("boom")'), "3.13", timeout=60)

    assert result == Result("skills/demo/SKILL.md:1", "3.13", Status.FAIL, "ValueError: boom")


def test_a_block_that_runs_cleanly_is_ok():
    result = run_block(only_block("assert sum([1, 2]) == 3"), "3.13", timeout=60)

    assert result.status is Status.OK


def test_a_deprecation_warning_fails_the_block():
    code = 'import warnings\nwarnings.warn("old api", DeprecationWarning)'

    result = run_block(only_block(code), "3.13", timeout=60)

    assert (result.status, result.message) == (Status.FAIL, "DeprecationWarning: old api")


def test_a_block_over_the_timeout_fails_without_waiting_for_it():
    started = time.monotonic()

    result = run_block(only_block("import time\ntime.sleep(30)"), "3.13", timeout=2)

    assert (result.status, result.message) == (Status.FAIL, "timeout after 2 s")
    assert time.monotonic() - started < 10


def test_an_exit_without_traceback_reports_the_exit_code():
    result = run_block(only_block("import os\nos._exit(3)"), "3.13", timeout=60)

    assert (result.status, result.message) == (Status.FAIL, "exit code 3")


def test_an_exit_without_a_report_shows_the_last_line_of_stderr():
    code = "import os, sys\nsys.stderr.write('first\\nmiddle\\nlast\\n')\nsys.stderr.flush()\nos._exit(4)"

    result = run_block(only_block(code), "3.13", timeout=60)

    assert (result.status, result.message) == (Status.FAIL, "last")


def test_a_zero_exit_without_a_report_is_clean():
    assert run_block(only_block("import os\nos._exit(0)"), "3.13", timeout=60).status is Status.OK


def test_sys_exit_with_a_code_fails_as_system_exit():
    result = run_block(only_block("import sys\nsys.exit(3)"), "3.13", timeout=60)

    assert (result.status, result.message) == (Status.FAIL, "SystemExit: 3")


def test_sys_exit_with_zero_ends_the_block_cleanly():
    assert run_block(only_block("import sys\nsys.exit(0)"), "3.13", timeout=60).status is Status.OK


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("import os\nf = open(os.devnull)\ndel f", "in a finalizer: ResourceWarning: unclosed file"),
        ("async def g():\n    pass\ng()", "in a finalizer: RuntimeWarning: coroutine 'g' was never awaited"),
        (
            "import threading\nt = threading.Thread(target=lambda: 1 / 0)\nt.start()\nt.join()",
            "in a thread: ZeroDivisionError: division by zero",
        ),
        (
            "import asyncio\n"
            "async def boom():\n    raise ValueError('x')\n"
            "async def main():\n    asyncio.get_running_loop().create_task(boom())\n    await asyncio.sleep(0.01)\n"
            "asyncio.run(main())",
            "in asyncio: Task exception was never retrieved (ValueError: x)",
        ),
        (
            "import threading, time\ndef work():\n    time.sleep(0.2)\n    1 / 0\nthreading.Thread(target=work).start()",
            "in a thread: ZeroDivisionError: division by zero",
        ),
        ("import atexit\natexit.register(lambda: 1 / 0)", "in an atexit callback: ZeroDivisionError: division by zero"),
        (
            "import tempfile\nd = tempfile.TemporaryDirectory()",
            "in an atexit callback: ResourceWarning: Implicitly cleaning up",
        ),
        (
            "import weakref\nclass Resource:\n    pass\nkept = Resource()\nweakref.finalize(kept, lambda: 1 / 0)",
            "in an atexit callback: ZeroDivisionError: division by zero",
        ),
    ],
    ids=[
        "finalizer warning",
        "coroutine never awaited",
        "thread",
        "asyncio task",
        "thread left running",
        "atexit",
        "temporary directory left open",
        "weakref.finalize on a live object",
    ],
)
def test_an_error_python_only_prints_still_fails_the_block(code, message):
    result = run_block(only_block(code), "3.13", timeout=60)

    assert result.status is Status.FAIL
    assert result.message.startswith(message)


@pytest.mark.parametrize(
    "code",
    [
        "import logging\nlog = logging.getLogger('demo')\n"
        "class Resource:\n    def __del__(self):\n        log.info('closing')\n"
        "kept = Resource()",
        "import weakref\nclosed = []\ndef cleanup(name):\n    closed.append(name)\n"
        "class Resource:\n    def __init__(self):\n        weakref.finalize(self, cleanup, 'r')\n"
        "kept = Resource()",
        "import threading, time\nresults = []\ndef work():\n    time.sleep(0.2)\n    results.append(1)\n"
        "threading.Thread(target=work).start()",
        "from concurrent.futures import ThreadPoolExecutor\npool = ThreadPoolExecutor()\n"
        "assert pool.submit(sum, [1, 2]).result() == 3",
        "import atexit\nseen = []\natexit.register(lambda: seen.append(1))",
    ],
    ids=["finalizer using a global", "weakref.finalize using a global", "thread left running", "pool never shut down", "atexit"],
)
def test_code_that_runs_after_the_last_line_still_sees_the_globals_of_the_block(code):
    result = run_block(only_block(code), "3.13", timeout=20)

    assert (result.status, result.message) == (Status.OK, "")


def test_a_block_that_replaces_sys_stderr_still_gets_its_report():
    block = marked("raises=ValueError", "import io, sys\nsys.stderr = io.StringIO()\nraise ValueError('hidden')")

    assert run_block(block, "3.13", timeout=60).status is Status.OK


def test_a_block_sees_none_of_the_runner_names():
    block = marked("raises=NameError", "json.dumps(1)")

    assert run_block(block, "3.13", timeout=60).status is Status.OK


def test_a_class_defined_in_a_block_can_be_pickled():
    code = "import pickle\nclass Point:\n    pass\nassert type(pickle.loads(pickle.dumps(Point()))) is Point"

    assert run_block(only_block(code), "3.13", timeout=60).status is Status.OK


def test_input_gets_end_of_file_instead_of_waiting():
    assert run_block(marked("raises=EOFError", "input()"), "3.13", timeout=10).status is Status.OK


def test_each_block_runs_in_a_fresh_empty_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    writer = only_block('import pathlib\npathlib.Path("out.txt").write_text("x")')
    reader = only_block("import os\nassert os.listdir() == []")

    assert run_block(writer, "3.13", timeout=60).status is Status.OK
    assert run_block(reader, "3.13", timeout=60).status is Status.OK
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("python", ["3.13", "3.14"])
def test_a_block_cannot_import_the_packages_of_the_dev_environment(python):
    block = marked("raises=ModuleNotFoundError", "import pytest")

    assert run_block(block, python, timeout=60).status is Status.OK


def test_report_lists_problems_and_a_summary_per_version():
    results = [
        Result("skills/demo/SKILL.md:3", "3.13.15", Status.OK),
        Result("skills/demo/SKILL.md:9", "3.13.15", Status.FAIL, "ValueError: boom"),
        Result("skills/demo/SKILL.md:3", "3.14.6", Status.OK),
        Result("skills/demo/SKILL.md:9", "3.14.6", Status.OK),
    ]

    assert report(results) == [
        "FAIL skills/demo/SKILL.md:9 [3.13.15] ValueError: boom",
        "3.13.15: 1 ok, 1 fail",
        "3.14.6: 2 ok",
    ]


def test_exit_code_is_1_when_anything_fails_and_0_otherwise():
    ok = Result("a.md:1", "3.13.15", Status.OK)
    failed = Result("a.md:2", "3.13.15", Status.FAIL, "ValueError: boom")

    assert exit_code([ok]) == 0
    assert exit_code([ok, failed]) == 1


# Unit B: markers and dependencies


def marked(marker: str, code: str) -> Block:
    [block] = blocks_of(f"<!-- test: {marker} -->\n```python\n{code}\n```\n")
    return block


def test_raises_passes_when_the_named_exception_is_raised():
    block = marked("raises=TypeError", '1 + "a"')

    assert run_block(block, "3.13", timeout=60).status is Status.OK


def test_raises_fails_when_the_block_runs_cleanly():
    result = run_block(marked("raises=TypeError", "x = 1"), "3.13", timeout=60)

    assert (result.status, result.message) == (Status.FAIL, "expected TypeError, but the block ran cleanly")


def test_raises_fails_on_a_different_exception():
    result = run_block(marked("raises=TypeError", 'raise ValueError("x")'), "3.13", timeout=60)

    assert (result.status, result.message) == (Status.FAIL, "expected TypeError, got ValueError: x")


def test_raises_matches_the_last_part_of_a_dotted_exception_name():
    block = marked("raises=JSONDecodeError", 'import json\njson.loads("{")')

    assert run_block(block, "3.13", timeout=60).status is Status.OK


@pytest.mark.parametrize(
    ("marker", "code"),
    [
        ("raises=ExceptionGroup", 'raise ExceptionGroup("group", [ValueError("a")])'),
        ("raises=TypeError", 'error = TypeError("bad")\nerror.add_note("while loading")\nraise error'),
        ("raises=SystemExit", "raise SystemExit(2)"),
    ],
    ids=["exception group", "exception with a note", "system exit"],
)
def test_raises_reads_the_type_of_the_exception_not_the_traceback_text(marker, code):
    assert run_block(marked(marker, code), "3.13", timeout=60).status is Status.OK


def test_python_marker_sets_the_minimum_version():
    block = marked("python>=3.14", "pass")

    assert block.min_python == (3, 14)
    assert not block.runs_on((3, 13))
    assert block.runs_on((3, 14))
    assert block.runs_on((3, 15))


def test_python_marker_is_skipped_on_older_versions_and_runs_on_newer():
    block = marked("python>=3.14", "import sys\nassert sys.version_info >= (3, 14)")

    results = check_blocks([block], Config(pythons=("3.13", "3.14")))

    assert [(r.python[:4], r.status) for r in results] == [("3.13", Status.SKIP), ("3.14", Status.OK)]


def test_deps_marker_installs_the_dependencies_first():
    block = marked("deps=pydantic<2", 'import pydantic\nassert pydantic.VERSION.startswith("1.")')

    assert run_block(block, "3.13", timeout=120).status is Status.OK


def test_a_dependency_uv_cannot_read_fails_with_the_uv_error():
    result = run_block(marked("deps=pydantic<<2", "pass"), "3.13", timeout=60)

    assert result.status is Status.FAIL
    assert result.message.startswith("error: ")


def test_marker_deps_add_to_the_skill_defaults():
    defaults = SkillDefaults(min_python=(3, 13), deps=("fastapi",))
    markdown = "<!-- test: deps=httpx2 sqlalchemy -->\n```python\npass\n```\n"

    [block] = blocks_of(markdown, defaults)

    assert (block.min_python, block.deps) == ((3, 13), ("fastapi", "httpx2", "sqlalchemy"))


def test_items_combine_with_semicolons():
    block = marked("python>=3.14; raises=TypeError", '1 + "a"')

    assert (block.min_python, block.raises) == ((3, 14), "TypeError")


def test_a_marker_applies_only_to_the_block_right_after_it():
    markdown = "<!-- test: raises=TypeError -->\n\nSome prose.\n\n```python\nx = 1\n```\n"

    [block] = blocks_of(markdown)

    assert block.raises is None


def test_skip_with_a_reason_is_listed_once_and_never_run():
    block = marked("skip=needs network", 'raise SystemExit("must not run")')

    results = check_blocks([block], Config(pythons=("3.13", "3.14")))

    assert results == [Result("skills/demo/SKILL.md:2", None, Status.SKIP, "needs network")]
    assert report(results) == ["SKIP skills/demo/SKILL.md:2 needs network"]


def test_skip_without_a_reason_fails_once():
    results = check_blocks([marked("skip", "pass")], Config(pythons=("3.13", "3.14")))

    assert results == [
        Result("skills/demo/SKILL.md:2", None, Status.FAIL, "skip needs a reason, as in skip=needs network")
    ]
    assert exit_code(results) == 1


def test_an_unknown_marker_item_is_an_error():
    assert marked("pyhton>=3.14", "pass").error == "unknown marker item 'pyhton>=3.14'"


def test_a_python_marker_needs_major_and_minor():
    assert marked("python>=3", "pass").error == "expected a version like 3.14, got '3'"


def test_an_empty_marker_value_is_an_error():
    assert marked("raises=", "pass").error == "raises needs a value"


# Unit C: version matrix, preview versions and the command line

VALID_SKILL = "---\nname: demo\ndescription: A demo skill for the tests.\n---\n\n# Demo\n\n"
PYPROJECT = '[tool.check-skills]\npython = ["3.13"]\ntimeout = 60\n'


def make_repo(root: Path, files: dict[str, str], pyproject: str = PYPROJECT) -> Path:
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_results_carry_the_full_version_of_the_interpreter_that_ran_them():
    [result] = check_blocks([only_block("pass")], Config(pythons=("3.13",)))

    assert re.fullmatch(r"3\.13\.\d+", result.python)


def test_the_reported_version_is_the_one_that_ran_the_block():
    reported = interpreter_version("3.14")
    block = only_block(f"import platform\nassert platform.python_version() == {reported!r}")

    assert run_block(block, "3.14", timeout=60).status is Status.OK


def test_a_failure_on_a_preview_version_is_a_warning_and_keeps_exit_code_0():
    results = check_blocks([only_block('raise ValueError("boom")')], Config(pythons=(), preview=("3.13",)))

    [result] = results
    assert result.status is Status.WARN
    assert re.fullmatch(r"3\.13\.\d+ \(preview\)", result.python)
    assert exit_code(results) == 0


def test_an_unavailable_version_fails_once_for_all_blocks():
    results = check_blocks([only_block("pass"), only_block("pass")], Config(pythons=("3.99",)))

    assert results == [Result("python 3.99", None, Status.FAIL, "interpreter not available")]


def test_an_unavailable_preview_version_is_a_warning():
    results = check_blocks([only_block("pass")], Config(pythons=(), preview=("3.99",)))

    assert results == [Result("python 3.99", None, Status.WARN, "interpreter not available")]


def test_load_config_reads_versions_timeout_and_skill_defaults(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.check-skills]\n"
        'python = ["3.13", "3.14"]\n'
        'preview = ["3.15"]\n'
        "timeout = 30\n"
        "[tool.check-skills.skills.demo]\n"
        'requires-python = ">=3.13"\n'
        'deps = ["pydantic<2"]\n',
        encoding="utf-8",
    )

    config = load_config(pyproject)

    assert config == Config(
        pythons=("3.13", "3.14"),
        preview=("3.15",),
        timeout=30,
        skills={"demo": SkillDefaults(min_python=(3, 13), deps=("pydantic<2",))},
    )
    assert config.defaults_for("demo").deps == ("pydantic<2",)
    assert config.defaults_for("other") == SkillDefaults()


def test_a_skill_without_requires_python_runs_on_every_version(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.check-skills]\npython = ["3.13"]\n[tool.check-skills.skills.demo]\ndeps = ["httpx2"]\n',
        encoding="utf-8",
    )

    assert load_config(pyproject).defaults_for("demo") == SkillDefaults(min_python=None, deps=("httpx2",))


def test_load_config_accepts_only_a_lower_bound_for_requires_python(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.check-skills]\npython = ["3.13"]\n[tool.check-skills.skills.demo]\nrequires-python = "==3.13"\n',
        encoding="utf-8",
    )

    with pytest.raises(SpecError, match="requires-python must look like >=3.13, got '==3.13'"):
        load_config(pyproject)


def test_load_config_rejects_a_version_without_minor(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[tool.check-skills]\npython = ["3"]\n', encoding="utf-8")

    with pytest.raises(SpecError, match="expected a version like 3.14, got '3'"):
        load_config(pyproject)


def test_main_returns_0_and_prints_a_summary_when_every_block_passes(tmp_path, capsys):
    root = make_repo(tmp_path, {"skills/demo/SKILL.md": VALID_SKILL + "```python\nassert 1 + 1 == 2\n```\n"})

    assert main(["--root", str(root)]) == 0
    assert re.fullmatch(r"3\.13\.\d+: 1 ok\n", capsys.readouterr().out)


def test_main_returns_1_and_lists_a_failing_block_of_a_reference(tmp_path, capsys):
    root = make_repo(
        tmp_path,
        {
            "skills/demo/SKILL.md": VALID_SKILL,
            "skills/demo/references/extra.md": '```python\nraise ValueError("boom")\n```\n',
        },
    )

    assert main(["--root", str(root)]) == 1
    first_line = capsys.readouterr().out.splitlines()[0]
    assert re.fullmatch(r"FAIL skills/demo/references/extra\.md:1 \[3\.13\.\d+\] ValueError: boom", first_line)


def test_main_applies_the_skill_defaults_from_the_config(tmp_path, capsys):
    pyproject = PYPROJECT + '[tool.check-skills.skills.demo]\nrequires-python = ">=3.14"\n'
    root = make_repo(tmp_path, {"skills/demo/SKILL.md": VALID_SKILL + "```python\npass\n```\n"}, pyproject)

    assert main(["--root", str(root)]) == 0
    assert re.fullmatch(r"3\.13\.\d+: 1 skip\n", capsys.readouterr().out)


def test_main_fails_when_there_are_no_skills(tmp_path, capsys):
    root = make_repo(tmp_path, {})

    assert main(["--root", str(root)]) == 1
    assert capsys.readouterr().out == f"FAIL {root / 'skills'} no skills found\n"


# Unit D: structure of each skill


def make_skill(root: Path, skill_md: str, folder: str = "demo", references: tuple[str, ...] = ()) -> Path:
    skill_dir = root / "skills" / folder
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    for name in references:
        (skill_dir / "references" / name).write_text("# Reference\n", encoding="utf-8")
    return skill_dir


def test_a_valid_skill_with_working_links_has_no_problems(tmp_path):
    skill_md = VALID_SKILL + "Read [the guide](references/guide.md) and [its part](references/guide.md#part).\n"

    assert skill_problems(make_skill(tmp_path, skill_md, references=("guide.md",))) == []


def test_the_name_must_match_the_folder(tmp_path):
    skill_dir = make_skill(tmp_path, VALID_SKILL, folder="other")

    assert skill_problems(skill_dir) == ["Directory name 'other' must match skill name 'demo'"]


def test_a_description_over_1024_characters_is_a_problem(tmp_path):
    skill_md = f"---\nname: demo\ndescription: {'x' * 1025}\n---\n"

    assert skill_problems(make_skill(tmp_path, skill_md)) == ["Description exceeds 1024 character limit (1025 chars)"]


def test_a_broken_relative_link_is_reported_with_the_link(tmp_path):
    skill_md = VALID_SKILL + "See [missing](references/missing.md).\n"

    assert skill_problems(make_skill(tmp_path, skill_md)) == ["broken link: references/missing.md"]


def test_links_in_code_external_links_and_anchors_are_not_checked(tmp_path):
    skill_md = (
        VALID_SKILL
        + "Use `def first[T](xs: Sequence[T])` here.\n\n"
        + "```markdown\n[example](references/not-here.md)\n```\n\n"
        + "See [docs](https://docs.python.org/3/), [above](#demo) and [mail](mailto:a@b.c).\n"
        + "Load [the script](//cdn.example.com/lib.js).\n"
    )

    assert skill_problems(make_skill(tmp_path, skill_md)) == []


def test_a_link_that_leaves_the_skill_folder_is_reported(tmp_path):
    (tmp_path / "README.md").write_text("# Repo\n", encoding="utf-8")
    skill_md = VALID_SKILL + "See [the readme](../../README.md).\n"

    assert skill_problems(make_skill(tmp_path, skill_md)) == ["link leaves the skill: ../../README.md"]


def test_a_broken_reference_style_link_is_reported(tmp_path):
    skill_md = VALID_SKILL + "See [the guide].\n\n[the guide]: references/missing.md\n"

    assert skill_problems(make_skill(tmp_path, skill_md)) == ["broken link: references/missing.md"]


def test_a_footnote_is_not_a_link(tmp_path):
    skill_md = VALID_SKILL + "A claim.[^1]\n\n[^1]: Some text from PEP 8.\n"

    assert skill_problems(make_skill(tmp_path, skill_md)) == []


def test_a_link_in_angle_brackets_may_contain_spaces(tmp_path):
    skill_md = VALID_SKILL + "See [it](<references/the guide.md>) and [that].\n\n[that]: <references/no guide.md>\n"

    problems = skill_problems(make_skill(tmp_path, skill_md, references=("the guide.md",)))

    assert problems == ["broken link: references/no guide.md"]


def test_main_lists_structure_problems_and_fails(tmp_path, capsys):
    root = make_repo(tmp_path, {"skills/demo/SKILL.md": VALID_SKILL + "See [missing](references/missing.md).\n"})

    assert main(["--root", str(root)]) == 1
    assert capsys.readouterr().out == "FAIL skills/demo/SKILL.md broken link: references/missing.md\n"
