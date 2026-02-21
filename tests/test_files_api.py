"""Integration tests for the files upload/list endpoints."""
import io
import pytest


def _make_run(client, name: str = "Test Run") -> int:
    return client.post("/runs", json={"name": name}).json()["id"]


def test_upload_csv_returns_201(client):
    run_id = _make_run(client)
    csv_bytes = b"name,hours\nAlice,8\nBob,6"
    resp = client.post(
        f"/runs/{run_id}/files/upload",
        files={"file": ("timesheets.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["status"] == "UPLOADED"
    assert body["original_filename"] == "timesheets.csv"
    assert body["run_id"] == run_id


def test_upload_dedup_returns_same_id(client):
    run_id = _make_run(client)
    csv_bytes = b"id,value\n1,100"
    first = client.post(
        f"/runs/{run_id}/files/upload",
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    ).json()
    second = client.post(
        f"/runs/{run_id}/files/upload",
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    ).json()
    assert first["id"] == second["id"]


def test_list_files_returns_file_list(client):
    run_id = _make_run(client)
    csv_bytes = b"col\nval"
    client.post(
        f"/runs/{run_id}/files/upload",
        files={"file": ("f.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    resp = client.get(f"/runs/{run_id}/files")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


def test_upload_to_nonexistent_run_returns_404(client):
    resp = client.post(
        "/runs/99999/files/upload",
        files={"file": ("x.csv", io.BytesIO(b"a,b"), "text/csv")},
    )
    assert resp.status_code == 404
