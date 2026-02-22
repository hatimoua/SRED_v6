import pytest
from unittest.mock import MagicMock, patch
from sred.ui.validation import validate_data_dir, validate_backend_connection
from sred.storage.files import sanitize_filename, compute_sha256, save_upload
from pathlib import Path

def test_sanitization():
    assert sanitize_filename("foo bar.txt") == "foo_bar.txt"
    assert sanitize_filename("../foo.txt") == ".._foo.txt"
    assert sanitize_filename("foo/bar") == "foo_bar"

def test_hashing():
    data = b"hello world"
    expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert compute_sha256(data) == expected

def test_save_upload(tmp_path):
    # Mock DATA_DIR
    with patch("sred.storage.files.DATA_DIR", tmp_path):
        mock_file = MagicMock()
        mock_file.getvalue.return_value = b"test content"
        mock_file.name = "test.txt"
        mock_file.type = "text/plain"

        run_id = 999
        path, sha, size, mime = save_upload(run_id, mock_file)

        expected_path = tmp_path / "runs" / "999" / "uploads" / f"{sha}_test.txt"
        assert expected_path.exists()
        assert size == 12
        assert mime == "text/plain"
        # Check return path is relative
        assert path == f"runs/999/uploads/{sha}_test.txt"

def test_validation():
    # Data dir validation should pass with a real data dir
    errors = validate_data_dir()
    # May or may not have errors depending on env, just ensure no crash
    assert isinstance(errors, list)

    # Backend connection will fail in test (no server), but should not crash
    errors = validate_backend_connection()
    assert isinstance(errors, list)
    # Expect a connection error since no backend is running
    assert len(errors) > 0
