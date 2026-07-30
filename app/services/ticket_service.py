from uuid import UUID

from sqlalchemy.orm import Session

from app.core.ticket_rules import (
    can_user_assign_ticket,
    can_user_change_status,
    is_status_change_reason_required,
    is_valid_status_transition,
)
from app.models.category import TicketCategory
from app.models.team import Team
from app.models.ticket import Ticket, TicketAssignmentHistory, TicketStatus, TicketStatusHistory
from app.models.user import User
from app.schemas.ticket import TicketCreate
from app.services.team_queries import is_team_lead, is_team_member


class TicketServiceError(Exception):
    pass


class TicketNotFoundError(TicketServiceError):
    pass


class AssignedUserNotFoundError(TicketServiceError):
    pass


class TicketPermissionError(TicketServiceError):
    pass


class InvalidStatusTransitionError(TicketServiceError):
    pass


class TicketAlreadyAssignedError(TicketServiceError):
    pass


class MissingStatusChangeReasonError(TicketServiceError):
    pass


class TicketTeamAssignmentError(TicketServiceError):
    pass


class TicketTeamNotFoundError(TicketServiceError):
    pass


class InvalidAssignedUserError(TicketServiceError):
    pass


class TicketCategoryNotFoundError(TicketServiceError):
    pass


class InvalidTicketCategoryError(TicketServiceError):
    pass


def _commit_and_refresh(db: Session, entity):
    try:
        db.commit()
        db.refresh(entity)
        return entity
    except Exception:
        db.rollback()
        raise


def _assign_ticket_to_user(db: Session, ticket: Ticket, new_user_id: UUID, changed_by_id: UUID) -> Ticket:
    old_assigned_to = ticket.assigned_to

    if old_assigned_to == new_user_id:
        raise TicketAlreadyAssignedError("Ticket already assigned to this user")

    ticket.assigned_to = new_user_id

    # El historial forma parte de la asignacion: se guarda en la misma transaccion.
    db.add(
        TicketAssignmentHistory(
            ticket_id=ticket.id,
            old_assigned_to=old_assigned_to,
            new_assigned_to=new_user_id,
            changed_by=changed_by_id,
        )
    )

    return _commit_and_refresh(db, ticket)


def create_ticket_service(db: Session, ticket_in: TicketCreate, current_user: User) -> Ticket:
    category = db.query(TicketCategory).filter(TicketCategory.id == ticket_in.category_id).first()
    if category is None:
        raise TicketCategoryNotFoundError("Category not found")

    if not category.is_active:
        raise InvalidTicketCategoryError("Inactive categories cannot be used for new tickets")

    new_ticket = Ticket(
        title=ticket_in.title,
        description=ticket_in.description,
        status=TicketStatus.OPEN,
        priority=ticket_in.priority,
        created_by=current_user.id,
        category_id=category.id,
    )

    try:
        db.add(new_ticket)
        db.commit()
        db.refresh(new_ticket)
        return new_ticket
    except Exception:
        db.rollback()
        raise


def change_ticket_status(db: Session, ticket: Ticket, new_status: TicketStatus, user: User, reason=None) -> Ticket:
    # El service revalida permisos y transiciones para no depender solo del router.
    if not can_user_change_status(user, ticket, new_status):
        raise TicketPermissionError("Not enough permissions to change ticket status")

    if not is_valid_status_transition(ticket.status, new_status):
        raise InvalidStatusTransitionError("Invalid transition")

    normalized_reason = reason.strip() if reason else None
    if is_status_change_reason_required(ticket.status, new_status) and not normalized_reason:
        raise MissingStatusChangeReasonError("Reason is required for this status change")

    old_status = ticket.status
    ticket.status = new_status

    db.add(
        TicketStatusHistory(
            ticket_id=ticket.id,
            old_status=old_status,
            new_status=new_status,
            reason=normalized_reason,
            changed_by=user.id,
        )
    )

    return _commit_and_refresh(db, ticket)


def assign_ticket_to_team(db: Session, ticket_id: UUID, team_id: UUID) -> Ticket:
    """Asigna un ticket a un equipo sin modificar el agente responsable.

    Si el ticket ya tenia agente, validamos que ese agente pertenezca al
    nuevo equipo para no dejar una asignacion inconsistente.
    """

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise TicketTeamNotFoundError("Team not found")

    if ticket.team_id == team.id:
        raise TicketTeamAssignmentError("Ticket already assigned to this team")

    # Si el ticket ya tiene agente, no permitimos moverlo a un equipo donde
    # ese agente no pertenece. Evita inconsistencias entre team_id y assigned_to.
    if ticket.assigned_to is not None and not is_team_member(db, team.id, ticket.assigned_to):
        raise TicketTeamAssignmentError("Assigned user does not belong to target team")

    ticket.team_id = team.id

    return _commit_and_refresh(db, ticket)


def assign_ticket(db: Session, ticket_id: UUID, assigned_user_id: UUID, current_user: User) -> Ticket:
    """Asigna un ticket a un agente.

    ADMIN puede asignar libremente. Un AGENT solo puede hacerlo si es lead
    del equipo del ticket y el agente destino pertenece al mismo equipo.
    """

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    assigned_user = db.query(User).filter(User.id == assigned_user_id).first()
    if assigned_user is None:
        raise AssignedUserNotFoundError("Assigned user not found")

    if not assigned_user.is_active:
        raise InvalidAssignedUserError("Assigned user must be active")

    is_current_user_team_lead = False
    is_assigned_user_team_member = False

    if ticket.team_id is not None:
        is_current_user_team_lead = is_team_lead(db, ticket.team_id, current_user.id)
        is_assigned_user_team_member = is_team_member(db, ticket.team_id, assigned_user.id)

    if not can_user_assign_ticket(
        current_user,
        assigned_user,
        ticket,
        is_current_user_team_lead,
        is_assigned_user_team_member,
    ):
        raise TicketPermissionError("Not enough permissions or invalid assignment")

    return _assign_ticket_to_user(db, ticket, assigned_user.id, current_user.id)
