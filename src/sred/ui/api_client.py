"""Typed HTTP client for Streamlit pages.

Only imports from ``sred.api.schemas`` — never ORM, never DB.
Instantiate via ``get_client()`` which caches per Streamlit session.
"""
from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from sred.api.schemas.runs import RunRead, RunList
from sred.api.schemas.files import FileRead, FileList
from sred.api.schemas.ingest import IngestResponse
from sred.api.schemas.people import PersonCreate, PersonRead, PersonList, PersonUpdate
from sred.api.schemas.dashboard import DashboardSummary
from sred.api.schemas.logs import ToolCallLogList, LLMCallLogList
from sred.api.schemas.search import SearchQuery, SearchResponse
from sred.api.schemas.tasks import (
    ContradictionList, ReviewTaskList, DecisionLockList,
    ReviewDecisionRead, DecisionLockRead, GateStatusResponse,
    ResolveTaskRequest, SupersedeRequest,
)
from sred.api.schemas.payroll import PayrollValidationResponse
from sred.api.schemas.ledger import LedgerSummaryResponse
from sred.api.schemas.csv import (
    CSVProfileResponse, CSVQueryResponse, MappingProposalList,
)


_DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class APIError(Exception):
    """Raised when the backend returns a 4xx/5xx response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"[{status_code}] {detail}")


class SREDClient:
    """One method per backend endpoint.  All return pure Pydantic DTOs."""

    def __init__(self, base_url: str = _DEFAULT_BASE_URL) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=30.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.is_success:
            return
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise APIError(resp.status_code, detail)

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def list_runs(self, limit: int = 100, offset: int = 0) -> RunList:
        resp = self._client.get("/runs", params={"limit": limit, "offset": offset})
        self._raise_for_status(resp)
        return RunList.model_validate(resp.json())

    def create_run(self, name: str) -> RunRead:
        resp = self._client.post("/runs", json={"name": name})
        self._raise_for_status(resp)
        return RunRead.model_validate(resp.json())

    def get_run(self, run_id: int) -> RunRead:
        resp = self._client.get(f"/runs/{run_id}")
        self._raise_for_status(resp)
        return RunRead.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def list_files(self, run_id: int) -> FileList:
        resp = self._client.get(f"/runs/{run_id}/files")
        self._raise_for_status(resp)
        return FileList.model_validate(resp.json())

    def upload_file(
        self, run_id: int, filename: str, content: bytes, content_type: str,
    ) -> FileRead:
        resp = self._client.post(
            f"/runs/{run_id}/files/upload",
            files={"file": (filename, content, content_type)},
        )
        self._raise_for_status(resp)
        return FileRead.model_validate(resp.json())

    def process_file(self, run_id: int, file_id: int) -> IngestResponse:
        resp = self._client.post(f"/runs/{run_id}/files/{file_id}/process")
        self._raise_for_status(resp)
        return IngestResponse.model_validate(resp.json())

    # ------------------------------------------------------------------
    # People
    # ------------------------------------------------------------------

    def list_people(self, run_id: int) -> PersonList:
        resp = self._client.get(f"/runs/{run_id}/people")
        self._raise_for_status(resp)
        return PersonList.model_validate(resp.json())

    def create_person(self, run_id: int, payload: PersonCreate) -> PersonRead:
        resp = self._client.post(f"/runs/{run_id}/people", json=payload.model_dump())
        self._raise_for_status(resp)
        return PersonRead.model_validate(resp.json())

    def update_person(self, run_id: int, person_id: int, payload: PersonUpdate) -> PersonRead:
        resp = self._client.patch(
            f"/runs/{run_id}/people/{person_id}", json=payload.model_dump(exclude_none=True),
        )
        self._raise_for_status(resp)
        return PersonRead.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def get_dashboard(self, run_id: int) -> DashboardSummary:
        resp = self._client.get(f"/runs/{run_id}/summary")
        self._raise_for_status(resp)
        return DashboardSummary.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Logs / Execution Trace
    # ------------------------------------------------------------------

    def list_tool_calls(
        self, run_id: int, *, limit: int = 50, offset: int = 0, tool_name: str | None = None,
    ) -> ToolCallLogList:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if tool_name:
            params["tool_name"] = tool_name
        resp = self._client.get(f"/runs/{run_id}/logs/tool-calls", params=params)
        self._raise_for_status(resp)
        return ToolCallLogList.model_validate(resp.json())

    def list_llm_calls(self, run_id: int, *, limit: int = 20, offset: int = 0) -> LLMCallLogList:
        resp = self._client.get(
            f"/runs/{run_id}/logs/llm-calls", params={"limit": limit, "offset": offset},
        )
        self._raise_for_status(resp)
        return LLMCallLogList.model_validate(resp.json())

    def list_sessions(self, run_id: int) -> list[dict]:
        resp = self._client.get(f"/runs/{run_id}/logs/sessions")
        self._raise_for_status(resp)
        return resp.json()

    def get_session_trace(self, run_id: int, session_id: str) -> dict:
        resp = self._client.get(f"/runs/{run_id}/logs/sessions/{session_id}")
        self._raise_for_status(resp)
        return resp.json()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, run_id: int, payload: SearchQuery) -> SearchResponse:
        resp = self._client.post(f"/runs/{run_id}/search", json=payload.model_dump())
        self._raise_for_status(resp)
        return SearchResponse.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Tasks & Gates
    # ------------------------------------------------------------------

    def get_gate_status(self, run_id: int) -> GateStatusResponse:
        resp = self._client.get(f"/runs/{run_id}/gate")
        self._raise_for_status(resp)
        return GateStatusResponse.model_validate(resp.json())

    def list_contradictions(self, run_id: int) -> ContradictionList:
        resp = self._client.get(f"/runs/{run_id}/contradictions")
        self._raise_for_status(resp)
        return ContradictionList.model_validate(resp.json())

    def list_tasks(self, run_id: int) -> ReviewTaskList:
        resp = self._client.get(f"/runs/{run_id}/tasks")
        self._raise_for_status(resp)
        return ReviewTaskList.model_validate(resp.json())

    def resolve_task(self, run_id: int, task_id: int, decision: str) -> ReviewDecisionRead:
        resp = self._client.post(
            f"/runs/{run_id}/tasks/{task_id}/resolve", json={"decision": decision},
        )
        self._raise_for_status(resp)
        return ReviewDecisionRead.model_validate(resp.json())

    def list_locks(self, run_id: int) -> DecisionLockList:
        resp = self._client.get(f"/runs/{run_id}/locks")
        self._raise_for_status(resp)
        return DecisionLockList.model_validate(resp.json())

    def supersede_lock(self, run_id: int, lock_id: int, reason: str) -> DecisionLockRead:
        resp = self._client.post(
            f"/runs/{run_id}/locks/{lock_id}/supersede", json={"reason": reason},
        )
        self._raise_for_status(resp)
        return DecisionLockRead.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Payroll
    # ------------------------------------------------------------------

    def get_payroll_validation(self, run_id: int) -> PayrollValidationResponse:
        resp = self._client.get(f"/runs/{run_id}/payroll-validation")
        self._raise_for_status(resp)
        return PayrollValidationResponse.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Ledger
    # ------------------------------------------------------------------

    def get_ledger_summary(self, run_id: int) -> LedgerSummaryResponse:
        resp = self._client.get(f"/runs/{run_id}/ledger")
        self._raise_for_status(resp)
        return LedgerSummaryResponse.model_validate(resp.json())

    # ------------------------------------------------------------------
    # CSV Tools
    # ------------------------------------------------------------------

    def csv_profile(self, run_id: int, file_id: int) -> CSVProfileResponse:
        resp = self._client.get(f"/runs/{run_id}/files/{file_id}/csv/profile")
        self._raise_for_status(resp)
        return CSVProfileResponse.model_validate(resp.json())

    def csv_query(self, run_id: int, file_id: int, sql: str) -> CSVQueryResponse:
        resp = self._client.post(
            f"/runs/{run_id}/files/{file_id}/csv/query", json={"sql": sql},
        )
        self._raise_for_status(resp)
        return CSVQueryResponse.model_validate(resp.json())

    def csv_list_proposals(self, run_id: int, file_id: int) -> MappingProposalList:
        resp = self._client.get(f"/runs/{run_id}/files/{file_id}/csv/proposals")
        self._raise_for_status(resp)
        return MappingProposalList.model_validate(resp.json())

    def csv_generate_proposals(self, run_id: int, file_id: int) -> MappingProposalList:
        resp = self._client.post(f"/runs/{run_id}/files/{file_id}/csv/proposals/generate")
        self._raise_for_status(resp)
        return MappingProposalList.model_validate(resp.json())

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict:
        resp = self._client.get("/health")
        self._raise_for_status(resp)
        return resp.json()


# ------------------------------------------------------------------
# Streamlit helper — one client per session
# ------------------------------------------------------------------

def get_client() -> SREDClient:
    """Return a cached ``SREDClient`` for the current Streamlit session."""
    if "sred_api_client" not in st.session_state:
        base_url = st.session_state.get("sred_api_url", _DEFAULT_BASE_URL)
        st.session_state["sred_api_client"] = SREDClient(base_url=base_url)
    return st.session_state["sred_api_client"]
