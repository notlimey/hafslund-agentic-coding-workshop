---
name: python-packaging
description: "Python packaging — uv preferred, pyproject.toml shape, runtime vs dev deps, lockfile committed, PEP 723 inline scripts, src/ layout, single version source. Not for code style (→ code-style) or typing (→ typing)."
paths:
  - "**/pyproject.toml"
  - "**/uv.lock"
  - "**/requirements*.txt"
  - "**/setup.py"
  - "**/setup.cfg"
---

# Python Packaging

Team standard is `uv`. Defaults Claude reaches for that are wrong here: `pip install -r requirements.txt`, `setup.py`, recommending Poetry, and conflating runtime with dev dependencies.

## Tool Choice

**`uv` for new projects.** Faster than pip/poetry, single tool for envs + deps + lock, drop-in `pip` interface. Don't introduce Poetry to a uv repo or vice versa — pick one per repo.

**`setup.py` and `setup.cfg` are legacy.** New projects: `pyproject.toml` only. Don't add `setup.py` "just in case" — modern build backends don't need it.

## pyproject.toml Shape

```toml
[project]
name = "happi-foo"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2",
]

[project.scripts]
happi-foo = "happi_foo.cli:main"

[dependency-groups]
dev = [
    "pytest>=8",
    "mypy>=1.10",
    "ruff>=0.6",
]
```

**Runtime deps in `[project].dependencies`**, dev/test deps in `[dependency-groups].dev` (PEP 735) or `[tool.uv].dev-dependencies`. Never mix — production installs should not pull pytest.

**Pin minimums (`>=`), not exact versions**, in libraries. Applications can be stricter but should rely on the lockfile, not pyproject pins, for reproducibility.

## Lockfile

**Commit `uv.lock`.** It's the reproducible-build artifact; pyproject alone is not.

**Regenerate, don't hand-edit.** `uv lock` or `uv sync` after changing dependencies.

## When a Script Becomes a Package

A standalone `.py` in `scripts/` is fine until any of:
- It's imported from another file.
- It needs dependencies that aren't in the parent project.
- It's invoked as a console command across machines.

At that point, give it a `pyproject.toml` and a `[project.scripts]` entry. Don't ship installers that `chmod +x` raw `.py` files.

**PEP 723 inline script metadata** is the right answer for one-file scripts with deps:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
import httpx
...
```

Run with `uv run script.py`. No virtualenv setup, no `requirements.txt` drift.

## Layout

**`src/package_name/` for libraries**, not flat `package_name/` at root. Prevents accidental imports from CWD masking the installed package — a class of bug that bites only in CI.

For applications (not distributed as wheels), flat layout is OK.

## Versioning

**Single source of truth.** Either `[project].version` in pyproject or `__version__` in `__init__.py` — never both. If you need the version at runtime: `importlib.metadata.version("happi-foo")`.

**Don't hand-bump versions for internal tooling.** Use the repo's release workflow (`hatch version` or a release-please action).
