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

def can_user_assign_ticket(current_user, assigned_user):
    if current_user.role == "USER":
        return False
    if current_user.role == "AGENT":
        return False    
    if assigned_user.role == "USER":
        return False
    if assigned_user.role == "ADMIN":
        return False
    
    return True