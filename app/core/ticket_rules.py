from app.models.ticket import TicketCommentVisibility, TicketStatus
from app.models.user import UserRole


# Estos roles pueden asumir la responsabilidad operativa de un ticket.
ASSIGNABLE_USER_ROLES = {UserRole.AGENT, UserRole.ADMIN}


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
    # USER representa al solicitante; solo AGENT y ADMIN pueden resolver tickets.
    if assigned_user is None or assigned_user.role not in ASSIGNABLE_USER_ROLES:
        return False

    # Un ticket debe ingresar primero a un equipo. Ningun rol, incluido ADMIN,
    # puede asignar una persona directamente desde la cola de categoria.
    if ticket is None or ticket.team_id is None:
        return False

    # El responsable debe pertenecer al equipo que atiende el ticket.
    if not is_assigned_user_team_member:
        return False

    if current_user.role == UserRole.ADMIN:
        return True

    # Un team lead puede asignar tickets de su propio equipo a miembros del mismo equipo.
    if (
        current_user.role == UserRole.AGENT
        and ticket is not None
        and ticket.team_id is not None
        and is_current_user_team_lead
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


def can_user_view_comments(user, ticket, is_team_member: bool = False) -> bool:
    """Los comentarios siguen el acceso al ticket; la visibilidad se filtra aparte."""

    return can_user_view_ticket(user, ticket, is_team_member)


def can_ticket_receive_comments(ticket) -> bool:
    """Un ticket cerrado o archivado conserva sus comentarios, pero no acepta nuevos."""

    return ticket.status != TicketStatus.CLOSED and ticket.archived_at is None


def can_user_create_comment(
    user,
    ticket,
    visibility: TicketCommentVisibility,
    is_team_member: bool = False,
    is_team_lead: bool = False,
) -> bool:
    """Decide si el participante puede publicar el tipo de comentario solicitado."""

    if user.role == UserRole.ADMIN:
        return True

    if user.role == UserRole.USER:
        return ticket.created_by == user.id and visibility == TicketCommentVisibility.REQUESTER_VISIBLE

    if user.role != UserRole.AGENT:
        return False

    is_assigned_agent = ticket.assigned_to == user.id
    if not (is_assigned_agent or is_team_member):
        return False

    if visibility == TicketCommentVisibility.INTERNAL:
        return True

    # Las respuestas al solicitante quedan a cargo del responsable o de un lead.
    return is_assigned_agent or is_team_lead
