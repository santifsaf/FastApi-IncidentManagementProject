from datetime import datetime
from enum import Enum
import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Enum as SqlEnum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.category import TeamAssignmentStrategy
from app.models.team import AssignmentStrategy


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


class TicketCommentVisibility(str, Enum):
    # Equivale a una respuesta publica de Jira: el solicitante puede leerla.
    REQUESTER_VISIBLE = "REQUESTER_VISIBLE"
    # Equivale a una nota interna de Jira: queda dentro del equipo operativo.
    INTERNAL = "INTERNAL"


class AssignmentSource(str, Enum):
    """Origen humano o automático de un cambio de asignación."""

    MANUAL = "MANUAL"
    CLAIM = "CLAIM"
    AUTOMATIC = "AUTOMATIC"


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        # Un responsable siempre trabaja dentro del equipo asignado al ticket.
        CheckConstraint(
            "assigned_to IS NULL OR team_id IS NOT NULL",
            name="ck_tickets_assigned_requires_team",
        ),
    )

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
    team_queue_entered_at = Column(DateTime(timezone=True), nullable=True)
    team_assignment_due_at = Column(DateTime(timezone=True), nullable=True)
    team_assignment_strategy = Column(
        SqlEnum(TeamAssignmentStrategy, name="teamassignmentstrategy"),
        nullable=True,
    )
    auto_assignment_due_at = Column(DateTime(timezone=True), nullable=True)
    auto_assignment_strategy = Column(
        SqlEnum(AssignmentStrategy, name="assignmentstrategy"),
        nullable=True,
    )

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
    comments = relationship(
        "TicketComment",
        back_populates="ticket",
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TicketComment(Base):
    """Mensaje publico para el solicitante o nota interna del equipo."""

    __tablename__ = "ticket_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False, index=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    visibility = Column(
        SqlEnum(TicketCommentVisibility, name="ticketcommentvisibility"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    ticket = relationship("Ticket", back_populates="comments")
    author = relationship("User", back_populates="authored_ticket_comments")


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
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    source = Column(
        SqlEnum(AssignmentSource, name="assignmentsource"),
        default=AssignmentSource.MANUAL,
        nullable=False,
    )

    # La base define el timestamp para evitar datetimes sin timezone en Python.
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketTeamHistory(Base):
    __tablename__ = "ticket_team_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)

    # Puede ser NULL cuando el ticket pasa de no tener equipo a tener uno.
    old_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    new_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)

    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    source = Column(
        SqlEnum(AssignmentSource, name="assignmentsource"),
        default=AssignmentSource.MANUAL,
        nullable=False,
    )
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
