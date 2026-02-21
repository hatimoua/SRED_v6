"""Integration tests for the /runs endpoints."""
import pytest


def test_create_run_returns_201(client):
    resp = client.post("/runs", json={"name": "My First Run"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["name"] == "My First Run"
    assert body["status"] == "INITIALIZING"


def test_get_run_returns_200(client):
    created = client.post("/runs", json={"name": "Fetch Me"}).json()
    resp = client.get(f"/runs/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_run_not_found_returns_404(client):
    resp = client.get("/runs/99999")
    assert resp.status_code == 404


def test_list_runs_returns_run_list(client):
    client.post("/runs", json={"name": "Run A"})
    client.post("/runs", json={"name": "Run B"})
    resp = client.get("/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 2


def test_create_run_empty_name_returns_422(client):
    resp = client.post("/runs", json={"name": ""})
    assert resp.status_code == 422
