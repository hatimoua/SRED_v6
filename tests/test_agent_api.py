"""Integration tests for /runs/{run_id}/agent/message."""

from __future__ import annotations

from sqlalchemy import text
from sqlmodel import Session

from sred.config import settings
from sred.models.core import File, Run, Segment
from sred.models.world import ContradictionSeverity, ReviewTask, ReviewTaskStatus
from sred.orchestration.state import PlannerDecision


class RecordingDoneLLM:
    """Deterministic planner response with call metadata for assertions."""

    message_lengths: list[int] = []

    def chat_completions_create(
        self,
        *,
        model: str,
        messages: list[dict],
        response_format: dict | None = None,
    ) -> str:
        RecordingDoneLLM.message_lengths.append(len(messages))
        call_number = len(RecordingDoneLLM.message_lengths)
        return PlannerDecision(
            done=True,
            stop_reason="complete",
            draft_response=f"Reply {call_number}",
            reasoning="done",
        ).model_dump_json()


def _seed_run_with_searchable_segment(session: Session) -> int:
    run = Run(name="Agent API Run")
    session.add(run)
    session.flush()

    file_obj = File(
        run_id=run.id,
        path=f"data/runs/{run.id}/uploads/evidence.txt",
        original_filename="evidence.txt",
        file_type="text/plain",
        mime_type="text/plain",
        size_bytes=64,
        content_hash="abc123",
    )
    session.add(file_obj)
    session.flush()

    seg = Segment(
        run_id=run.id,
        file_id=file_obj.id,
        content="alpha evidence for salary allocation and qualifying work",
    )
    session.add(seg)
    session.flush()
    session.exec(
        text(
            "INSERT INTO segment_fts(rowid, id, content) VALUES (:rowid, :id, :content)"
        ),
        params={"rowid": seg.id, "id": seg.id, "content": seg.content},
    )
    session.commit()
    return run.id


def test_agent_message_resumes_same_session_id_and_returns_citations(
    client, use_test_engine, monkeypatch, tmp_path,
):
    RecordingDoneLLM.message_lengths = []
    monkeypatch.setattr(
        "sred.services.agent_service.OpenAILLMClient",
        lambda: RecordingDoneLLM(),
    )
    monkeypatch.setattr(settings, "checkpoint_db", tmp_path / "agent_checkpoints.db", raising=False)

    with Session(use_test_engine) as session:
        run_id = _seed_run_with_searchable_segment(session)

    first = client.post(
        f"/runs/{run_id}/agent/message",
        json={"session_id": "sess-1", "message": "alpha evidence"},
    )
    assert first.status_code == 200
    body_1 = first.json()
    assert body_1["status"] == "OK"
    assert body_1["message"] == "Reply 1"
    assert isinstance(body_1["next_actions"], list)
    assert body_1["references"]
    assert body_1["citations"]

    second = client.post(
        f"/runs/{run_id}/agent/message",
        json={"session_id": "sess-1", "message": "continue"},
    )
    assert second.status_code == 200
    body_2 = second.json()
    assert body_2["status"] == "OK"
    assert body_2["message"] == "Reply 2"

    # Same session_id resumes thread state; second planner call sees prior assistant message.
    assert RecordingDoneLLM.message_lengths[:2] == [2, 3]


def test_agent_message_returns_needs_review_with_next_actions(
    client, use_test_engine, monkeypatch, tmp_path,
):
    monkeypatch.setattr(
        "sred.services.agent_service.OpenAILLMClient",
        lambda: RecordingDoneLLM(),
    )
    monkeypatch.setattr(settings, "checkpoint_db", tmp_path / "agent_checkpoints_blocked.db", raising=False)

    with Session(use_test_engine) as session:
        run = Run(name="Blocked Run")
        session.add(run)
        session.flush()
        session.add(
            ReviewTask(
                run_id=run.id,
                issue_key=f"TASK:{run.id}:1",
                title="Resolve blocker",
                description="Blocking task for endpoint test",
                severity=ContradictionSeverity.BLOCKING,
                status=ReviewTaskStatus.OPEN,
            )
        )
        session.commit()
        run_id = run.id

    response = client.post(
        f"/runs/{run_id}/agent/message",
        json={"session_id": "blocked-1", "message": "finish"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NEEDS_REVIEW"
    assert body["next_actions"]
    assert any(action["action"] == "RESOLVE_TASK" for action in body["next_actions"])
