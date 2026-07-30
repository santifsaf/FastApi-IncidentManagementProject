from app.models.ticket import TicketStatus
from app.models.user import UserRole


# Flujo basico permitido para cambios de estado.
ALLOWED_TRANSITIONS = {
    TicketStatus.OPEN: {TicketStatus.IN_PROGRESS, TicketStatus.ON_HOLD, TicketStatus.RESOLVED},
    TicketStatus.IN_PROGRESS: {TicketStatus.ON_HOLD, TicketStatus.RESOLVED},
    TicketStatus.ON_HOLD: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED},
    TicketStatus.RESOLVED: {TicketStatus.OPEN, TicketStatus.CLOSED},
    TicketStatus.CLOSED: set(),
}


def is_valid_status_transition(current_status: TicketStatus, new_status: TicketStatus) -> bool:
    return new_status in ALLOWED_TRANSITIONS.get(current_status, set())


def is_status_change_reason_required(current_status: TicketStatus, new_status: TicketStatus) -> bool:
    return (
        new_status in {TicketStatus.ON_HOLD, TicketStatus.CLOSED}
        or current_status == TicketStatus.RESOLVED and new_status == TicketStatus.OPEN
    )


def can_user_change_status(user, ticket, new_status) -> bool:
    if user.role == UserRole.USER:
        return False

    if user.role == UserRole.AGENT and ticket.assigned_to != user.id:
        return False

    if new_status == TicketStatus.CLOSED and user.role != UserRole.ADMIN:
        return False

    return True


def can_user_view_ticket(user, ticket, is_team_member: bool = False) -> bool:
    if user.role == UserRole.ADMIN:
        return True

    if user.role == UserRole.USER:
        return ticket.created_by == user.id

    if user.role == UserRole.AGENT:
        return ticket.assigned_to == user.id or is_team_member

    return False


def can_user_assign_ticket(
    current_user,
    assigned_user,
    ticket=None,
    is_current_user_team_lead: bool = False,
    is_assigned_user_team_member: bool = False,
) -> bool:
    # La asignacion siempre requiere un usuario destino agente.
    if assigned_user is None or assigned_user.role != UserRole.AGENT:
        return False

    if current_user.role == UserRole.ADMIN:
        return True

    # Un team lead puede asignar tickets de su propio equipo a miembros del mismo equipo.
    if (
        current_user.role == UserRole.AGENT
        and ticket is not None
        and ticket.team_id is not None
        and is_current_user_team_lead
        and is_assigned_user_team_member
    ):
        return True

    return False


def can_user_view_status_history(user, ticket, is_team_member: bool = False) -> bool:
    if user.role == UserRole.ADMIN:
        return True

    if user.role == UserRole.AGENT and (ticket.assigned_to == user.id or is_team_member):
        return True

    if user.role == UserRole.USER and ticket.created_by == user.id:
        return True

    return False


def can_user_view_assignment_history(user, ticket, is_team_member: bool = False) -> bool:
    if user.role == UserRole.ADMIN:
        return True

    if user.role == UserRole.AGENT and (ticket.assigned_to == user.id or is_team_member):
        return True

    return False
