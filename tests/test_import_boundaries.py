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

KNOWN_LEGACY_VIOLATIONS = {
    "src/sred/ui/state.py",
    "src/sred/ui/validation.py",
    "src/sred/ui/pages/1_run.py",
    "src/sred/ui/pages/2_people.py",
    "src/sred/ui/pages/3_uploads.py",
    "src/sred/ui/pages/4_dashboard.py",
    "src/sred/ui/pages/5_search.py",
    "src/sred/ui/pages/6_csv_tools.py",
    "src/sred/ui/pages/7_agent.py",
    "src/sred/ui/pages/8_tasks.py",
    "src/sred/ui/pages/9_payroll.py",
    "src/sred/ui/pages/10_trace.py",
    "src/sred/ui/pages/11_ledger.py",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent


def _is_banned_import(module_name: str) -> bool:
    """Return True if the module name is in the banned set or starts with a banned prefix."""
    if module_name in BANNED_MODULES:
        return True
    return any(module_name.startswith(prefix) for prefix in BANNED_PREFIXES)


def _file_has_banned_imports(path: Path) -> bool:
    """Parse *path* with AST and return True if any import is banned."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # If the file can't be parsed, treat it as a violation so it's noticed.
        return True

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_banned_import(alias.name):
                    return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_banned_import(module):
                return True

    return False


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
    violations = []
    for py_file in sorted(services_root.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fastapi"):
                violations.append(_repo_relative(py_file))
                break
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("fastapi"):
                        violations.append(_repo_relative(py_file))
                        break
    assert not violations, (
        "Service files must not import fastapi:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
