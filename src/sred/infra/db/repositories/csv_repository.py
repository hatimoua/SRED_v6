"""Repository for CSV-related entities (mapping proposals)."""
from __future__ import annotations
from sqlmodel import Session, select
from sred.models.hypothesis import StagingMappingProposal


class CSVRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_proposals_by_file(self, file_id: int) -> list[StagingMappingProposal]:
        return list(self._s.exec(
            select(StagingMappingProposal).where(StagingMappingProposal.file_id == file_id)
        ).all())
