from typing import Optional
from uuid import UUID

from pydantic import BaseModel
from app.models.ticket import TicketStatus


class TicketCreate(BaseModel):
    title: str
    description: str
    priority: str = "MEDIUM"


class TicketRead(BaseModel):
    id: UUID
    title: str
    description: str
    status: str
    priority: str
    created_by: UUID
    assigned_to: Optional[UUID] = None

    class Config:
        from_attributes = True

class UpdateTicketStatus(BaseModel):
    status: TicketStatus