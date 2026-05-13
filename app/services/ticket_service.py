from app.core.ticket_rules import is_valid_status_transition
from app.models.ticket import TicketStatusHistory, TicketAssignmentHistory
from app.core.ticket_rules import can_user_change_status, can_user_assign_ticket


def change_ticket_status(db, ticket, new_status, user):
    # Revalida la transición aquí para mantener la regla aunque el servicio
    # sea reutilizado desde otro endpoint o proceso en el futuro.
    # Valida que el usuario tenga permitido realizar el cambio de estado
    if not can_user_change_status(user, ticket.status, new_status):
        raise PermissionError("Not enough permissions to change ticket status")

    if not is_valid_status_transition(ticket.status, new_status):
        raise ValueError("Invalid transition")
        
    old_status = ticket.status
    ticket.status = new_status

    history = TicketStatusHistory(
        ticket_id=ticket.id,
        old_status=old_status,
        new_status=new_status,
        changed_by=user.id,
    )

    try:
        db.add(history)
        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception:
        # Deja la sesion limpia si falla el commit o el flush implicito.
        db.rollback()
        raise

def assign_ticket(db, ticket, current_user, assigned_user):
    # El service vuelve a validar la regla para que la lógica sea segura
    # aunque esta función se use desde otro endpoint o proceso.
    if not can_user_assign_ticket(current_user, assigned_user):
        raise PermissionError("Not enough permissions or invalid assignment")

    # Guardamos el responsable anterior antes de modificar el ticket.
    old_assigned_to = ticket.assigned_to

    if old_assigned_to == assigned_user.id:
        raise ValueError("Ticket already assigned to this user")

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
        # Deja la sesion limpia si falla el commit o el flush implicito.
        db.rollback()
        raise
