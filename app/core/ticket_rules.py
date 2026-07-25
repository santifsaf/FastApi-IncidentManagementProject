from app.models.ticket import TicketStatus
from app.models.user import UserRole


# Define qué cambios de estado están permitidos dentro del flujo básico del ticket.
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

def can_user_assign_ticket(current_user, assigned_user) -> bool:
    # Solo un ADMIN puede asignar tickets.
    if current_user.role != UserRole.ADMIN:
        return False

    # El usuario destino debe existir; esta validación protege al service
    # si alguien lo reutiliza sin validar antes en el endpoint.
    if assigned_user is None:
        return False

    # Los tickets solo se asignan a agentes operativos.
    if assigned_user.role != UserRole.AGENT:
        return False

    return True


def can_user_view_status_history(user, ticket) -> bool:
    if user.role == UserRole.ADMIN:
        return True

    if user.role == UserRole.AGENT and ticket.assigned_to == user.id:
        return True

    if user.role == UserRole.USER and ticket.created_by == user.id:
        return True

    return False


def can_user_view_assignment_history(user, ticket) -> bool:
    if user.role == UserRole.ADMIN:
        return True

    if user.role == UserRole.AGENT and ticket.assigned_to == user.id:
        return True

    return False
