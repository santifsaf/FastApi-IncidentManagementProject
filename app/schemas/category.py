from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.category import TeamAssignmentStrategy


class TicketCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    auto_team_assignment_enabled: bool = False
    team_assignment_delay_minutes: int = Field(default=0, ge=0)
    team_assignment_strategy: TeamAssignmentStrategy = TeamAssignmentStrategy.LEAST_LOAD_PER_MEMBER


class TicketCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str] = None
    is_active: bool
    auto_team_assignment_enabled: bool
    team_assignment_delay_minutes: int
    team_assignment_strategy: TeamAssignmentStrategy
    created_at: datetime


class CategoryTeamAssignmentUpdate(BaseModel):
    auto_team_assignment_enabled: bool
    team_assignment_delay_minutes: int = Field(ge=0)
    team_assignment_strategy: TeamAssignmentStrategy


class CategoryTeamCreate(BaseModel):
    team_id: UUID


class CategoryTeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    team_id: UUID
    created_at: datetime
