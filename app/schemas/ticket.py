from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.ticket import TicketPriority, TicketStatus

#SCHEMAS GLOBALES DE TICKET
class TicketCreate(BaseModel):
    title: str
    description: str
    category_id: UUID
    priority: TicketPriority = TicketPriority.MEDIUM


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    created_by: UUID
    assigned_to: Optional[UUID] = None
    team_id: Optional[UUID] = None
    category_id: UUID


#SCHEMAS DEL ESTADO DEL TICKET
class UpdateTicketStatus(BaseModel):
    status: TicketStatus
    reason: Optional[str] = None

class TicketStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_status: TicketStatus
    new_status: TicketStatus
    reason: Optional[str] = None
    changed_by: UUID
    changed_at: datetime


#SCHEMAS DE ASIGNACION
class TicketAssignmentUpdate(BaseModel):
    assigned_to:UUID 


class TicketTeamAssignmentUpdate(BaseModel):
    team_id: UUID

class TicketAssignmentHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_assigned_to: Optional[UUID] = None
    new_assigned_to: Optional[UUID] = None
    changed_by: UUID
    changed_at: datetime
