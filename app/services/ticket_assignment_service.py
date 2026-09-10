"""Casos de uso de asignacion, equipo y categoria de tickets."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.ticket_rules import (
    can_user_assign_ticket,
    can_user_claim_ticket,
    can_user_view_assignment_history,
)
from app.models.category import TicketCategory
from app.models.team import Team
from app.models.ticket import (
    Ticket,
    TicketAssignmentHistory,
    TicketCategoryHistory,
    TicketStatus,
    TicketTeamHistory,
)
from app.models.user import User, UserRole
from app.services.category_queries import is_category_associated_with_team
from app.services.team_queries import is_team_lead, is_team_member
from app.services.ticket_exceptions import (
    AssignedUserNotFoundError,
    InvalidAssignedUserError,
    InvalidTicketCategoryChangeError,
    InvalidTicketCategoryError,
    MissingCategoryChangeReasonError,
    TicketAlreadyAssignedError,
    TicketCategoryNotFoundError,
    TicketClaimNotAllowedError,
    TicketNotFoundError,
    TicketPermissionError,
    TicketTeamAssignmentError,
    TicketTeamNotFoundError,
    TicketTeamPermissionError,
)
from app.services.ticket_service_utils import commit_and_refresh, normalize_optional_reason


def _assign_ticket_to_user(db: Session, ticket: Ticket, new_user_id: UUID, changed_by_id: UUID) -> Ticket:
    """Actualiza el responsable y registra ambos cambios en una transaccion."""

    old_assigned_to = ticket.assigned_to
    if old_assigned_to == new_user_id:
        raise TicketAlreadyAssignedError("Ticket already assigned to this user")

    ticket.assigned_to = new_user_id
    db.add(
        TicketAssignmentHistory(
            ticket_id=ticket.id,
            old_assigned_to=old_assigned_to,
            new_assigned_to=new_user_id,
            changed_by=changed_by_id,
        )
    )
    return commit_and_refresh(db, ticket)


def assign_ticket(db: Session, ticket_id: UUID, assigned_user_id: UUID, current_user: User) -> Ticket:
    """Asigna a un miembro activo del team como responsable del ticket."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    if ticket.team_id is None:
        raise TicketTeamAssignmentError("Ticket must belong to a team before assigning a responsible user")

    assigned_user = db.query(User).filter(User.id == assigned_user_id).first()
    if assigned_user is None:
        raise AssignedUserNotFoundError("Assigned user not found")

    if not assigned_user.is_active:
        raise InvalidAssignedUserError("Assigned user must be active")

    current_user_is_lead = is_team_lead(db, ticket.team_id, current_user.id)
    assigned_user_is_member = is_team_member(db, ticket.team_id, assigned_user.id)

    if not can_user_assign_ticket(
        current_user,
        assigned_user,
        ticket,
        is_current_user_team_lead=current_user_is_lead,
        is_assigned_user_team_member=assigned_user_is_member,
    ):
        raise TicketPermissionError("Not enough permissions or invalid assignment")

    return _assign_ticket_to_user(db, ticket, assigned_user.id, current_user.id)


def claim_ticket(db: Session, ticket_id: UUID, current_user: User) -> Ticket:
    """Permite que un agente tome un ticket abierto de su propio equipo.

    La fila queda bloqueada hasta finalizar la transaccion. De esta manera, si
    dos agentes reclaman a la vez, solo el primero puede completar la accion.
    """

    if current_user.role != UserRole.AGENT or not current_user.is_active:
        raise TicketPermissionError("Only active agents can claim tickets")

    try:
        ticket = (
            db.query(Ticket)
            .filter(Ticket.id == ticket_id)
            .with_for_update()
            .first()
        )
        if ticket is None:
            raise TicketNotFoundError("Ticket not found")

        if ticket.team_id is None:
            raise TicketClaimNotAllowedError("Ticket must belong to a team before it can be claimed")
        if ticket.assigned_to is not None:
            raise TicketAlreadyAssignedError("Ticket already has an assigned user")
        if ticket.status != TicketStatus.OPEN:
            raise TicketClaimNotAllowedError("Only open tickets can be claimed")
        if ticket.archived_at is not None:
            raise TicketClaimNotAllowedError("Archived tickets cannot be claimed")

        team = db.query(Team).filter(Team.id == ticket.team_id).first()
        if team is None:
            raise TicketTeamNotFoundError("Team not found")

        current_user_is_member = is_team_member(db, team.id, current_user.id)
        if not current_user_is_member:
            raise TicketPermissionError("Agent must belong to the ticket team")
        if not team.self_assignment_enabled:
            raise TicketClaimNotAllowedError("Self-assignment is disabled for this team")

        if not can_user_claim_ticket(
            current_user,
            ticket,
            is_team_member=current_user_is_member,
            self_assignment_enabled=team.self_assignment_enabled,
        ):
            raise TicketClaimNotAllowedError("Ticket cannot be claimed")

        return _assign_ticket_to_user(db, ticket, current_user.id, current_user.id)
    except Exception:
        # Tambien libera el FOR UPDATE cuando una validacion rechaza el reclamo.
        db.rollback()
        raise


def assign_ticket_to_team(db: Session, ticket_id: UUID, team_id: UUID, current_user: User) -> Ticket:
    """Asigna un ticket a un equipo y audita el cambio."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise TicketTeamNotFoundError("Team not found")

    if ticket.team_id == team.id:
        raise TicketTeamAssignmentError("Ticket already assigned to this team")

    if current_user.role != UserRole.ADMIN:
        if ticket.team_id is not None:
            raise TicketTeamPermissionError("Team lead can only assign tickets without team")
        if not is_team_lead(db, team.id, current_user.id):
            raise TicketTeamPermissionError("Not enough permissions to assign ticket to this team")
        if not is_category_associated_with_team(db, ticket.category_id, team.id):
            raise TicketTeamPermissionError("Ticket category is not associated with this team")

    # Un responsable existente debe seguir perteneciendo al equipo de destino.
    if ticket.assigned_to is not None and not is_team_member(db, team.id, ticket.assigned_to):
        raise TicketTeamAssignmentError("Assigned user does not belong to target team")

    old_team_id = ticket.team_id
    ticket.team_id = team.id
    db.add(
        TicketTeamHistory(
            ticket_id=ticket.id,
            old_team_id=old_team_id,
            new_team_id=team.id,
            changed_by=current_user.id,
        )
    )
    return commit_and_refresh(db, ticket)


def change_ticket_category(
    db: Session,
    ticket_id: UUID,
    new_category_id: UUID,
    current_user: User,
    reason: str | None,
) -> Ticket:
    """Recategoriza el ticket y limpia asignaciones que pueden quedar invalidas."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    new_category = db.query(TicketCategory).filter(TicketCategory.id == new_category_id).first()
    if new_category is None:
        raise TicketCategoryNotFoundError("Category not found")
    if not new_category.is_active:
        raise InvalidTicketCategoryError("Inactive categories cannot be used for tickets")
    if ticket.category_id == new_category.id:
        raise InvalidTicketCategoryChangeError("Ticket already belongs to this category")

    normalized_reason = normalize_optional_reason(reason)
    if not normalized_reason:
        raise MissingCategoryChangeReasonError("Reason is required for category change")

    if current_user.role == UserRole.ADMIN:
        if ticket.status == TicketStatus.CLOSED:
            raise InvalidTicketCategoryChangeError("Closed tickets cannot change category")
    elif current_user.role == UserRole.AGENT:
        allowed_statuses = {TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.ON_HOLD}
        if ticket.status not in allowed_statuses:
            raise InvalidTicketCategoryChangeError(
                "Category can only be changed while ticket is open, in progress, or on hold"
            )
        if ticket.team_id is None or not is_team_lead(db, ticket.team_id, current_user.id):
            raise TicketPermissionError("Only the current team lead can change ticket category")
    else:
        raise TicketPermissionError("Not enough permissions to change ticket category")

    old_category_id = ticket.category_id
    old_team_id = ticket.team_id
    old_assigned_to = ticket.assigned_to
    ticket.category_id = new_category.id
    ticket.team_id = None
    ticket.assigned_to = None

    db.add(
        TicketCategoryHistory(
            ticket_id=ticket.id,
            old_category_id=old_category_id,
            new_category_id=new_category.id,
            reason=normalized_reason,
            changed_by=current_user.id,
        )
    )
    if old_team_id is not None:
        db.add(
            TicketTeamHistory(
                ticket_id=ticket.id,
                old_team_id=old_team_id,
                new_team_id=None,
                changed_by=current_user.id,
            )
        )
    if old_assigned_to is not None:
        db.add(
            TicketAssignmentHistory(
                ticket_id=ticket.id,
                old_assigned_to=old_assigned_to,
                new_assigned_to=None,
                changed_by=current_user.id,
            )
        )

    return commit_and_refresh(db, ticket)


def _get_history_context(
    db: Session,
    ticket_id: UUID,
    current_user: User,
    permission_message: str,
) -> Ticket:
    """Valida una vez el acceso comun a historiales internos de asignacion."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    current_user_is_member = is_team_member(db, ticket.team_id, current_user.id)
    if not can_user_view_assignment_history(current_user, ticket, current_user_is_member):
        raise TicketPermissionError(permission_message)
    return ticket


def get_ticket_category_history_service(
    db: Session, ticket_id: UUID, current_user: User
) -> list[TicketCategoryHistory]:
    _get_history_context(
        db,
        ticket_id,
        current_user,
        "Not enough permissions to view ticket category history",
    )
    return (
        db.query(TicketCategoryHistory)
        .filter(TicketCategoryHistory.ticket_id == ticket_id)
        .order_by(TicketCategoryHistory.changed_at.desc())
        .all()
    )


def get_ticket_assignment_history_service(
    db: Session, ticket_id: UUID, current_user: User
) -> list[TicketAssignmentHistory]:
    _get_history_context(
        db,
        ticket_id,
        current_user,
        "Not enough permissions to view ticket assignment history",
    )
    return (
        db.query(TicketAssignmentHistory)
        .filter(TicketAssignmentHistory.ticket_id == ticket_id)
        .order_by(TicketAssignmentHistory.changed_at.desc())
        .all()
    )


def get_ticket_team_history_service(
    db: Session, ticket_id: UUID, current_user: User
) -> list[TicketTeamHistory]:
    _get_history_context(
        db,
        ticket_id,
        current_user,
        "Not enough permissions to view ticket team history",
    )
    return (
        db.query(TicketTeamHistory)
        .filter(TicketTeamHistory.ticket_id == ticket_id)
        .order_by(TicketTeamHistory.changed_at.desc())
        .all()
    )
