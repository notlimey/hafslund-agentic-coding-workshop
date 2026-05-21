---
name: python-test-style
description: "Python unit-test discipline — pytest only, parametrize, fixtures, tmp_path, monkeypatch, no time.sleep waits, no unittest.TestCase mixing. Not for code style (→ code-style) or typing (→ typing)."
paths:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/tests/**/*.py"
  - "**/conftest.py"
---

# Python Test Style

The team uses pytest. Tests Claude writes by default tend to mix `unittest.TestCase` patterns, repeat setup across cases, and use `time.sleep` to "wait for" async work. Avoid each.

## Framework

**Pytest functions, not `unittest.TestCase` classes.** Mixing styles inside one repo makes fixtures inconsistent and forces readers to remember two mental models. New tests are plain functions.

```python
# Good
def test_parses_iso8601():
    assert parse("2026-01-01") == date(2026, 1, 1)

# Bad — don't introduce unittest.TestCase in a pytest repo
class TestParser(unittest.TestCase):
    def test_parses_iso8601(self):
        self.assertEqual(parse("2026-01-01"), date(2026, 1, 1))
```

## Parametrize

**Repeated test bodies become `@pytest.mark.parametrize`.** Three near-identical `test_x_when_y` functions are three places to update when the assertion changes.

```python
@pytest.mark.parametrize("input_,expected", [
    ("2026-01-01", date(2026, 1, 1)),
    ("2026-12-31", date(2026, 12, 31)),
], ids=["new-year", "year-end"])
def test_parses_iso8601(input_, expected):
    assert parse(input_) == expected
```

Name the ids when the values aren't self-describing.

## Fixtures

**Fixtures over module-level setup.** Pytest fixtures are composable, scoped (`function`/`module`/`session`), and lazy. Module-level mutable state leaks between tests.

**Use built-in fixtures before writing your own:**
- `tmp_path` — per-test temp directory (auto-cleaned). Never write to `/tmp` or repo paths.
- `monkeypatch` — patch env vars, attributes, dicts; auto-reverted at teardown.
- `capsys` / `caplog` — capture stdout/stderr/logging without redirecting manually.

## Time and I/O

**Never `time.sleep` in tests.** Flaky and slow. For:
- **Polling async work** — use the project's wait helper or `tenacity` with a real condition.
- **Time-sensitive code** — inject a clock (`Callable[[], datetime]`) or use `freezegun` / `time-machine`.
- **HTTP** — `respx` for httpx, `responses` for requests. Don't hit real servers in unit tests.

## Assertions

**Assert on the field that matters, not the whole object.** Asserting `result == big_dict_literal` couples the test to fields it doesn't care about — adding an unrelated field breaks an unrelated test.

```python
# Good
assert result.status == "ready"
assert result.id == "x"

# Bad
assert result == {"status": "ready", "id": "x", "created_at": ..., ...}
```

**`pytest.approx` for floats.** Don't compare floats with `==`.

## Layout

**Tests live under `tests/`** at the project root, mirroring the package structure (`tests/foo/test_bar.py` for `src/foo/bar.py`). Keeps imports obvious.

**`conftest.py` is for shared fixtures, not import-time side effects.** Putting `os.environ[...] = ...` at module top of `conftest.py` is a known footgun — use a fixture and `monkeypatch.setenv`.

## What to Test

**Test behavior, not implementation.** Asserting "was `_internal_method` called twice" is a refactor-breaker. Assert on the observable result or the side effect the caller cares about.

**One thing per test.** `test_parser_handles_empty_input`, not `test_parser`.
