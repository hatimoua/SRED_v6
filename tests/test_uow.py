"""Unit tests for the UnitOfWork context manager."""
import pytest
from sqlmodel import Session, select
from sred.models.core import Run
from sred.infra.db.uow import UnitOfWork


def test_commit_persists_record(use_test_engine):
    with UnitOfWork() as uow:
        run = Run(name="Committed Run")
        uow.session.add(run)
        uow.commit()
        run_id = run.id

    # Verify in a separate session
    with Session(use_test_engine) as s:
        fetched = s.get(Run, run_id)
        assert fetched is not None
        assert fetched.name == "Committed Run"


def test_rollback_on_exception_reverts_record(use_test_engine):
    with Session(use_test_engine) as s:
        count_before = len(s.exec(select(Run)).all())

    try:
        with UnitOfWork() as uow:
            run = Run(name="Will Be Rolled Back")
            uow.session.add(run)
            uow.session.flush()  # write to DB within transaction
            raise ValueError("forced error")
    except ValueError:
        pass

    # Record must not have been persisted
    with Session(use_test_engine) as s:
        count_after = len(s.exec(select(Run)).all())

    assert count_after == count_before
