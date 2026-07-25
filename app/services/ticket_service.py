from app.core.ticket_rules import is_status_change_reason_required, is_valid_status_transition
from app.models.ticket import Ticket, TicketStatusHistory, TicketAssignmentHistory
from app.core.ticket_rules import can_user_change_status, can_user_assign_ticket


class TicketServiceError(Exception):
    pass


class TicketPermissionError(TicketServiceError):
    pass


class InvalidStatusTransitionError(TicketServiceError):
    pass


class TicketAlreadyAssignedError(TicketServiceError):
    pass


class MissingStatusChangeReasonError(TicketServiceError):
    pass


def create_ticket_service(db, ticket_in, current_user):
    new_ticket = Ticket(
        title=ticket_in.title,
        description=ticket_in.description,
        priority=ticket_in.priority,
        created_by=current_user.id,
    )

    try:
        db.add(new_ticket)
        db.commit()
        db.refresh(new_ticket)
        return new_ticket
    except Exception:
        # Deja la sesion limpia si falla la persistencia del ticket.
        db.rollback()
        raise


def change_ticket_status(db, ticket, new_status, user, reason=None):
    # Revalida la transición aquí para mantener la regla aunque el servicio
    # sea reutilizado desde otro endpoint o proceso en el futuro.
    # Valida que el usuario tenga permitido realizar el cambio de estado
    if not can_user_change_status(user, ticket, new_status):
        raise TicketPermissionError("Not enough permissions to change ticket status")

    if not is_valid_status_transition(ticket.status, new_status):
        raise InvalidStatusTransitionError("Invalid transition")

    normalized_reason = reason.strip() if reason else None
    if is_status_change_reason_required(ticket.status, new_status) and not normalized_reason:
        raise MissingStatusChangeReasonError("Reason is required for this status change")
        
    old_status = ticket.status
    ticket.status = new_status

    history = TicketStatusHistory(
        ticket_id=ticket.id,
        old_status=old_status,
        new_status=new_status,
        reason=normalized_reason,
        changed_by=user.id,
    )

    try:
        db.add(history)
        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception:
        # Deja la sesion limpia si falla el commit
        db.rollback()
        raise

def assign_ticket(db, ticket, current_user, assigned_user):
    # El service vuelve a validar la regla para que la lógica sea segura
    # aunque esta función se use desde otro endpoint o proceso.
    if not can_user_assign_ticket(current_user, assigned_user):
        raise TicketPermissionError("Not enough permissions or invalid assignment")

    # Guardamos el responsable anterior antes de modificar el ticket.
    old_assigned_to = ticket.assigned_to

    if old_assigned_to == assigned_user.id:
        raise TicketAlreadyAssignedError("Ticket already assigned to this user")

    # assigned_to es una columna UUID, por eso guardamos assigned_user.id
    # y no el objeto User completo.
    ticket.assigned_to = assigned_user.id

    history = TicketAssignmentHistory(
        ticket_id=ticket.id,
        old_assigned_to=old_assigned_to,
        new_assigned_to=assigned_user.id,
        changed_by=current_user.id,
    )

    try:
        db.add(history)
        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception:
        # Deja la sesion limpia si falla el commit 
        db.rollback()
        raise
