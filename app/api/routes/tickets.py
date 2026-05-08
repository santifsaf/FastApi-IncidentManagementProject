from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_roles
from app.db.session import get_db
from app.models.ticket import Ticket, TicketStatusHistory
from app.models.user import User
from app.schemas.ticket import TicketCreate, TicketRead, UpdateTicketStatus, TicketStatusHistoryRead, TicketAssignment
from app.services.ticket_service import change_ticket_status
from app.core.ticket_rules import can_user_change_status, can_user_assign_ticket

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("/", response_model=TicketRead, status_code=201)
def create_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    new_ticket = Ticket(
        title=ticket.title,
        description=ticket.description,
        priority=ticket.priority,
        created_by=current_user.id,
    )

    db.add(new_ticket)
    db.commit()
    db.refresh(new_ticket)

    return new_ticket


@router.get("/my", response_model=list[TicketRead])
def get_my_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Solo devuelve tickets creados por el usuario autenticado.
    return db.query(Ticket).filter(Ticket.created_by == current_user.id).all()


@router.get("/", response_model=list[TicketRead])
def get_all_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("AGENT", "ADMIN")),
):
    # Esta vista queda reservada para perfiles operativos.
    return db.query(Ticket).all()


@router.get("/{ticket_id}/history", response_model=list[TicketStatusHistoryRead])
def get_ticket_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),  #DEFINIR REGLAS SEGUN ROL PARA ACCEDER AL HISTORIAL 
):
    # Primero validamos que el ticket exista para no devolver un historial vacío
    # cuando en realidad el recurso no existe.
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

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

    if not can_user_change_status(current_user, ticket.status, ticket_update.status):
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions to change ticket status",
        )

    try:
        return change_ticket_status(db, ticket, ticket_update.status, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    

@router.patch("/{ticket_id}/assign", response_model=TicketAssignment)
def ticket_assignment(
    ticket_id:UUID,
    assigned_user: User = Depends(require_roles("AGENT")),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
    
    if not can_user_assign_ticket(current_user, assigned_user):
        raise HTTPException(
            status_code=403,
            detail="Mnejo de error dentro de ticket_rules? en el service? ",
        )