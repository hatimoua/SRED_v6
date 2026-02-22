"""Tasks & Gates DTOs — pure Pydantic, zero ORM imports."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel


# --- Contradiction DTOs ---

class ContradictionSeverityDTO(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKING = "BLOCKING"


class ContradictionTypeDTO(str, Enum):
    MISSING_RATE = "MISSING_RATE"
    PAYROLL_MISMATCH = "PAYROLL_MISMATCH"
    UNKNOWN_BASIS = "UNKNOWN_BASIS"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    OTHER = "OTHER"


class ContradictionStatusDTO(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class ContradictionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    run_id: int
    issue_key: str
    contradiction_type: ContradictionTypeDTO
    severity: ContradictionSeverityDTO
    description: str
    status: ContradictionStatusDTO
    related_entity_type: str | None = None
    related_entity_id: int | None = None
    created_at: datetime | None = None


class ContradictionList(BaseModel):
    items: list[ContradictionRead]
    total: int


# --- ReviewTask DTOs ---

class ReviewTaskStatusDTO(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    SUPERSEDED = "SUPERSEDED"


class ReviewTaskRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    run_id: int
    issue_key: str
    title: str
    description: str
    severity: ContradictionSeverityDTO
    status: ReviewTaskStatusDTO
    contradiction_id: int | None = None
    created_at: datetime | None = None


class ReviewTaskList(BaseModel):
    items: list[ReviewTaskRead]
    total: int


# --- ReviewDecision DTOs ---

class ReviewDecisionCreate(BaseModel):
    decision: str


class ReviewDecisionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    run_id: int
    task_id: int
    decision: str
    decided_by: str
    created_at: datetime | None = None


# --- DecisionLock DTOs ---

class DecisionLockRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    run_id: int
    issue_key: str
    decision_id: int
    reason: str
    active: bool
    created_at: datetime | None = None


class DecisionLockList(BaseModel):
    items: list[DecisionLockRead]
    total: int


class SupersedeRequest(BaseModel):
    reason: str


# --- Gate status ---

class GateStatusResponse(BaseModel):
    run_status: str
    blocking_contradictions: int
    blocking_tasks: int


# --- Resolve task (creates decision + lock + resolves task + contradiction) ---

class ResolveTaskRequest(BaseModel):
    decision: str
