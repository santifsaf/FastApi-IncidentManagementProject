from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_roles
from app.db.session import get_db
from app.models.ticket import Ticket, TicketStatusHistory, TicketAssignmentHistory
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketRead, UpdateTicketStatus, TicketStatusHistoryRead, TicketAssignmentUpdate, TicketAssignmentHistoryRead
from app.services.ticket_service import (
    InvalidStatusTransitionError,
    MissingStatusChangeReasonError,
    TicketAlreadyAssignedError,
    TicketPermissionError,
    assign_ticket,
    change_ticket_status,
    create_ticket_service,
)
from app.core.ticket_rules import (
    can_user_view_assignment_history,
    can_user_view_status_history,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("/", response_model=TicketRead, status_code=201)
def create_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return create_ticket_service(db, ticket, current_user)


@router.get("/created-by-me", response_model=list[TicketRead])
def get_tickets_created_by_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Tickets que el usuario autenticado creo como solicitante.
    return db.query(Ticket).filter(Ticket.created_by == current_user.id).all()


@router.get("/assigned-to-me", response_model=list[TicketRead])
def get_tickets_assigned_to_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("AGENT", "ADMIN")),
):
    # Tickets que el usuario autenticado tiene asignados como responsable.
    return db.query(Ticket).filter(Ticket.assigned_to == current_user.id).all()


@router.get("/", response_model=list[TicketRead])
def get_all_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("AGENT", "ADMIN")),
):
    # Esta vista queda reservada para perfiles operativos.
    return db.query(Ticket).all()


@router.get("/{ticket_id}/status-history", response_model=list[TicketStatusHistoryRead])
def get_ticket_status_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Primero validamos que el ticket exista para no devolver un historial vacío
    # cuando en realidad el recurso no existe.
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if not can_user_view_status_history(current_user, ticket):
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions to view ticket status history",
        )

    return (
        db.query(TicketStatusHistory)
        .filter(TicketStatusHistory.ticket_id == ticket_id)
        .order_by(TicketStatusHistory.changed_at.desc())
        .all()
    )

@router.patch("/{ticket_id}/status", response_model=TicketRead)
def update_ticket_status(
    ticket_id: UUID,
    ticket_update: UpdateTicketStatus,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("AGENT", "ADMIN")),
):
    # Busca el ticket concreto que vino en la URL.
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        return change_ticket_status(db, ticket, ticket_update.status, current_user, ticket_update.reason)
    except (InvalidStatusTransitionError, MissingStatusChangeReasonError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    

@router.patch("/{ticket_id}/assign", response_model=TicketRead)
def ticket_assignment(
    ticket_id: UUID,
    assignment: TicketAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    # Buscamos el ticket que se quiere asignar.
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # El usuario asignado viene en el body, no desde Depends.
    # Depends representa al usuario autenticado, no al usuario destino.
    assigned_user = db.query(User).filter(User.id == assignment.assigned_to).first()

    if not assigned_user:
        raise HTTPException(status_code=404, detail="Assigned user not found")

    try:
        return assign_ticket(db, ticket, current_user, assigned_user)
    except TicketAlreadyAssignedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{ticket_id}/assignment-history", response_model=list[TicketAssignmentHistoryRead])
def get_ticket_assignment_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Validamos que el ticket exista para no confundir "sin historial"
    # con "ticket inexistente".
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if not can_user_view_assignment_history(current_user, ticket):
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions to view ticket assignment history",
        )

    return (
        db.query(TicketAssignmentHistory)
        .filter(TicketAssignmentHistory.ticket_id == ticket_id)
        .order_by(TicketAssignmentHistory.changed_at.desc())
        .all()
    )
