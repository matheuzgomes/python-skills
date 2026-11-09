# Reviewing Python code

Contents: order · correctness · security · performance · maintainability and typing · tests ·
writing findings · sources

Review a change in this order: run the tools, then read for what they can't see. Each row below
names the rule or check that catches the problem; "read" means no tool does, so look for it
yourself. Rule codes are ruff's, stable unless marked preview.

## Order

1. Run the project's own linter, type checker and tests. Where it has none for an area, run ruff
   on the changed files with `--select S,B,ASYNC,DTZ,UP,G` and `--target-version` set to the
   project's minimum Python, and run the tests with warnings as errors.
2. Read the diff against the plan or the issue: every promised behavior is there, and nothing else.
3. Go through the tables below for what the tools missed.

## Correctness

| Look for | Caught by |
|---|---|
| a mutable default argument | B006 |
| a bare `except:` | E722 |
| `except Exception: pass`, or any broad catch that hides errors | BLE001, S110 |
| a `raise` inside `except` without `from` | B904 |
| a closure in a loop that captures the loop variable | B023 |
| `is` with a literal, `== None` | F632, E711 |
| `assert (condition, "message")`, which is always true | F631 |
| `zip` of iterables that must match in length, without `strict=True` | B905 |
| a task created and dropped, which can be collected mid-run | RUF006 |
| a coroutine called without `await` | pyright (`reportUnusedCoroutine`); the `RuntimeWarning` under `-W error` |
| naive datetimes | DTZ005, DTZ003, DTZ004, DTZ011 and the other DTZ rules |
| text I/O without `encoding=` | PLW1514 (preview); `-X warn_default_encoding` |
| floats for money, a rounding mode left to the default | read (`production-pitfalls.md`) |
| empty input, zero, one, the maximum, an off-by-one | read; a test for each boundary |

## Security

Details and safe versions are in `security.md`.

| Look for | Caught by |
|---|---|
| a command run through a shell with outside input | S602, S605 |
| SQL text built from values | S608 |
| `pickle`, `marshal`, `yaml.load`, `eval` or `exec` on outside data | S301, S302, S506, S307, S102 |
| `random` for tokens, ids or reset links | S311 |
| a secret compared with `==` | read |
| MD5 or SHA-1 for anything secret | S324 |
| a fast hash such as SHA-256 for passwords | read |
| a user path joined to a base without the resolve check | read |
| `tarfile.extractall` without `filter=` | S202 |
| XML from outside parsed with the standard library | S314 |
| a URL from a user fetched without a host allowlist (SSRF) | read |
| `requests` without `timeout=`, `verify=False` | S113, S501 |
| a route or action without an authorization check | read; a test for each role that must be refused |
| a secret in the source | S105, S106, S107 |
| a secret in a log line or an error message | read |
| `assert` used for validation or permissions | S101 |
| `tempfile.mktemp`, a fixed path under `/tmp` | S306, S108 |

## Performance

| Look for | Caught by |
|---|---|
| `x in a_list` inside a loop | read (`collections.md`) |
| one query per item (N+1) | read; a test that counts the queries |
| a blocking call inside `async def` | ASYNC210, ASYNC221, ASYNC230, ASYNC251 |
| `lru_cache` or `cache` on a method | B019 |
| a loop that only appends | PERF401 |
| `s += piece` in a loop | read |
| everything read into memory where streaming works | read (`performance.md`) |
| a cache with no size limit or expiry | read |

## Maintainability and typing

| Look for | Caught by |
|---|---|
| `Optional`, `List` and other `typing` names with a builtin form | UP045, UP006, UP035 |
| `TypeVar`, `Generic` or `TypeAlias` where the project is on 3.12+ | UP047, UP046, UP040 (needs the target version) |
| public functions without annotations | ANN001, ANN201; the type checker |
| `Any` or `# type: ignore` hiding a real type error | the type checker in strict mode; read |
| a function too complex to follow | C901, PLR0911, PLR0912 |
| `print` left in library code | T201 |
| an f-string in a logging call | G004 |
| duplicated logic, a name that doesn't say what it holds | read |
| a changed behavior or API that the docs and changelog don't mention | read |
| a raised minimum version or an upgraded library that nobody asked for | read |

## Tests

| Look for | Caught by |
|---|---|
| a behavior of the plan without a test that uses its numbers | read the plan next to the tests |
| a test that only checks that a mock was called | read (`testing.md`) |
| changed lines that no test runs | coverage of the diff, as with diff-cover |
| assertions that wouldn't notice the code changing | mutation testing |
| a test that depends on the clock, the run order or the network | read |

## Writing findings

Report only problems that change behavior, security or cost, each with:

- the place, as `path:line`;
- a concrete failure: the input or state, and what goes wrong;
- how severe it is, and the fix.

Leave out style that a formatter or linter would fix, and preferences that the project's code
doesn't already follow.

## Sources

- https://docs.astral.sh/ruff/rules/ (the codes above, checked against ruff 0.17)
- https://microsoft.github.io/pyright/#/configuration (`reportUnusedCoroutine`)
- https://github.com/Bachmann1234/diff_cover · https://mutmut.readthedocs.io/
- `security.md`, `testing.md`, `performance.md`, `production-pitfalls.md` in this skill
