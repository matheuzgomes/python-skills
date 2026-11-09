# Production pitfalls

Contents: money · floats · dates and times · text encoding · logging · configuration · sources

Each of these works on a laptop and breaks in production: on another locale, time zone or day
of the year, or with real amounts of money.

## Money is Decimal, never float

- Build a `Decimal` from a `str` or an `int`. `Decimal(0.1)` keeps the binary value of the float.
- Round with `quantize` and name the rounding. The default, like `round()`, is half to even
  (banker's rounding), which is often not what an invoice or a tax rule asks for.
- The `FloatOperation` trap makes mixing floats in raise: in the constructor and in `<` or `>`.
  `==` with a float doesn't raise; it just compares.
- `json` can't write a `Decimal`, and it reads `9.90` as a float. Read with `parse_float=Decimal`,
  and write amounts as strings.

<!-- test: raises=decimal.FloatOperation -->
```python
import json
from decimal import ROUND_HALF_UP, Decimal, FloatOperation, localcontext

assert str(Decimal(0.1)).startswith("0.1000000000000000055")
price = Decimal("0.125")
assert price.quantize(Decimal("0.01")) == Decimal("0.12")  # half to even
assert price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal("0.13")
assert round(2.5) == 2 and round(3.5) == 4

order = json.loads('{"total": 9.90}', parse_float=Decimal)
assert order["total"] == Decimal("9.90")
assert json.dumps({"total": str(order["total"])}) == '{"total": "9.90"}'

with localcontext() as ctx:
    ctx.traps[FloatOperation] = True
    Decimal("1.50") + Decimal(1.5)  # raises FloatOperation
```

Integer cents are the other safe choice, when every amount has the same number of decimal places.

## Floats

- Compare with `math.isclose`. Its defaults are `rel_tol=1e-09` and `abs_tol=0.0`, so near zero
  nothing is close to 0 unless you pass `abs_tol`.
- NaN is not equal to itself. Test it with `math.isnan`.
- Since 3.12, `sum()` of floats uses compensated summation, so it no longer drifts on long lists.

```python
import math

assert 0.1 + 0.2 != 0.3 and math.isclose(0.1 + 0.2, 0.3)
assert not math.isclose(1e-12, 0) and math.isclose(1e-12, 0, abs_tol=1e-9)
nan = float("nan")
assert nan != nan and math.isnan(nan)
assert sum([0.1] * 10) == 1.0
```

## Dates and times

- Use aware datetimes only. `datetime.now(UTC)`, not `datetime.now()` (DTZ005). `utcnow()` and
  `utcfromtimestamp()` return naive values and are deprecated since 3.12 (DTZ003, DTZ004). `date.today()`
  uses the server's time zone (DTZ011). The DTZ rules aren't part of `S`; enable them.
- Store and compute in UTC. Convert to the user's zone with `zoneinfo.ZoneInfo` only to show a
  time or to read one the user typed. On Windows and in slim containers, install `tzdata`.
- Arithmetic on an aware datetime moves the wall clock, not the elapsed time. Across a daylight
  saving change it can land on a time that doesn't exist, and "one day later" can be 23 hours.
  For elapsed time, go through UTC.
- Ordering a naive and an aware datetime raises `TypeError`, but `==` silently returns `False`.
- `datetime.fromisoformat` accepts a trailing `Z` since 3.11.

```python
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

new_york = ZoneInfo("America/New_York")
before = datetime(2026, 3, 8, 1, 30, tzinfo=new_york)  # clocks jump from 2:00 to 3:00 that night
assert (before + timedelta(hours=1)).hour == 2  # 2:30 never happens in New York that day
after = (before.astimezone(UTC) + timedelta(hours=1)).astimezone(new_york)
assert (after.hour, after.minute) == (3, 30)

assert datetime.fromisoformat("2026-11-08T12:00:00Z") == datetime(2026, 11, 8, 12, tzinfo=UTC)
assert datetime(2026, 1, 1) != datetime(2026, 1, 1, tzinfo=UTC)  # never equal, no error
```

## Text encoding

- `open`, `Path.read_text` and `Path.write_text` use the locale's encoding unless you pass one,
  until UTF-8 mode becomes the default in 3.15 (PEP 686). Pass `encoding="utf-8"` every time.
  `python -X warn_default_encoding` emits `EncodingWarning` where it is missing (PEP 597), and
  ruff's PLW1514 flags it, in preview only.
- The same goes for `subprocess.run(..., text=True)`: pass `encoding="utf-8"`.
- Open CSV files with `newline=""`, or the csv module mishandles line breaks inside quoted fields.
- Decode bytes once, at the edge, and keep `str` inside the program.

```python
from pathlib import Path

path = Path("note.txt")
path.write_text("café", encoding="utf-8")
assert path.read_bytes() == b"caf\xc3\xa9"
assert path.read_text(encoding="utf-8") == "café"
```

## Logging

- Each module gets `logger = logging.getLogger(__name__)`. Only the program's entry point
  configures handlers and levels; a library never calls `basicConfig`.
- Pass values as arguments, as in `logger.info("order %s paid", order_id)`. The text is built only
  if the record is emitted, and log tools can group records by their template. An f-string is
  G004.
- Inside `except`, `logger.exception("...")` logs the traceback too. `exc_info=True` outside a
  handler has no traceback to log (LOG014).
- Never log secrets, tokens, passwords or full card numbers.

```python
import logging

records: list[logging.LogRecord] = []

class Collect(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        records.append(record)

logger = logging.getLogger("shop.orders")
logger.addHandler(Collect())
logger.setLevel(logging.INFO)

logger.info("order %s paid", 42)
assert (records[0].msg, records[0].getMessage()) == ("order %s paid", "order 42 paid")
try:
    1 / 0
except ZeroDivisionError:
    logger.exception("payment failed")
assert records[1].exc_info is not None and records[1].exc_info[0] is ZeroDivisionError
```

## Configuration

Read the environment once at startup into a frozen, typed object, so a missing or bad value
stops the program before it serves anything. `bool("false")` is `True`, so parse flags yourself.

```python
from collections.abc import Mapping
from dataclasses import dataclass

def parse_flag(raw: str) -> bool:
    match raw.strip().lower():
        case "1" | "true" | "yes" | "on":
            return True
        case "0" | "false" | "no" | "off" | "":
            return False
        case _:
            raise ValueError(f"not a boolean: {raw!r}")

@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    debug: bool

def load_settings(env: Mapping[str, str]) -> Settings:  # pass os.environ
    return Settings(database_url=env["DATABASE_URL"], debug=parse_flag(env.get("DEBUG", "")))

assert bool("false") is True
assert load_settings({"DATABASE_URL": "postgresql://db/app", "DEBUG": "false"}).debug is False
```

## Sources

- https://docs.python.org/3.13/library/decimal.html · https://docs.python.org/3.13/tutorial/floatingpoint.html
- https://docs.python.org/3.13/library/math.html#math.isclose · https://docs.python.org/3.13/library/json.html
- https://docs.python.org/3/whatsnew/3.12.html (`sum`, `utcnow` deprecation)
- https://docs.python.org/3.13/library/datetime.html · https://docs.python.org/3.13/library/zoneinfo.html ·
  https://peps.python.org/pep-0615/
- https://docs.python.org/3.13/library/io.html#text-encoding · https://peps.python.org/pep-0597/ ·
  https://peps.python.org/pep-0686/ · https://docs.python.org/3.13/library/csv.html
- https://docs.python.org/3.13/howto/logging.html · https://docs.python.org/3.13/library/logging.html
- https://docs.astral.sh/ruff/rules/ (DTZ, G, LOG, PLW1514)
