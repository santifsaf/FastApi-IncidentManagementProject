from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.ticket import TicketCommentVisibility, TicketPriority, TicketStatus

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
    closed_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    archived_by: Optional[UUID] = None
    archive_reason: Optional[str] = None


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


class TicketCategoryUpdate(BaseModel):
    category_id: UUID
    reason: str


class TicketDependencyCreate(BaseModel):
    depends_on_ticket_id: UUID
    reason: Optional[str] = None


class TicketDependencyRemove(BaseModel):
    reason: str


class TicketArchiveUpdate(BaseModel):
    reason: str


class BlockingTicketCreate(BaseModel):
    title: str
    description: str
    category_id: UUID
    priority: TicketPriority = TicketPriority.MEDIUM
    reason: str


class TicketAssignmentHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_assigned_to: Optional[UUID] = None
    new_assigned_to: Optional[UUID] = None
    changed_by: UUID
    changed_at: datetime


class TicketTeamHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_team_id: Optional[UUID] = None
    new_team_id: Optional[UUID] = None
    changed_by: UUID
    changed_at: datetime


class TicketCategoryHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    old_category_id: UUID
    new_category_id: UUID
    reason: str
    changed_by: UUID
    changed_at: datetime


class TicketDependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID
    depends_on_ticket_id: UUID
    reason: Optional[str] = None
    created_by: UUID
    created_at: datetime
    is_active: bool
    removed_by: Optional[UUID] = None
    removed_at: Optional[datetime] = None
    removed_reason: Optional[str] = None


class BlockingTicketRead(BaseModel):
    current_ticket: TicketRead
    blocking_ticket: TicketRead
    dependency: TicketDependencyRead


# SCHEMAS DE COMENTARIOS
class TicketCommentCreate(BaseModel):
    body: str
    # Es obligatorio para no publicar accidentalmente una nota interna.
    visibility: TicketCommentVisibility


class TicketCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_id: UUID
    author_id: UUID
    body: str
    visibility: TicketCommentVisibility
    created_at: datetime
