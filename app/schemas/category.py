from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TicketCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None


class TicketCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime


class CategoryTeamCreate(BaseModel):
    team_id: UUID


class CategoryTeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    team_id: UUID
    created_at: datetime
