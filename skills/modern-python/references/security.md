# Security

Contents: commands · SQL · deserializing · secrets and tokens · passwords · paths · archives ·
XML · URLs and HTTP · temporary files and assert · sources

Everything from outside the process is untrusted: request bodies and headers, uploaded files,
environment variables, command-line arguments and rows that other users wrote. Convert it once,
at the edge, into typed values (see `modeling.md`), and never let it become code, a command, a
query or a path without a check.

The ruff `S` rules (from bandit) flag most patterns below, and each section names its rule or says
that none exists; `review.md` lists what ruff misses. A hit is a question to answer: fix it, or
silence it with a reason, as in `# noqa: S603 - fixed program, list arguments`.

## Commands

- Pass the arguments as a list. A string with `shell=True` (S602) or `os.system` (S605) goes
  through a shell, which runs whatever follows `;`, `|` or `$(...)`.
- ruff flags a `subprocess` call whose arguments aren't all literals (S603), since one of them may
  come from the user. The program itself never should: name it by absolute path or through
  `shutil.which` (S607).
- Put `--` before user arguments when the program takes options, so `-rf` stays a file name.
  Set `timeout=` and `check=True`.

```python
import subprocess, sys

name = "x; rm -rf ~"
# avoid: subprocess.run(f"echo {name}", shell=True)  -- the shell runs rm
args = [sys.executable, "-c", "import sys; print(sys.argv[1])", name]
result = subprocess.run(args, capture_output=True, text=True, check=True, timeout=10)
assert result.stdout == "x; rm -rf ~\n"
```

## SQL

Bind every value as a parameter, so the driver sends it apart from the query text. A query built
with an f-string, `%` or `+` is S608. Placeholders depend on the driver: `?` or `:name` in sqlite3,
`%s` in psycopg, `$1` in asyncpg. Table and column names can't be parameters, so take them from
a fixed set. In sqlite3, `with conn:` commits or rolls back but doesn't close; call `close()`.

```python
import sqlite3

conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE users (name TEXT, age INT)")
name = "x'); DROP TABLE users; --"
# avoid: conn.execute(f"INSERT INTO users (name, age) VALUES ('{name}', 30)")
conn.execute("INSERT INTO users (name, age) VALUES (?, ?)", (name, 30))

SORTABLE = {"name": "name", "age": "age"}
column = SORTABLE["age"]  # a KeyError for anything else
rows = conn.execute(f"SELECT name, age FROM users ORDER BY {column}").fetchall()  # noqa: S608 - column from SORTABLE
assert rows == [(name, 30)]
conn.close()
```

## Deserializing

- `pickle` and `shelve` can run code while loading (S301), and `marshal` isn't safe against
  malicious data either (S302). Load only what this program wrote itself; take anything else as
  JSON.
- `eval` and `exec` run code (S307, S102). For a Python literal use `ast.literal_eval`, and cap
  the input size first: deeply nested input can still raise `RecursionError` or `MemoryError`.
- `yaml.load` with the full or unsafe loader builds any Python object (S506). Use `yaml.safe_load`.

<!-- test: deps=pyyaml; raises=yaml.constructor.ConstructorError -->
```python
import ast
import yaml

assert ast.literal_eval("{'a': [1, 2]}") == {"a": [1, 2]}  # and ValueError for code
assert yaml.safe_load("port: 8080") == {"port": 8080}
yaml.safe_load('!!python/object/apply:os.system ["echo pwned"]')  # raises ConstructorError
```

## Secrets and tokens

- Tokens, session ids, reset links and API keys come from `secrets`, never from `random` (S311).
- Compare a secret with `hmac.compare_digest`. `==` returns at the first different character, and
  the time it takes tells an attacker how much of a guess was right. ruff doesn't flag this.
  Compare bytes: given two `str`, `compare_digest` raises `TypeError` when either one isn't ASCII,
  so a guess such as `"é"` would crash the check instead of failing it.
- Read secrets from the environment or a secret manager, never from the source (S105–S107), and keep
  them out of logs and exception messages.

```python
import hmac, secrets

def matches(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.encode(), expected.encode())

token = secrets.token_urlsafe(32)  # 32 random bytes as 43 URL-safe characters
assert len(token) == 43
assert matches(token, token) and not matches("guess", token) and not matches("é", token)
```

## Passwords

Store a slow, salted hash, never the password or a fast hash. MD5 and SHA-1 are S324; SHA-256 isn't
flagged, but it is just as wrong for passwords. OWASP's order is Argon2id, then scrypt, then bcrypt
for legacy systems, then PBKDF2 where FIPS-140 requires it (600,000 iterations of HMAC-SHA256).

With a dependency, use `argon2-cffi`. `PasswordHasher()` uses Argon2id with the low-memory profile
of RFC 9106 (64 MiB, 3 passes, 4 lanes), above OWASP's minimum (19 MiB, 2 passes, 1 lane). The hash
string carries its salt and parameters, so `check_needs_rehash` can tell when to hash again at login.

<!-- test: deps=argon2-cffi; raises=VerifyMismatchError -->
```python
from argon2 import PasswordHasher

hasher = PasswordHasher()
stored = hasher.hash("correct horse")
assert stored.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
assert hasher.verify(stored, "correct horse")
hasher.verify(stored, "wrong")  # raises VerifyMismatchError
```

With the standard library only, use `hashlib.scrypt`. OWASP's first setting, N=2^17, r=8, p=1, needs
128 MiB, past OpenSSL's default memory limit of 32 MiB, so it raises `ValueError` unless you raise
`maxmem`. OWASP lists N=2^14, r=8, p=5 (16 MiB) as a similar minimum. Keep the salt and the
parameters next to the hash.

```python
import hashlib, hmac, secrets

PARAMS = {"n": 2**14, "r": 8, "p": 5}

def hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, dklen=32, **PARAMS)

salt = secrets.token_bytes(16)
stored = hash_password("correct horse", salt)
assert hmac.compare_digest(hash_password("correct horse", salt), stored)
assert not hmac.compare_digest(hash_password("wrong", salt), stored)
```

## Paths from users

`base / user_path` doesn't stay in `base`: `..` climbs out, and an absolute `user_path` replaces
`base` altogether. Resolve the joined path, which also follows symlinks, and check that it is still
inside. ruff doesn't flag the join. The check holds at that moment only: if an attacker can write
to the directory, they can still swap in a symlink before you open the file.

<!-- test: raises=PermissionError -->
```python
from pathlib import Path

def inside(base: Path, user_path: str) -> Path:
    target = (base / user_path).resolve()
    if not target.is_relative_to(base.resolve()):
        raise PermissionError(f"outside {base}: {user_path!r}")
    return target

base = Path("/srv/files")
assert base / "/etc/passwd" == Path("/etc/passwd")  # the absolute part wins
assert inside(base, "reports/2026.pdf") == base.resolve() / "reports" / "2026.pdf"
inside(base, "../../etc/passwd")  # raises PermissionError
```

## Archives

`tarfile` with `filter="data"` (3.12+, and the default from 3.14) strips leading slashes, refuses
members and links that would land outside the destination, and refuses device files. It raises a
subclass of `tarfile.FilterError`. S202 flags `extractall` without a filter. `zipfile` strips
leading slashes and `..` from names. Neither module limits size, so before you extract an upload,
add up `TarInfo.size` or `ZipInfo.file_size` to stop a decompression bomb.

<!-- test: raises=tarfile.OutsideDestinationError -->
```python
import io, tarfile, tempfile

buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w") as tar:
    member = tarfile.TarInfo("../escape.txt")
    member.size = 2
    tar.addfile(member, io.BytesIO(b"hi"))
buffer.seek(0)
with tempfile.TemporaryDirectory() as dest, tarfile.open(fileobj=buffer) as tar:
    tar.extractall(dest, filter="data")  # raises OutsideDestinationError
```

## XML

The standard parsers are only as safe as the Expat library they use. The docs warn that versions
below 2.7.2 may be open to billion laughs, quadratic blowup and large-token attacks. Builds differ,
so check `pyexpat.EXPAT_VERSION`. For XML from outside, use `defusedxml`, which S314 suggests: it
refuses entity declarations outright.

<!-- test: deps=defusedxml; raises=EntitiesForbidden -->
```python
import defusedxml.ElementTree as ET

assert ET.fromstring('<order id="7"/>').get("id") == "7"
ET.fromstring('<!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><l>&b;</l>')  # raises EntitiesForbidden
```

## URLs and HTTP

- `urllib.request.urlopen` also opens `file:` and other schemes (S310).
- When you fetch a URL that a user gave you (a webhook, a preview, an import), it can point at your
  internal services or the cloud metadata address (SSRF). Allow only `https`, known hosts and the
  default port, and check every redirect too: requests follows redirects by default, httpx doesn't.
- Parsers disagree on unusual URLs. For `https://evil.com\@api.example.com/`, `urlsplit` returns
  the host `api.example.com`, while urllib3, which requests uses, connects to `evil.com`. Refuse
  characters outside RFC 3986 and any user info, as below, or check the URL with the parser of the
  client that sends it.
- `requests` has no default timeout, so pass `timeout=` (S113). httpx defaults to 5 seconds, and
  S113 flags `timeout=None`. Never pass `verify=False` (S501).

```python
import re
from urllib.parse import urlsplit

ALLOWED_HOSTS = frozenset({"api.example.com"})
URL_CHARACTERS = re.compile(r"[-A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%]+")  # RFC 3986

def allowed(url: str) -> bool:
    if not URL_CHARACTERS.fullmatch(url):  # a backslash, a space, a control character
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:  # a port out of range, an unclosed [
        return False
    return (
        parts.scheme == "https"
        and parts.hostname in ALLOWED_HOSTS
        and "@" not in parts.netloc
        and port in (None, 443)
    )

assert allowed("https://api.example.com/v1/items") and allowed("https://api.example.com:443/")
refused = ["file:///etc/passwd", "http://api.example.com/", "https://169.254.169.254/",
           "https://evil.com\\@api.example.com/", "https://user@api.example.com/",
           "https://api.example.com:8443/", "https://api.example.com:99999/", "https://[api.example.com/"]
assert not any(map(allowed, refused))
```

## Temporary files and `assert`

- `tempfile.mktemp` (S306) and fixed paths under `/tmp` (S108) let another user create the file
  first. `NamedTemporaryFile`, `mkstemp` and `TemporaryDirectory` create it in one step, readable
  only by your user.
- `python -O` removes every `assert`, so never use one for permissions or input validation (S101).
  Raise an exception instead. The asserts in these references only demonstrate results.

## Sources

- https://docs.python.org/3.13/library/security_warnings.html ·
  https://docs.python.org/3.13/library/subprocess.html#security-considerations
- https://docs.python.org/3.13/library/sqlite3.html#sqlite3-placeholders ·
  https://docs.python.org/3.13/library/pickle.html · https://docs.python.org/3.13/library/ast.html#ast.literal_eval
- https://docs.python.org/3.13/library/secrets.html · https://docs.python.org/3.13/library/hmac.html ·
  https://docs.python.org/3.13/library/hashlib.html#hashlib.scrypt
- https://docs.python.org/3.14/library/tarfile.html#extraction-filters · https://peps.python.org/pep-0706/ ·
  https://docs.python.org/3.13/library/zipfile.html · https://docs.python.org/3.13/library/tempfile.html
- https://docs.python.org/3/library/xml.html#xml-security
- https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- https://argon2-cffi.readthedocs.io/en/stable/ · https://github.com/tiran/defusedxml ·
  https://pyyaml.org/wiki/PyYAMLDocumentation
- https://requests.readthedocs.io/en/latest/user/advanced/ (timeouts) · https://docs.astral.sh/ruff/rules/
