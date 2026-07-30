from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TeamCreate(BaseModel):
    name: str
    lead_id: UUID


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    lead_id: UUID
    created_at: datetime


class TeamMemberCreate(BaseModel):
    user_id: UUID


class TeamMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    user_id: UUID
    created_at: datetime
