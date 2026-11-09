# Testing with pytest

Contents: what to test · parametrize · exceptions and warnings · fixtures · fakes over mocks ·
time and randomness · async tests · properties · configuration · coverage and mutation · sources

## What to test

- Test behavior through the public interface: what a caller sends and gets back, or what changes
  in the world. A test of a private helper breaks on every refactor and proves nothing new.
- One behavior per test, named as a sentence that states it:
  `test_a_coupon_over_100_percent_is_rejected`, not `test_coupon_2`.
- Arrange, act, assert, in that order. Use plain `assert`: pytest rewrites it to show both sides.
- When a plan lists behaviors with numbers ("10% off 200.00 is 180.00"), each one becomes a test or
  a parametrize row with those numbers.

## Parametrize

Give each row an id that says what it covers, so a failure names the case.

<!-- test: pytest -->
```python
from decimal import Decimal

import pytest

def apply_discount(total: Decimal, percent: Decimal) -> Decimal:
    if not 0 < percent <= 100:
        raise ValueError(f"percent must be in (0, 100], got {percent}")
    return total * (100 - percent) / 100

@pytest.mark.parametrize(
    ("total", "percent", "expected"),
    [
        pytest.param(Decimal("200.00"), Decimal("10"), Decimal("180.00"), id="10% off"),
        pytest.param(Decimal("99.90"), Decimal("100"), Decimal("0"), id="100% makes it free"),
    ],
)
def test_apply_discount(total: Decimal, percent: Decimal, expected: Decimal) -> None:
    assert apply_discount(total, percent) == expected

@pytest.mark.parametrize("percent", [Decimal("0"), Decimal("-5"), Decimal("100.01")])
def test_a_percent_outside_0_to_100_is_rejected(percent: Decimal) -> None:
    with pytest.raises(ValueError, match=r"percent must be in \(0, 100\]"):
        apply_discount(Decimal("10"), percent)
```

## Exceptions and warnings

- `pytest.raises(Type, match=...)` checks the type and searches the message with `re.search`, so
  escape special characters, or pass `re.escape(text)`. Use `as excinfo` to check attributes.
- Keep only the line that should raise inside the `with`; anything after it never runs.
- `pytest.RaisesGroup(ValueError, TypeError)` checks an `ExceptionGroup` and what it holds.
- `pytest.warns(DeprecationWarning, match=...)` checks a warning the same way.

<!-- test: pytest -->
```python
import warnings

import pytest

def test_a_batch_reports_every_failure() -> None:
    with pytest.RaisesGroup(ValueError, TypeError):
        raise ExceptionGroup("batch", [ValueError("row 1"), TypeError("row 2")])

def test_the_old_name_still_works_but_warns() -> None:
    with pytest.warns(DeprecationWarning, match="use new_name"):
        warnings.warn("old_name is deprecated; use new_name", DeprecationWarning, stacklevel=1)
```

## Fixtures

- A fixture builds what a test needs; the test asks for it by parameter name. Code after `yield`
  is the teardown and runs even when the test fails.
- Built-in fixtures cover the usual needs: `tmp_path` (a new directory as a `Path`), `monkeypatch`
  (environment variables and attributes, undone after the test), `capsys` and `caplog` (output
  and log records).
- Keep the default function scope. A wider scope shares state between tests, so use it only for
  something slow and read-only. Put shared fixtures in `conftest.py`.

<!-- test: pytest -->
```python
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

@pytest.fixture
def db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE notes (body TEXT)")
    yield conn
    conn.close()

def test_a_note_is_stored(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO notes VALUES (?)", ("hi",))
    assert db.execute("SELECT body FROM notes").fetchall() == [("hi",)]

def test_the_export_goes_to_the_configured_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    (Path(os.environ["EXPORT_DIR"]) / "out.csv").write_text("a,b\n", encoding="utf-8")
    assert (tmp_path / "out.csv").read_text(encoding="utf-8") == "a,b\n"
```

## Fakes over mocks

Pass dependencies in (a parameter or a `Protocol`), and give the test a small working fake that
records what happened. The test then checks the result, not the calls, and survives refactoring.
Reach for `unittest.mock` only where you can't inject. Then use `create_autospec(Real,
instance=True)` or `patch(..., autospec=True)`, so a call with the wrong arguments fails.

## Time and randomness

Make the clock and the random source parameters (`now: Callable[[], datetime]`,
`rng: random.Random`) instead of patching `datetime` or `random`. A test then picks the exact
moment or seed it needs.

<!-- test: pytest -->
```python
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

class Mailer(Protocol):
    def send(self, to: str, subject: str) -> None: ...

@dataclass
class FakeMailer:
    sent: list[tuple[str, str]] = field(default_factory=list)

    def send(self, to: str, subject: str) -> None:
        self.sent.append((to, subject))

def remind_overdue(due_dates: dict[str, datetime], mailer: Mailer, now: Callable[[], datetime]) -> None:
    for email, due in due_dates.items():
        if due < now():
            mailer.send(email, "Your invoice is overdue")

def test_only_overdue_invoices_get_a_reminder() -> None:
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)
    mailer = FakeMailer()
    due_dates = {"late@example.com": now - timedelta(days=1), "early@example.com": now + timedelta(days=1)}

    remind_overdue(due_dates, mailer, now=lambda: now)

    assert mailer.sent == [("late@example.com", "Your invoice is overdue")]
```

## Async tests

pytest doesn't run `async def` tests by itself: it fails them with "async def functions are not
natively supported". Use the plugin the project already has: pytest-asyncio
(`@pytest.mark.asyncio`, or `asyncio_mode = "auto"`) or AnyIO's (`@pytest.mark.anyio`).

<!-- test: pytest; deps=anyio -->
```python
import anyio
import pytest

@pytest.mark.anyio
async def test_a_slow_call_times_out() -> None:
    with anyio.move_on_after(0.01) as scope:
        await anyio.sleep(1)
    assert scope.cancelled_caught
```

## Properties

For parsers, encoders and conversions, state a property and let Hypothesis generate the inputs,
including edge cases you wouldn't write by hand. When a test fails, it shrinks the input to the
smallest example that still fails.

<!-- test: pytest; deps=hypothesis -->
```python
from decimal import Decimal

import pytest
from hypothesis import given, strategies as st

LIMIT = Decimal(10) ** 13  # above any amount this program handles
CENT = Decimal("0.01")

def to_cents(amount: Decimal) -> int:
    # Bound it first: int() of Decimal("9e999990") takes seconds, and scaleb rounds past 28 digits.
    if not amount.is_finite() or not -LIMIT < amount < LIMIT:
        raise ValueError(f"amount out of range: {amount}")
    cents = amount.quantize(CENT)
    if cents != amount:
        raise ValueError(f"not a whole number of cents: {amount}")
    return int(cents.scaleb(2))

def from_cents(cents: int) -> Decimal:
    return Decimal(cents).scaleb(-2)

@given(st.integers(min_value=-10**12, max_value=10**12))
def test_cents_survive_a_round_trip(cents: int) -> None:
    assert to_cents(from_cents(cents)) == cents

@pytest.mark.parametrize(
    ("amount", "reason"),
    [("0.019", "whole number"), ("1000000000.00000000000000000001", "whole number"),
     ("NaN", "out of range"), ("sNaN", "out of range"), ("1e13", "out of range"), ("9e999990", "out of range")],
)
def test_an_amount_that_is_not_whole_cents_is_refused(amount: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        to_cents(Decimal(amount))
```

## Configuration

Turn warnings into errors, so a deprecation fails the test suite before the next release
removes the API, and make typos in marker and option names fail too:

```toml
[tool.pytest.ini_options]
addopts = ["--strict-markers", "--strict-config"]
filterwarnings = ["error"]
xfail_strict = true
```

## Coverage and mutation

Coverage shows which lines ran, not whether a test checked what they did. Run
`coverage run --branch -m pytest`, then `coverage report -m`, and read the uncovered branches.
A mutation tester such as mutmut changes the code (`<` to `<=`, `and` to `or`) and reruns the
tests. A change that survives is a behavior that no test checks.

## Sources

- https://docs.pytest.org/en/stable/how-to/assert.html ·
  https://docs.pytest.org/en/stable/how-to/parametrize.html
- https://docs.pytest.org/en/stable/reference/reference.html (`raises`, `RaisesGroup`, `warns`)
- https://docs.pytest.org/en/stable/how-to/fixtures.html ·
  https://docs.pytest.org/en/stable/how-to/monkeypatch.html
- https://docs.pytest.org/en/stable/how-to/capture-warnings.html
- https://docs.python.org/3.13/library/unittest.mock.html#autospeccing
- https://anyio.readthedocs.io/en/stable/testing.html · https://pytest-asyncio.readthedocs.io/
- https://hypothesis.readthedocs.io/ · https://coverage.readthedocs.io/ · https://mutmut.readthedocs.io/
