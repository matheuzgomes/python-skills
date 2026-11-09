"""Check the skills in this repository.

Every ```python block in skills/ runs in a fresh uv-managed interpreter, once per version listed
in [tool.check-skills] of pyproject.toml, with warnings as errors. An error that Python only
prints, in a finalizer, a thread, an atexit callback or asyncio, also fails the block (see
block_runner.py). A comment right before a block changes how it runs; items combine with ";":

    <!-- test: python>=3.14 -->            run only on 3.14 and later
    <!-- test: deps=pydantic<2 httpx2 -->  install these first, on top of the skill's deps
    <!-- test: raises=TypeError -->        pass only if the block raises TypeError
    <!-- test: skip=needs network -->      do not run; the reason is required

Each skill must also pass the Agent Skills validator, and the relative links in its SKILL.md
must lead to files that exist.
"""

import argparse
import contextlib
import copy
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import textwrap
import tomllib
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote, urlsplit

from block_runner import REPORT_PREFIX, Report
from skills_ref import validate as validate_skill

type Version = tuple[int, int]

FENCE = re.compile(
    r"^(?P<indent>[ \t]*)```python[ \t]*\n(?P<code>.*?)^(?P=indent)```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
MARKER = re.compile(r"<!--\s*test:(?P<items>.*?)-->")
PYTHON_ITEM = re.compile(r"python\s*>=\s*(?P<version>\S+)")
ANY_FENCE = re.compile(r"^[ \t]*```.*?^[ \t]*```[ \t]*$", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")
# A target in <angle brackets> may contain spaces. A footnote, [^1]: text, is not a link.
LINK = re.compile(r"\[[^\]]*\]\((?P<target><[^>\n]*>|[^)\s]+)[^)]*\)")
REFERENCE_LINK = re.compile(r"^[ \t]*\[(?!\^)[^\]]+\]:[ \t]*(?P<target><[^>\n]*>|\S+)", re.MULTILINE)
RUNNER = Path(__file__).with_name("block_runner.py")
# uv runs inside the environment these point to, even with --no-project.
ACTIVE_ENVIRONMENT_VARIABLES = frozenset({"VIRTUAL_ENV", "CONDA_PREFIX"})


class SpecError(ValueError):
    """A marker or a config value that cannot be read."""


class Status(StrEnum):
    OK = "ok"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class SkillDefaults:
    min_python: Version | None = None
    deps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Block:
    path: Path
    line: int
    code: str
    min_python: Version | None = None
    deps: tuple[str, ...] = ()
    raises: str | None = None
    skip: str | None = None
    error: str | None = None

    @property
    def where(self) -> str:
        return f"{self.path}:{self.line}"

    def runs_on(self, version: Version) -> bool:
        return self.min_python is None or version >= self.min_python


@dataclass(frozen=True, slots=True)
class Config:
    pythons: tuple[str, ...]
    preview: tuple[str, ...] = ()
    timeout: float = 60
    skills: Mapping[str, SkillDefaults] = field(default_factory=dict)

    def defaults_for(self, skill: str) -> SkillDefaults:
        return self.skills.get(skill, SkillDefaults())


@dataclass(frozen=True, slots=True)
class Result:
    location: str
    python: str | None
    status: Status
    message: str = ""


@dataclass(frozen=True, slots=True)
class Outcome:
    returncode: int | None  # None when the command hit the timeout
    stdout: str
    stderr: str


def parse_version(text: str) -> Version:
    match = re.fullmatch(r"(\d+)\.(\d+)", text)
    if match is None:
        raise SpecError(f"expected a version like 3.14, got {text!r}")
    return int(match[1]), int(match[2])


def load_config(pyproject: Path) -> Config:
    """Read [tool.check-skills] from a pyproject.toml."""
    table = tomllib.loads(pyproject.read_text(encoding="utf-8"))["tool"]["check-skills"]
    pythons = tuple(table["python"])
    preview = tuple(table.get("preview", ()))
    for python in (*pythons, *preview):
        parse_version(python)
    skills = {
        name: SkillDefaults(
            min_python=_parse_requires(raw.get("requires-python")),
            deps=tuple(raw.get("deps", ())),
        )
        for name, raw in table.get("skills", {}).items()
    }
    return Config(pythons, preview, table.get("timeout", 60), skills)


def _parse_requires(spec: str | None) -> Version | None:
    if spec is None:
        return None
    if not spec.startswith(">="):
        raise SpecError(f"requires-python must look like >=3.13, got {spec!r}")
    return parse_version(spec.removeprefix(">=").strip())


def extract_blocks(markdown: str, path: Path, defaults: SkillDefaults) -> list[Block]:
    """Every ```python block of a markdown text, with the marker right before it applied."""
    blocks = []
    for match in FENCE.finditer(markdown):
        block = Block(
            path=path,
            line=markdown.count("\n", 0, match.start()) + 1,
            code=textwrap.dedent(match["code"]),
            min_python=defaults.min_python,
            deps=defaults.deps,
        )
        if (items := _marker_before(markdown, match.start())) is not None:
            block = _apply_marker(block, items)
        blocks.append(block)
    return blocks


def _marker_before(markdown: str, fence_start: int) -> str | None:
    """The items of a marker on the last non-blank line before a fence, if there is one."""
    previous = markdown[:fence_start].rstrip().rpartition("\n")[2].strip()
    match = MARKER.fullmatch(previous)
    return match["items"] if match else None


def _apply_marker(block: Block, items: str) -> Block:
    try:
        return copy.replace(block, **_parse_items(items, block.deps))
    except SpecError as exc:
        return copy.replace(block, error=str(exc))


def _parse_items(items: str, default_deps: tuple[str, ...]) -> dict[str, object]:
    changes: dict[str, object] = {}
    for item in filter(None, (part.strip() for part in items.split(";"))):
        if match := PYTHON_ITEM.fullmatch(item):
            changes["min_python"] = parse_version(match["version"])
            continue
        key, _, value = (part.strip() for part in item.partition("="))
        if key not in ("deps", "raises", "skip"):
            raise SpecError(f"unknown marker item {item!r}")
        if not value:
            if key == "skip":
                raise SpecError("skip needs a reason, as in skip=needs network")
            raise SpecError(f"{key} needs a value")
        changes[key] = (*default_deps, *value.split()) if key == "deps" else value
    return changes


def check_blocks(blocks: Iterable[Block], config: Config) -> list[Result]:
    """Run every block on every Python version it supports."""
    blocks = list(blocks)
    results = [Result(b.where, None, Status.FAIL, b.error) for b in blocks if b.error]
    results += [Result(b.where, None, Status.SKIP, b.skip) for b in blocks if b.skip and not b.error]
    runnable = [b for b in blocks if not (b.error or b.skip)]
    if not runnable:
        return results
    for python in config.pythons:
        results += _run_on(python, runnable, config.timeout, preview=False)
    for python in config.preview:
        results += _run_on(python, runnable, config.timeout, preview=True)
    return results


def _run_on(python: str, blocks: Sequence[Block], timeout: float, *, preview: bool) -> list[Result]:
    """Run blocks on one version; on a preview version a failure is only a warning."""
    failed = Status.WARN if preview else Status.FAIL
    found = interpreter_version(python)
    if found is None:
        return [Result(f"python {python}", None, failed, "interpreter not available")]
    label = f"{found} (preview)" if preview else found
    version = parse_version(python)
    results = []
    for block in blocks:
        if not block.runs_on(version):
            results.append(Result(block.where, label, Status.SKIP, "needs a newer Python"))
            continue
        result = run_block(block, python, timeout)
        status = failed if result.status is Status.FAIL else result.status
        results.append(copy.replace(result, python=label, status=status))
    return results


def interpreter_version(python: str) -> str | None:
    """The full version uv runs for a request like 3.14, or None when uv cannot find one."""
    command = _uv_python(python, (), "-c", "import platform; print(platform.python_version())")
    outcome = _run_in_scratch(command, timeout=300)  # long enough for uv to download it
    return outcome.stdout.strip() if outcome.returncode == 0 else None


def run_block(block: Block, python: str, timeout: float) -> Result:
    """Run a block in a fresh interpreter and empty directory, with warnings as errors."""
    command = _uv_python(python, block.deps, "-W", "error", str(RUNNER))
    outcome = _run_in_scratch(command, timeout, stdin=block.code)
    if outcome.returncode is None:
        return Result(block.where, python, Status.FAIL, f"timeout after {timeout:g} s")
    report = _runner_report(outcome.stderr)
    if report is None:  # uv failed, or the block ended the interpreter before the runner could report
        if outcome.returncode != 0:
            return Result(block.where, python, Status.FAIL, _error_line(outcome))
        report = Report(raised=None, message=None, problems=[])
    return Result(block.where, python, *_verdict(block, report))


def _runner_report(stderr: str) -> Report | None:
    for line in reversed(stderr.splitlines()):
        if line.startswith(REPORT_PREFIX):
            return json.loads(line.removeprefix(REPORT_PREFIX))
    return None


def _verdict(block: Block, report: Report) -> tuple[Status, str]:
    if report["problems"]:
        return Status.FAIL, "; ".join(report["problems"])
    raised, message = report["raised"], report["message"]
    if block.raises is None:
        return (Status.OK, "") if raised is None else (Status.FAIL, str(message))
    if raised is None:
        return Status.FAIL, f"expected {block.raises}, but the block ran cleanly"
    if _names_exception(raised, block.raises):
        return Status.OK, ""
    return Status.FAIL, f"expected {block.raises}, got {message}"


def _uv_python(python: str, deps: Iterable[str], *args: str) -> list[str]:
    """A uv command for a uv-managed interpreter, so neither the repo's nor the active
    virtual environment leaks its packages into a block."""
    with_deps = [arg for dep in deps for arg in ("--with", dep)]
    uv = ["uv", "run", "--no-project", "--managed-python", "--quiet", "--python", python]
    return [*uv, *with_deps, "--", "python", "-I", *args]


def _run_in_scratch(command: list[str], timeout: float, stdin: str = "") -> Outcome:
    """Run a command in a new empty directory, outside any active virtual environment."""
    env = {k: v for k, v in os.environ.items() if k not in ACTIVE_ENVIRONMENT_VARIABLES}
    with tempfile.TemporaryDirectory() as workdir:
        # A session of its own lets a timeout kill uv and the interpreter it started.
        with subprocess.Popen(  # noqa: S603 - fixed uv command, no shell; the code is this repo's
            command,
            cwd=workdir,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        ) as process:
            try:
                stdout, stderr = process.communicate(stdin, timeout=timeout)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):  # it may finish meanwhile
                    os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
                return Outcome(None, "", "")
    return Outcome(process.returncode, stdout, stderr)


def _error_line(outcome: Outcome) -> str:
    """The line that explains a failure without a report: uv's own error, or the last line."""
    lines = outcome.stderr.strip().splitlines()
    uv_errors = [line for line in lines if line.startswith("error:")]
    if uv_errors:
        return uv_errors[0]
    return lines[-1] if lines else f"exit code {outcome.returncode}"


def _names_exception(qualified: str, name: str) -> bool:
    """Whether a qualified type, as in json.decoder.JSONDecodeError, is the one named."""
    return qualified == name or qualified.endswith(f".{name}")


def report(results: Iterable[Result]) -> list[str]:
    """One line per problem, then one summary line per Python version."""
    results = list(results)
    lines = [_problem_line(r) for r in results if _is_listed(r)]
    counts: dict[str, Counter[Status]] = {}
    for result in results:
        if result.python is not None:
            counts.setdefault(result.python, Counter())[result.status] += 1
    for python, by_status in counts.items():
        summary = ", ".join(f"{n} {status}" for status in Status if (n := by_status[status]))
        lines.append(f"{python}: {summary}")
    return lines


def _is_listed(result: Result) -> bool:
    """Problems, and skips asked for by a marker; a block too new for a version is not listed."""
    if result.status is Status.SKIP:
        return result.python is None
    return result.status is not Status.OK


def _problem_line(result: Result) -> str:
    version = f" [{result.python}]" if result.python is not None else ""
    return f"{result.status.upper()} {result.location}{version} {result.message}"


def exit_code(results: Iterable[Result]) -> int:
    return 1 if any(r.status is Status.FAIL for r in results) else 0


def skill_problems(skill_dir: Path) -> list[str]:
    """What the Agent Skills validator finds, plus the bad relative links in SKILL.md."""
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    return [*validate_skill(skill_dir), *link_problems(skill_md, skill_dir)]


def link_problems(markdown: str, skill_dir: Path) -> list[str]:
    """Relative links that lead nowhere or outside the skill, which is installed on its own.
    Links inside code are not links."""
    prose = INLINE_CODE.sub("", ANY_FENCE.sub("", markdown))
    matches = [m for pattern in (LINK, REFERENCE_LINK) for m in pattern.finditer(prose)]
    targets = [m["target"].removeprefix("<").removesuffix(">") for m in matches]
    return [problem for target in targets if (problem := _link_problem(target, skill_dir))]


def _link_problem(target: str, skill_dir: Path) -> str | None:
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not parts.path:  # a URL, an email or an anchor
        return None
    path = (skill_dir / unquote(parts.path)).resolve()
    if not path.is_relative_to(skill_dir.resolve()):
        return f"link leaves the skill: {target}"
    if not path.exists():
        return f"broken link: {target}"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root, with pyproject.toml and skills/ (default: this repository)",
    )
    root = parser.parse_args(argv).root
    config = load_config(root / "pyproject.toml")
    skill_files = sorted(root.glob("skills/*/SKILL.md"))
    if not skill_files:
        results = [Result(str(root / "skills"), None, Status.FAIL, "no skills found")]
    else:
        results = [
            Result(str(skill_md.relative_to(root)), None, Status.FAIL, problem)
            for skill_md in skill_files
            for problem in skill_problems(skill_md.parent)
        ]
        results += check_blocks(_all_blocks(root, skill_files, config), config)
    print("\n".join(report(results)))
    return exit_code(results)


def _all_blocks(root: Path, skill_files: Iterable[Path], config: Config) -> Iterator[Block]:
    for skill_md in skill_files:
        defaults = config.defaults_for(skill_md.parent.name)
        for markdown in sorted(skill_md.parent.rglob("*.md")):
            text = markdown.read_text(encoding="utf-8")
            yield from extract_blocks(text, markdown.relative_to(root), defaults)


if __name__ == "__main__":
    sys.exit(main())
