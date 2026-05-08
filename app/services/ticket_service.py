from app.core.ticket_rules import is_valid_status_transition
from app.models.ticket import TicketStatusHistory
from app.core.ticket_rules import can_user_change_status


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

    db.add(history)
    db.commit()
    db.refresh(ticket)

    return ticket

def assign_ticket(db, ticket, assigned_user, current_user):
    