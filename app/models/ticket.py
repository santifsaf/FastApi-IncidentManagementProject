from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy import Column, DateTime, Enum as SqlEnum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class TicketPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(SqlEnum(TicketStatus), default=TicketStatus.OPEN, nullable=False)
    priority = Column(SqlEnum(TicketPriority), default=TicketPriority.MEDIUM, nullable=False)

    # Guarda qué usuario creó el ticket para poder filtrar "mis tickets".
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("ticket_categories.id"), nullable=False)

    creator = relationship(
        "User",
        foreign_keys=[created_by],
        back_populates="created_tickets",
    )

    assigned_user = relationship(
        "User",
        foreign_keys=[assigned_to],
        back_populates="assigned_tickets",
    )

    team = relationship("Team", back_populates="tickets")
    category = relationship("TicketCategory", back_populates="tickets")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TicketStatusHistory(Base):
    __tablename__ = "ticket_status_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)

    # Conserva una auditoría básica de cada cambio de estado.
    old_status = Column(SqlEnum(TicketStatus), nullable=False)
    new_status = Column(SqlEnum(TicketStatus), nullable=False)
    reason = Column(Text, nullable=True)

    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # La base define el timestamp para evitar datetimes sin timezone en Python.
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketAssignmentHistory(Base):
    __tablename__ = "ticket_assignment_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)

    # Usuario que tenía asignado el ticket antes del cambio.
    # Puede ser NULL si el ticket todavía no estaba asignado.
    old_assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Usuario que queda asignado después del cambio.
    # Puede ser NULL si en el futuro permitís "desasignar" tickets.
    new_assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Usuario que realizó la acción de asignar o reasignar.
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # La base define el timestamp para evitar datetimes sin timezone en Python.
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
