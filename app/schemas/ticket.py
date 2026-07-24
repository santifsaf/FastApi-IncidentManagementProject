from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.ticket import TicketPriority, TicketStatus

#SCHEMAS GLOBALES DE TICKET
class TicketCreate(BaseModel):
    title: str
    description: str
    priority: TicketPriority = TicketPriority.MEDIUM


class TicketRead(BaseModel):
    id: UUID
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    created_by: UUID
    assigned_to: Optional[UUID] = None

    class Config:
        from_attributes = True


#SCHEMAS DEL ESTADO DEL TICKET
class UpdateTicketStatus(BaseModel):
    status: TicketStatus

class TicketStatusHistoryRead(BaseModel):
    old_status: TicketStatus
    new_status: TicketStatus
    changed_by: UUID
    changed_at: datetime

    class Config:
        from_attributes = True


#SCHEMAS DE ASIGNACION
class TicketAssignmentUpdate(BaseModel):
    assigned_to:UUID 

class TicketAssignmentHistoryRead(BaseModel):
    old_assigned_to: Optional[UUID] = None
    new_assigned_to: Optional[UUID] = None
    changed_by: UUID
    changed_at: datetime

    class Config:
        from_attributes = True
