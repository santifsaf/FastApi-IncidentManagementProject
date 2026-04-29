from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy import Column, DateTime, Enum as SqlEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"))

    # Conserva una auditoría básica de cada cambio de estado.
    old_status = Column(SqlEnum(TicketStatus))
    new_status = Column(SqlEnum(TicketStatus))

    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    changed_at = Column(DateTime, default=datetime.utcnow)
