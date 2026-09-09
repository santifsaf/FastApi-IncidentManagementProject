"""Casos de uso que modifican el estado operativo de un ticket."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.ticket_rules import (
    can_user_change_status,
    can_user_view_status_history,
    is_status_change_reason_required,
    is_valid_status_transition,
)
from app.models.ticket import Ticket, TicketDependency, TicketStatus, TicketStatusHistory
from app.models.user import User, UserRole
from app.services.team_queries import is_team_member
from app.services.ticket_exceptions import (
    InvalidStatusTransitionError,
    MissingStatusChangeReasonError,
    TicketArchiveError,
    TicketBlockedByOpenDependenciesError,
    TicketNotFoundError,
    TicketPermissionError,
)
from app.services.ticket_service_utils import commit_and_refresh, normalize_optional_reason


def _ticket_has_open_dependencies(db: Session, ticket_id: UUID) -> bool:
    """Indica si otro ticket todavia impide resolver el ticket actual."""

    return (
        db.query(TicketDependency.id)
        .join(Ticket, Ticket.id == TicketDependency.depends_on_ticket_id)
        .filter(
            TicketDependency.ticket_id == ticket_id,
            TicketDependency.is_active.is_(True),
            Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED]),
        )
        .first()
        is not None
    )


def change_ticket_status(
    db: Session,
    ticket_id: UUID,
    new_status: TicketStatus,
    user: User,
    reason: str | None = None,
) -> Ticket:
    """Busca el ticket y ejecuta el cambio de estado completo."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    # El service revalida permisos y transiciones para no depender solo del router.
    if not can_user_change_status(user, ticket, new_status):
        raise TicketPermissionError("Not enough permissions to change ticket status")

    if not is_valid_status_transition(ticket.status, new_status):
        raise InvalidStatusTransitionError("Invalid transition")

    if new_status == TicketStatus.RESOLVED and _ticket_has_open_dependencies(db, ticket.id):
        raise TicketBlockedByOpenDependenciesError("Ticket has open dependencies")

    normalized_reason = reason.strip() if reason else None
    if is_status_change_reason_required(ticket.status, new_status) and not normalized_reason:
        raise MissingStatusChangeReasonError("Reason is required for this status change")

    old_status = ticket.status
    ticket.status = new_status
    if new_status == TicketStatus.CLOSED:
        ticket.closed_at = func.now()

    db.add(
        TicketStatusHistory(
            ticket_id=ticket.id,
            old_status=old_status,
            new_status=new_status,
            reason=normalized_reason,
            changed_by=user.id,
        )
    )

    return commit_and_refresh(db, ticket)


def archive_ticket(db: Session, ticket_id: UUID, current_user: User, reason: str | None) -> Ticket:
    """Archiva un ticket cerrado sin cambiar su status."""

    if current_user.role != UserRole.ADMIN:
        raise TicketPermissionError("Only admins can archive tickets")

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    if ticket.archived_at is not None:
        raise TicketArchiveError("Ticket already archived")

    if ticket.status != TicketStatus.CLOSED:
        raise TicketArchiveError("Only closed tickets can be archived")

    normalized_reason = normalize_optional_reason(reason)
    if not normalized_reason:
        raise TicketArchiveError("Reason is required to archive ticket")

    ticket.archived_at = func.now()
    ticket.archived_by = current_user.id
    ticket.archive_reason = normalized_reason

    return commit_and_refresh(db, ticket)


def unarchive_ticket(db: Session, ticket_id: UUID, current_user: User) -> Ticket:
    """Vuelve visible un ticket archivado sin reabrirlo."""

    if current_user.role != UserRole.ADMIN:
        raise TicketPermissionError("Only admins can unarchive tickets")

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    if ticket.archived_at is None:
        raise TicketArchiveError("Ticket is not archived")

    ticket.archived_at = None
    ticket.archived_by = None
    ticket.archive_reason = None

    return commit_and_refresh(db, ticket)


def archive_old_closed_tickets(db: Session, days: int = 30) -> int:
    """Archiva tickets cerrados que superaron la antiguedad configurada."""

    if days <= 0:
        raise TicketArchiveError("Days must be greater than zero")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    tickets = (
        db.query(Ticket)
        .filter(
            Ticket.status == TicketStatus.CLOSED,
            Ticket.closed_at.is_not(None),
            Ticket.closed_at <= cutoff,
            Ticket.archived_at.is_(None),
        )
        .all()
    )

    for ticket in tickets:
        ticket.archived_at = func.now()
        ticket.archived_by = None
        ticket.archive_reason = f"Archivado automaticamente luego de {days} dias cerrado"

    try:
        db.commit()
        return len(tickets)
    except Exception:
        db.rollback()
        raise


def get_ticket_status_history_service(
    db: Session,
    ticket_id: UUID,
    current_user: User,
) -> list[TicketStatusHistory]:
    """Devuelve el historial de estado aplicando permisos de lectura."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    current_user_is_team_member = is_team_member(db, ticket.team_id, current_user.id)
    if not can_user_view_status_history(current_user, ticket, current_user_is_team_member):
        raise TicketPermissionError("Not enough permissions to view ticket status history")

    return (
        db.query(TicketStatusHistory)
        .filter(TicketStatusHistory.ticket_id == ticket_id)
        .order_by(TicketStatusHistory.changed_at.desc())
        .all()
    )
