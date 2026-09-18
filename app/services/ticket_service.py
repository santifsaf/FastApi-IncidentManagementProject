"""Creacion y consultas principales de tickets.

Las operaciones especializadas viven en services separados para que este
modulo conserve una responsabilidad pequena y facil de reconocer.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.ticket_rules import can_user_view_ticket
from app.models.category import TicketCategory
from app.models.team import TeamMember
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCreate
from app.services.assignment_timing import calculate_assignment_due_at
from app.services.team_queries import is_team_member
from app.services.ticket_exceptions import (
    InvalidTicketCategoryError,
    TicketCategoryNotFoundError,
    TicketNotFoundError,
    TicketPermissionError,
)
from app.services.ticket_service_utils import commit_and_refresh


def create_ticket_service(db: Session, ticket_in: TicketCreate, current_user: User) -> Ticket:
    """Crea un ticket abierto dentro de una categoria activa."""

    category = db.query(TicketCategory).filter(TicketCategory.id == ticket_in.category_id).first()
    if category is None:
        raise TicketCategoryNotFoundError("Category not found")
    if not category.is_active:
        raise InvalidTicketCategoryError("Inactive categories cannot be used for new tickets")

    now = datetime.now(timezone.utc)
    new_ticket = Ticket(
        title=ticket_in.title,
        description=ticket_in.description,
        status=TicketStatus.OPEN,
        priority=ticket_in.priority,
        created_by=current_user.id,
        category_id=category.id,
        team_queue_entered_at=now,
        team_assignment_due_at=calculate_assignment_due_at(
            category.auto_team_assignment_enabled,
            category.team_assignment_delay_minutes,
            now=now,
        ),
        team_assignment_strategy=(
            category.team_assignment_strategy
            if category.auto_team_assignment_enabled
            else None
        ),
    )
    db.add(new_ticket)
    return commit_and_refresh(db, new_ticket)


def get_tickets_created_by_user(
    db: Session,
    current_user: User,
    skip: int,
    limit: int,
) -> list[Ticket]:
    """Lista tickets creados por el usuario autenticado."""

    return (
        db.query(Ticket)
        .filter(Ticket.created_by == current_user.id, Ticket.archived_at.is_(None))
        .order_by(Ticket.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_tickets_assigned_to_user(
    db: Session,
    current_user: User,
    skip: int,
    limit: int,
) -> list[Ticket]:
    """Lista los tickets donde el usuario es responsable directo."""

    if current_user.role not in {UserRole.AGENT, UserRole.ADMIN}:
        raise TicketPermissionError("Not enough permissions")

    return (
        db.query(Ticket)
        .filter(Ticket.assigned_to == current_user.id, Ticket.archived_at.is_(None))
        .order_by(Ticket.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_visible_tickets(
    db: Session,
    current_user: User,
    skip: int,
    limit: int,
) -> list[Ticket]:
    """Lista la cola operativa respetando el alcance del usuario."""

    if current_user.role not in {UserRole.AGENT, UserRole.ADMIN}:
        raise TicketPermissionError("Not enough permissions")

    query = db.query(Ticket).filter(Ticket.archived_at.is_(None)).order_by(Ticket.created_at.desc())
    if current_user.role == UserRole.AGENT:
        team_ids = select(TeamMember.team_id).where(TeamMember.user_id == current_user.id)
        query = query.filter(
            or_(
                Ticket.assigned_to == current_user.id,
                Ticket.team_id.in_(team_ids),
            )
        )

    return query.offset(skip).limit(limit).all()


def get_ticket_detail(db: Session, ticket_id: UUID, current_user: User) -> Ticket:
    """Devuelve un ticket puntual si el usuario puede consultar el recurso."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    current_user_is_team_member = False
    if current_user.role == UserRole.AGENT and ticket.team_id is not None:
        current_user_is_team_member = is_team_member(db, ticket.team_id, current_user.id)

    if not can_user_view_ticket(current_user, ticket, current_user_is_team_member):
        raise TicketPermissionError("Not enough permissions to view ticket")

    return ticket
