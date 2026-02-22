"""Pre-flight validation for the Streamlit UI.

No ORM, no DB — uses the API client for backend checks.
"""
from typing import List
from pathlib import Path


def validate_data_dir() -> List[str]:
    """Validate data directory structure and permissions."""
    errors = []
    # Import here to avoid circular issues at module level
    from sred.config import settings
    data_dir = settings.data_dir

    if not data_dir.exists():
        errors.append(f"Data directory missing: {data_dir}")
        return errors

    runs_dir = data_dir / "runs"
    try:
        if not runs_dir.exists():
            runs_dir.mkdir(parents=True, exist_ok=True)
        test_file = runs_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
    except Exception as e:
        errors.append(f"Cannot write to runs directory {runs_dir}: {e}")

    return errors


def validate_backend_connection() -> List[str]:
    """Validate that the FastAPI backend is reachable."""
    errors = []
    try:
        from sred.ui.api_client import SREDClient
        client = SREDClient()
        client.health()
    except Exception as e:
        errors.append(f"Backend connection failed: {e}")
    return errors


def run_all_checks() -> List[str]:
    """Run all validation checks."""
    errors = []
    errors.extend(validate_data_dir())
    errors.extend(validate_backend_connection())
    return errors
