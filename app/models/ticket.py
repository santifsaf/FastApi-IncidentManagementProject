from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum as SqlEnum, ForeignKey, Index, String, Text, func
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
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Archivado administrativo: no cambia el status, solo oculta el ticket de
    # listados operativos normales sin perderlo de la base.
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archived_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    archive_reason = Column(Text, nullable=True)

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


class TicketTeamHistory(Base):
    __tablename__ = "ticket_team_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)

    # Puede ser NULL cuando el ticket pasa de no tener equipo a tener uno.
    old_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    new_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)

    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketCategoryHistory(Base):
    __tablename__ = "ticket_category_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)

    old_category_id = Column(UUID(as_uuid=True), ForeignKey("ticket_categories.id"), nullable=False)
    new_category_id = Column(UUID(as_uuid=True), ForeignKey("ticket_categories.id"), nullable=False)

    # Cambiar categoria puede cambiar el equipo responsable, por eso exigimos motivo.
    reason = Column(Text, nullable=False)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketDependency(Base):
    __tablename__ = "ticket_dependencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ticket_id es el ticket que queda bloqueado.
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)

    # depends_on_ticket_id es el ticket que debe resolverse antes.
    depends_on_ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)

    reason = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Soft delete: la dependencia queda registrada, pero deja de bloquear.
    is_active = Column(Boolean, default=True, nullable=False)
    removed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    removed_at = Column(DateTime(timezone=True), nullable=True)
    removed_reason = Column(Text, nullable=True)


Index(
    "uq_ticket_dependencies_active_pair",
    TicketDependency.ticket_id,
    TicketDependency.depends_on_ticket_id,
    unique=True,
    postgresql_where=TicketDependency.is_active.is_(True),
)
