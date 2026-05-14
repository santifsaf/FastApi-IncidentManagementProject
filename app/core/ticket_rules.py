from app.models.ticket import TicketStatus


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


def can_user_change_status(user, ticket_status, new_status) -> bool:
    if user.role == "USER":
        return False

    if new_status == TicketStatus.CLOSED and user.role != "ADMIN":
        return False

    return True

def can_user_assign_ticket(current_user, assigned_user) -> bool:
    # Solo un ADMIN puede asignar tickets.
    if current_user.role != "ADMIN":
        return False

    # El usuario destino debe existir; esta validación protege al service
    # si alguien lo reutiliza sin validar antes en el endpoint.
    if assigned_user is None:
        return False

    # Los tickets solo se asignan a agentes operativos.
    if assigned_user.role != "AGENT":
        return False

    return True


def can_user_view_status_history(user, ticket) -> bool:
    if user.role == "ADMIN":
        return True

    if user.role == "AGENT" and ticket.assigned_to == user.id:
        return True

    if user.role == "USER" and ticket.created_by == user.id:
        return True

    return False


def can_user_view_assignment_history(user, ticket) -> bool:
    if user.role == "ADMIN":
        return True

    # El historial de asignaciones es informacion operativa interna.
    if user.role == "AGENT" and ticket.assigned_to == user.id:
        return True

    return False
