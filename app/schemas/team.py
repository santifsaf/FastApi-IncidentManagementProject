from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.team import AssignmentStrategy


class TeamCreate(BaseModel):
    name: str
    lead_id: UUID
    self_assignment_enabled: bool = False


class TeamSelfAssignmentUpdate(BaseModel):
    self_assignment_enabled: bool


class TeamAutoAssignmentUpdate(BaseModel):
    auto_assignment_enabled: bool
    auto_assignment_delay_minutes: int = Field(ge=0)
    assignment_strategy: AssignmentStrategy


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    self_assignment_enabled: bool
    auto_assignment_enabled: bool
    auto_assignment_delay_minutes: int
    assignment_strategy: AssignmentStrategy
    created_at: datetime


class TeamMemberCreate(BaseModel):
    user_id: UUID


class TeamMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    user_id: UUID
    created_at: datetime


class TeamLeadCreate(BaseModel):
    user_id: UUID


class TeamLeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    user_id: UUID
    created_at: datetime
