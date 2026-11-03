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

## License

MIT
