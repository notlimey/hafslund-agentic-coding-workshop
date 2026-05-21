---
name: python-code-style
description: "General Python style — early returns, logging over print, pathlib over os.path, subprocess argv lists, narrow except, dataclasses over dict-as-record. Not for typing (→ typing), tests (→ test-style), or packaging (→ packaging)."
paths:
  - "**/*.py"
---

# Python Code Style

Rules the team applies across scripts, services, and tooling. None are exotic — they're the defaults Claude has to be reminded of every time.

## Control Flow

**Early returns over nested `if/else`.** Guard clauses keep the happy path at the leftmost indent.

```python
# Good
if not items:
    return []
# main work
```

**`for/else` is a footgun.** The `else` runs when the loop exits without `break` — almost no reader knows this. Rewrite with a flag or extract the loop into a function that `return`s.

## Output and Logging

**`logging`, not `print`, outside CLI entry points.** `print` bypasses levels, structured fields, and log routing.

```python
import logging
log = logging.getLogger(__name__)
log.info("processed %d records", n)
```

Pass values as args, not f-string interpolation — the logging framework formats lazily and structured handlers can extract fields.

In services, use the project's structured logger (e.g. `structlog`). Never `print`, never f-string into the message.

## Paths

**`pathlib.Path`, not `os.path` string concat.** `Path("/a") / "b"` survives the trailing-slash and OS-separator bugs that `"/a" + "/" + "b"` produces.

```python
from pathlib import Path
config = Path(__file__).parent / "config" / "app.yaml"
```

## Subprocess

**Argv list, never `shell=True`** with interpolated input. `shell=True` plus any user/env value is a shell-injection bug.

```python
# Good
subprocess.run(["kubectl", "get", "pods", "-n", namespace], check=True)

# Bad
subprocess.run(f"kubectl get pods -n {namespace}", shell=True)
```

Always pass `check=True` unless you're explicitly handling a non-zero exit; silent failures hide bugs for weeks.

## Exceptions

**Catch the narrowest type that fits.** `except Exception:` is the widest you should ever go, and only with a logged reason. Never bare `except:` — it swallows `KeyboardInterrupt` and `SystemExit`.

**Don't catch to log-and-re-raise without adding context.** Either handle it or let it propagate. When you catch to add context, use `raise NewError(...) from e` to preserve the chain.

## Records and Defaults

**Dataclasses or `pydantic.BaseModel` for records**, not 4-key dicts that drift across files. Dicts are for genuinely dynamic key sets.

**No mutable defaults.** `def f(items=[]):` shares the list across calls. Use `None` and replace inside the body.

## Comprehensions

**Use them for transformation, not side effects.** A list comprehension that calls a void function is harder to read than a `for` loop. If you're not collecting a value, write the loop.

## Mandatory Checks Before Shipping

1. **Linter/formatter clean.** `ruff check` and `ruff format` (or the project's configured equivalent).
2. **No `print()`** outside `__main__` blocks and CLI entry points.
3. **No `shell=True`** unless the command is a hard-coded literal with no interpolation.
4. **No bare `except:` or `except Exception:`** without a logged reason.
5. **No `os.path.join`** in new code; use `pathlib`.
