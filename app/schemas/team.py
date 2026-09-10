from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TeamCreate(BaseModel):
    name: str
    lead_id: UUID
    self_assignment_enabled: bool = False


class TeamSelfAssignmentUpdate(BaseModel):
    self_assignment_enabled: bool


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    self_assignment_enabled: bool
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
