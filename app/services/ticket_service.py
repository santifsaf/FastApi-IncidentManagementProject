def change_ticket_status(db, ticket, new_status, user):
    if not is_valid_status_transition(ticket.status, new_status):
        raise ValueError("Invalid transition")

    old_status = ticket.status
    ticket.status = new_status

    history = TicketStatusHistory(
        ticket_id=ticket.id,
        old_status=old_status,
        new_status=new_status,
        changed_by=user.id
    )

    db.add(history)
    db.commit()
    db.refresh(ticket)

    return ticket
