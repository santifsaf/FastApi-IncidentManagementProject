from datetime import datetime
import uuid

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from enum import Enum 

from app.db.base import Base

class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

ALLOWED_TRANSITIONS = {
    TicketStatus.OPEN: {TicketStatus.IN_PROGRESS, TicketStatus.ON_HOLD, TicketStatus.RESOLVED},
    TicketStatus.IN_PROGRESS: {TicketStatus.ON_HOLD, TicketStatus.RESOLVED},
    TicketStatus.ON_HOLD: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED},
    TicketStatus.RESOLVED: {TicketStatus.OPEN, TicketStatus.CLOSED},
    TicketStatus.CLOSED: set(),
}

def is_valid_status_transition(current_status: TicketStatus, new_status: TicketStatus) -> bool:
    return new_status in ALLOWED_TRANSITIONS.get(current_status, set())

                                                 
class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(SqlEnum(TicketStatus), default=TicketStatus.OPEN, nullable=False)
    priority = Column(String, nullable=False, default="MEDIUM")

    # Guarda qué usuario creó el ticket para poder filtrar "mis tickets".
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TicketStatusHistory(Base):
    __tablename__ = "ticket_status_history"

    id = Column(UUID, primary_key=True)
    ticket_id = Column(UUID, ForeignKey("tickets.id"))

    old_status = Column(String)
    new_status = Column(String)

    changed_by = Column(UUID, ForeignKey("users.id"))
    changed_at = Column(DateTime, default=datetime.utcnow)
