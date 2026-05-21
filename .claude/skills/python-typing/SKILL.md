---
name: python-typing
description: "Python type hints — boundaries not locals, X | None over Optional[X], Protocol vs ABC, no Any escape hatch, TypedDict for JSON, mypy/pyright strict. Not for runtime validation (→ code-style pydantic)."
paths:
  - "**/*.py"
---

# Python Typing

Defaults Claude reaches for wrong: annotating every local, falling back to `Any` when a Protocol would work, picking `Optional[X]` over modern `X | None`, and choosing `ABC` where structural typing fits.

## Where to Annotate

**Boundaries: function signatures, dataclass fields, public attributes.** Don't annotate every local — the checker infers them, and the noise hides the signatures that matter.

```python
# Good — boundary annotations, inferred locals
def parse(raw: str) -> Event:
    parts = raw.split(",")
    timestamp = int(parts[0])
    return Event(timestamp, parts[1])

# Bad — annotation noise
def parse(raw: str) -> Event:
    parts: list[str] = raw.split(",")
    timestamp: int = int(parts[0])
    ...
```

## Modern Syntax

**`X | None`, not `Optional[X]`.** Python 3.10+ syntax.

**`list[str]`, not `List[str]`.** The `typing.List` form is deprecated for new code.

**`from __future__ import annotations`** at the top of modules with forward references — makes all annotations strings, no runtime cost, no quoting for self-references.

## Protocol vs ABC

**`Protocol` for "anything with these methods"; `ABC` for explicit inheritance.** Protocols are structural — they type duck-typing without forcing callers to inherit.

```python
class SupportsClose(Protocol):
    def close(self) -> None: ...

def shutdown(thing: SupportsClose) -> None:
    thing.close()
```

If you're writing an `ABC` so callers can pass "any of these classes I own," it's still a `Protocol`.

## Any and Cast

**`Any` is a confession the type system has lost.** Acceptable in two places:
- The boundary with untyped libraries — annotate once at the seam, convert immediately.
- Genuinely dynamic data before validation.

Don't sprinkle `Any` to silence the checker. If the checker complains, the code is usually wrong.

**`cast()` is a lie to the checker.** Use only when you know more than the checker can prove (e.g. after a runtime check it can't follow). Comment why.

## JSON and Untrusted Data

**`TypedDict` for known JSON shapes** at boundaries. Cleaner than `dict[str, Any]`, narrower than a dataclass when you don't own the producer.

For untrusted input that needs *validation* (not just typing), use `pydantic.BaseModel` — typing alone doesn't enforce runtime shape.

## Generics

**Built-in syntax (3.12+):** `def first[T](xs: list[T]) -> T:`. On older versions, `T = TypeVar("T")` once at module top.

Don't reach for generics until the same function genuinely takes multiple unrelated types. A function that only ever sees `Event` should be typed as `Event`.

## Checker Configuration

**Strict mode on for new code.** `mypy --strict` or pyright `strict`. The defaults let through too much.

**Per-module overrides for legacy code**, not project-wide laxity. Migrate modules to strict incrementally — never lower the global bar.
