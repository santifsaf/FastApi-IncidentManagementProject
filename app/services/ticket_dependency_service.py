"""Casos de uso para dependencias y tickets bloqueantes."""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.ticket_rules import can_user_view_assignment_history
from app.models.category import TicketCategory
from app.models.ticket import Ticket, TicketDependency, TicketStatus, TicketStatusHistory
from app.models.user import User, UserRole
from app.services.team_queries import is_team_lead, is_team_member
from app.services.ticket_exceptions import (
    InvalidTicketCategoryError,
    MissingStatusChangeReasonError,
    TicketCategoryNotFoundError,
    TicketDependencyError,
    TicketDependencyNotFoundError,
    TicketNotFoundError,
    TicketPermissionError,
)
from app.services.ticket_service_utils import commit_and_refresh, normalize_optional_reason


def _can_user_manage_ticket_dependencies(db: Session, ticket: Ticket, current_user: User) -> bool:
    if current_user.role == UserRole.ADMIN:
        return True
    if current_user.role != UserRole.AGENT or ticket.team_id is None:
        return False
    return is_team_lead(db, ticket.team_id, current_user.id)


def _create_ticket_dependency(
    db: Session,
    ticket: Ticket,
    depends_on_ticket: Ticket,
    current_user: User,
    reason: str | None = None,
) -> TicketDependency:
    """Construye y agrega una dependencia dentro de la transaccion actual."""

    if ticket.id == depends_on_ticket.id:
        raise TicketDependencyError("A ticket cannot depend on itself")
    if ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise TicketDependencyError("Resolved or closed tickets cannot receive new dependencies")
    if depends_on_ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise TicketDependencyError("A ticket cannot depend on a resolved or closed ticket")

    existing_dependency = (
        db.query(TicketDependency.id)
        .filter(
            TicketDependency.ticket_id == ticket.id,
            TicketDependency.depends_on_ticket_id == depends_on_ticket.id,
            TicketDependency.is_active.is_(True),
        )
        .first()
    )
    if existing_dependency:
        raise TicketDependencyError("Dependency already exists")

    reverse_dependency = (
        db.query(TicketDependency.id)
        .filter(
            TicketDependency.ticket_id == depends_on_ticket.id,
            TicketDependency.depends_on_ticket_id == ticket.id,
            TicketDependency.is_active.is_(True),
        )
        .first()
    )
    if reverse_dependency:
        raise TicketDependencyError("Circular dependency is not allowed")

    dependency = TicketDependency(
        ticket_id=ticket.id,
        depends_on_ticket_id=depends_on_ticket.id,
        reason=normalize_optional_reason(reason),
        created_by=current_user.id,
    )
    db.add(dependency)
    return dependency


def add_ticket_dependency(
    db: Session,
    ticket_id: UUID,
    depends_on_ticket_id: UUID,
    current_user: User,
    reason: str | None = None,
) -> TicketDependency:
    """Vincula el ticket actual con otro ticket existente que lo bloquea."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    depends_on_ticket = db.query(Ticket).filter(Ticket.id == depends_on_ticket_id).first()
    if depends_on_ticket is None:
        raise TicketDependencyNotFoundError("Blocking ticket not found")

    if not _can_user_manage_ticket_dependencies(db, ticket, current_user):
        raise TicketPermissionError("Not enough permissions to manage ticket dependencies")

    dependency = _create_ticket_dependency(db, ticket, depends_on_ticket, current_user, reason)
    return commit_and_refresh(db, dependency)


def get_ticket_dependencies_service(
    db: Session, ticket_id: UUID, current_user: User
) -> list[TicketDependency]:
    """Lista los tickets de los que depende el ticket actual."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    current_user_is_member = is_team_member(db, ticket.team_id, current_user.id)
    if not can_user_view_assignment_history(current_user, ticket, current_user_is_member):
        raise TicketPermissionError("Not enough permissions to view ticket dependencies")

    return (
        db.query(TicketDependency)
        .filter(TicketDependency.ticket_id == ticket.id, TicketDependency.is_active.is_(True))
        .order_by(TicketDependency.created_at.desc())
        .all()
    )


def get_blocked_tickets_service(db: Session, ticket_id: UUID, current_user: User) -> list[Ticket]:
    """Lista los tickets que siguen bloqueados por el ticket actual."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    current_user_is_member = is_team_member(db, ticket.team_id, current_user.id)
    if not can_user_view_assignment_history(current_user, ticket, current_user_is_member):
        raise TicketPermissionError("Not enough permissions to view blocked tickets")

    return (
        db.query(Ticket)
        .join(TicketDependency, TicketDependency.ticket_id == Ticket.id)
        .filter(
            TicketDependency.depends_on_ticket_id == ticket.id,
            TicketDependency.is_active.is_(True),
            Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED]),
        )
        .order_by(Ticket.created_at.desc())
        .all()
    )


def remove_ticket_dependency(
    db: Session,
    ticket_id: UUID,
    dependency_id: UUID,
    current_user: User,
    reason: str | None,
) -> TicketDependency:
    """Desactiva una dependencia y conserva el evento para auditoria."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")
    if not _can_user_manage_ticket_dependencies(db, ticket, current_user):
        raise TicketPermissionError("Not enough permissions to manage ticket dependencies")

    dependency = (
        db.query(TicketDependency)
        .filter(
            TicketDependency.id == dependency_id,
            TicketDependency.ticket_id == ticket.id,
            TicketDependency.is_active.is_(True),
        )
        .first()
    )
    if dependency is None:
        raise TicketDependencyNotFoundError("Dependency not found")

    normalized_reason = normalize_optional_reason(reason)
    if not normalized_reason:
        raise TicketDependencyError("Reason is required to remove dependency")

    dependency.is_active = False
    dependency.removed_by = current_user.id
    dependency.removed_at = func.now()
    dependency.removed_reason = normalized_reason
    return commit_and_refresh(db, dependency)


def create_blocking_ticket(db: Session, ticket_id: UUID, blocking_ticket_in, current_user: User) -> dict:
    """Crea ticket, dependencia y ON_HOLD dentro de una sola transaccion."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")
    if not _can_user_manage_ticket_dependencies(db, ticket, current_user):
        raise TicketPermissionError("Not enough permissions to manage ticket dependencies")

    normalized_reason = normalize_optional_reason(blocking_ticket_in.reason)
    if not normalized_reason:
        raise MissingStatusChangeReasonError("Reason is required to create a blocking ticket")

    category = db.query(TicketCategory).filter(TicketCategory.id == blocking_ticket_in.category_id).first()
    if category is None:
        raise TicketCategoryNotFoundError("Category not found")
    if not category.is_active:
        raise InvalidTicketCategoryError("Inactive categories cannot be used for new tickets")

    blocking_ticket = Ticket(
        title=blocking_ticket_in.title,
        description=blocking_ticket_in.description,
        status=TicketStatus.OPEN,
        priority=blocking_ticket_in.priority,
        created_by=current_user.id,
        category_id=category.id,
    )
    db.add(blocking_ticket)
    # flush obtiene el UUID sin confirmar; un rollback posterior revierte todo.
    db.flush()

    dependency = _create_ticket_dependency(db, ticket, blocking_ticket, current_user, normalized_reason)

    if ticket.status != TicketStatus.ON_HOLD:
        old_status = ticket.status
        ticket.status = TicketStatus.ON_HOLD
        db.add(
            TicketStatusHistory(
                ticket_id=ticket.id,
                old_status=old_status,
                new_status=TicketStatus.ON_HOLD,
                reason=normalized_reason,
                changed_by=current_user.id,
            )
        )

    try:
        db.commit()
        db.refresh(ticket)
        db.refresh(blocking_ticket)
        db.refresh(dependency)
        return {
            "current_ticket": ticket,
            "blocking_ticket": blocking_ticket,
            "dependency": dependency,
        }
    except Exception:
        db.rollback()
        raise
