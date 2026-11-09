# python-skills

Agent skills for writing idiomatic, modern Python.

## `modern-python`

Python 3.13+ best practices for coding agents. The skill focuses on decisions and version changes
rather than basics that LLMs already know:

- choosing between list, tuple, set, frozenset, dict, deque, array, Counter and bisect
- comprehensions vs generator expressions, the walrus operator, `itertools.batched`
- parameters, closures, typed decorators with ParamSpec, caching
- typing: `X | None`, PEP 695 generics and `type` aliases, `TypeIs`, `@override`, `ReadOnly`, `@deprecated`
- dataclasses (`frozen`, `slots`, `kw_only`), NamedTuple, StrEnum, `copy.replace`
- structural pattern matching
- exceptions: chaining, notes, `ExceptionGroup` / `except*`, context managers, `weakref.finalize`
- asyncio `TaskGroup` and `timeout`, threads vs processes, the experimental free-threaded build

`SKILL.md` stays short and loads only when the agent works on Python. Detailed rules live in
`references/` and are read one file at a time, only when the task needs them. Every reference file
lists the official documentation and PEPs it is based on, and every code example runs on Python 3.13.

## Install

Requires Node.js 22.20 or later.

```sh
npx skills add matheuzgomes/python-skills -g -a claude-code
```

`-g` installs globally (available in every project). Drop `-a claude-code` to pick other agents
interactively.

## Update

```sh
npx skills check        # list installed skills that have updates
npx skills update -g    # update global skills
```

## Remove

```sh
npx skills remove modern-python -g
```

## Layout

```
skills/modern-python/
  SKILL.md          always-on rules and an index of when to read each reference
  references/       collections, comprehensions, functions-and-decorators, typing, modeling,
                    pattern-matching, errors-and-resources, concurrency, identity-and-copying
```

## Development

`tools/check_skills.py` runs every Python code block of every skill in a fresh, uv-managed
interpreter, once per version listed in `[tool.check-skills]` of `pyproject.toml`, with warnings
turned into errors. An error that Python only prints, in a finalizer, a thread, an atexit callback
or asyncio, also fails the block. It also validates each skill with
[skills-ref](https://github.com/agentskills/agentskills/tree/main/skills-ref) and checks that the
relative links in `SKILL.md` lead to files that exist inside the skill. Requires [uv](https://docs.astral.sh/uv/)
and runs on Linux and macOS.

```sh
uv run tools/check_skills.py   # check the skills
uv run pytest                  # test the checker
```

A comment right before a code block changes how that block runs. Items combine with `;`.

| Comment | Effect |
|---|---|
| `<!-- test: python>=3.14 -->` | Run only on Python 3.14 and later. |
| `<!-- test: deps=pydantic<2 httpx2 -->` | Install these first, space-separated, on top of the skill's `deps`. |
| `<!-- test: raises=TypeError -->` | Pass only if the block raises `TypeError`. |
| `<!-- test: skip=needs network -->` | Don't run the block. The reason is required. |

A skill can set defaults for all its blocks under `[tool.check-skills.skills.<name>]`, with
`requires-python = ">=3.13"` and `deps = [...]`. A failure on a `preview` version is only a
warning.

A block runs as `__main__` but not from a file, so a process pool started with spawn or forkserver
(the default on Linux from Python 3.14) cannot find the functions the block defines. Mark such a
block with `skip=`.

CI runs both commands on every push and every Monday, against the newest releases of
Python and of each library, so a deprecation shows up before it becomes an error.

## License

MIT
