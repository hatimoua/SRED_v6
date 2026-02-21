"""Integration tests for the ingest endpoint."""
import io
import pytest
from unittest.mock import patch


def _make_run(client, name: str = "Ingest Run") -> int:
    return client.post("/runs", json={"name": name}).json()["id"]


def _upload_csv(client, run_id: int) -> int:
    resp = client.post(
        f"/runs/{run_id}/files/upload",
        files={"file": ("data.csv", io.BytesIO(b"col\nval"), "text/csv")},
    )
    return resp.json()["id"]


def test_process_file_returns_completed(client):
    run_id = _make_run(client)
    file_id = _upload_csv(client, run_id)

    with patch("sred.ingest.process.process_source_file") as mock_process:
        mock_process.return_value = None
        resp = client.post(f"/runs/{run_id}/files/{file_id}/process")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["file_id"] == file_id
    mock_process.assert_called_once_with(file_id=file_id)


def test_process_nonexistent_file_returns_404(client):
    run_id = _make_run(client)
    resp = client.post(f"/runs/{run_id}/files/99999/process")
    assert resp.status_code == 404


def test_process_already_processed_file_returns_already_processed(client):
    run_id = _make_run(client)
    file_id = _upload_csv(client, run_id)

    # Manually mark as PROCESSED in DB
    from sred.infra.db.uow import UnitOfWork
    from sred.models.core import File, FileStatus

    with UnitOfWork() as uow:
        file = uow.session.get(File, file_id)
        file.status = FileStatus.PROCESSED
        uow.commit()

    with patch("sred.ingest.process.process_source_file") as mock_process:
        resp = client.post(f"/runs/{run_id}/files/{file_id}/process")

    assert resp.status_code == 200
    assert resp.json()["message"] == "already processed"
    mock_process.assert_not_called()
