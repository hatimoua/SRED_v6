"""
Import boundary guard for src/sred/ui/.

Rule (target architecture): UI files must never import sqlmodel, sqlalchemy,
or any sred ORM/DB modules (sred.models, sred.db, sred.domain.models).

Strategy: explicit legacy allowlist.
- The test PASSES now because every current violation is listed below.
- The test FAILS if a NEW file is added to src/sred/ui/ with ORM imports.
- The test FAILS if a listed file no longer violates (forces the allowlist to
  shrink as files are migrated, preventing stale entries).

When a page is migrated to use the API client instead of ORM imports:
  1. Fix the imports in the page file.
  2. Remove it from KNOWN_LEGACY_VIOLATIONS.
  3. Re-run the test — it should still pass.
"""

import ast
import os
from collections.abc import Callable
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UI_ROOT = Path(__file__).parent.parent / "src" / "sred" / "ui"

# Banned top-level module names / prefixes detected via AST.
# Any `import X` or `from X ...` where X matches one of these is a violation.
BANNED_MODULES = {
    "sqlmodel",
    "sqlalchemy",
}
BANNED_PREFIXES = (
    "sred.models",
    "sred.db",
    "sred.domain.models",
    "sred.infra.db",
    "sred.services",
)

# ---------------------------------------------------------------------------
# Known legacy violations — shrink this list as pages are migrated.
# Paths are relative to the repo root (forward slashes, POSIX-style).
# ---------------------------------------------------------------------------

KNOWN_LEGACY_VIOLATIONS: set[str] = set()  # All pages migrated to API client!

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


def _is_banned_import(module_name: str) -> bool:
    """Return True if the module name is in the banned set or starts with a banned prefix."""
    if module_name in BANNED_MODULES:
        return True
    return any(module_name.startswith(prefix) for prefix in BANNED_PREFIXES)


def _file_imports_any(path: Path, is_banned: Callable[[str], bool]) -> bool:
    """Parse *path* with AST and return True if any import matches *is_banned*."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return True

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if is_banned(alias.name):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if is_banned(node.module or ""):
                return True

    return False


def _file_has_banned_imports(path: Path) -> bool:
    """Return True if *path* contains any import banned for UI files."""
    return _file_imports_any(path, _is_banned_import)


def _collect_ui_python_files() -> list[Path]:
    """Walk src/sred/ui/ and return all .py files."""
    return sorted(UI_ROOT.rglob("*.py"))


def _repo_relative(path: Path) -> str:
    """Return a POSIX-style path relative to the repo root."""
    return path.relative_to(REPO_ROOT).as_posix()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_ui_import_boundaries() -> None:
    """
    Actual violations must exactly equal KNOWN_LEGACY_VIOLATIONS.

    - Extra violation  → new file introduced a banned import (FAIL — fix the import)
    - Missing violation → a listed file no longer imports ORM (PASS after removing from allowlist)
    """
    actual_violations: set[str] = set()

    for py_file in _collect_ui_python_files():
        if _file_has_banned_imports(py_file):
            actual_violations.add(_repo_relative(py_file))

    extra = actual_violations - KNOWN_LEGACY_VIOLATIONS
    stale = KNOWN_LEGACY_VIOLATIONS - actual_violations

    messages: list[str] = []

    if extra:
        messages.append(
            "NEW ORM imports found in UI files not in the legacy allowlist "
            "(add API-client calls instead of ORM imports):\n"
            + "\n".join(f"  {p}" for p in sorted(extra))
        )

    if stale:
        messages.append(
            "Files listed in KNOWN_LEGACY_VIOLATIONS no longer have banned imports "
            "(remove them from the allowlist to record migration progress):\n"
            + "\n".join(f"  {p}" for p in sorted(stale))
        )

    assert not messages, "\n\n".join(messages)


def test_service_import_boundaries() -> None:
    """Service files must not import from fastapi."""
    services_root = REPO_ROOT / "src" / "sred" / "services"
    _is_fastapi = lambda m: m.startswith("fastapi")  # noqa: E731
    violations = [
        _repo_relative(py_file)
        for py_file in sorted(services_root.rglob("*.py"))
        if _file_imports_any(py_file, _is_fastapi)
    ]
    assert not violations, (
        "Service files must not import fastapi:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
