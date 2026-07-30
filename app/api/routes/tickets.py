from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_roles
from app.db.session import get_db
from app.models.team import TeamMember
from app.models.ticket import Ticket, TicketStatusHistory, TicketAssignmentHistory
from app.models.user import User, UserRole
from app.schemas.ticket import (
    TicketAssignmentHistoryRead,
    TicketAssignmentUpdate,
    TicketCreate,
    TicketRead,
    TicketStatusHistoryRead,
    TicketTeamAssignmentUpdate,
    UpdateTicketStatus,
)
from app.services.ticket_service import (
    InvalidStatusTransitionError,
    AssignedUserNotFoundError,
    InvalidAssignedUserError,
    MissingStatusChangeReasonError,
    TicketAlreadyAssignedError,
    TicketCategoryNotFoundError,
    TicketNotFoundError,
    TicketPermissionError,
    TicketTeamAssignmentError,
    TicketTeamNotFoundError,
    InvalidTicketCategoryError,
    assign_ticket,
    assign_ticket_to_team,
    change_ticket_status,
    create_ticket_service,
)
from app.core.ticket_rules import (
    can_user_view_assignment_history,
    can_user_view_status_history,
)
from app.services.team_queries import is_team_member

router = APIRouter(prefix="/tickets", tags=["tickets"])
PaginationSkip = Annotated[int, Query(ge=0)]
PaginationLimit = Annotated[int, Query(ge=1, le=100)]


@router.post("/", response_model=TicketRead, status_code=201)
def create_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return create_ticket_service(db, ticket, current_user)
    except TicketCategoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidTicketCategoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/created-by-me", response_model=list[TicketRead])
def get_tickets_created_by_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    # Tickets que el usuario autenticado creo como solicitante.
    # skip/limit permiten traer el listado por partes y evitan respuestas enormes.
    return (
        db.query(Ticket)
        .filter(Ticket.created_by == current_user.id)
        .order_by(Ticket.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/assigned-to-me", response_model=list[TicketRead])
def get_tickets_assigned_to_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("AGENT", "ADMIN")),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    # Tickets que el usuario autenticado tiene asignados como responsable.
    # El orden estable hace que la pagina 1, 2, 3, etc. sean consistentes.
    return (
        db.query(Ticket)
        .filter(Ticket.assigned_to == current_user.id)
        .order_by(Ticket.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/", response_model=list[TicketRead])
def get_all_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("AGENT", "ADMIN")),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    # Esta vista queda reservada para perfiles operativos.
    # Paginamos el listado general porque puede crecer mucho mas que los listados personales.
    query = db.query(Ticket).order_by(Ticket.created_at.desc())

    if current_user.role == UserRole.AGENT:
        team_ids = select(TeamMember.team_id).where(TeamMember.user_id == current_user.id)
        query = query.filter(
            or_(
                Ticket.assigned_to == current_user.id,
                Ticket.team_id.in_(team_ids),
            )
        )

    return query.offset(skip).limit(limit).all()


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

    current_user_is_team_member = is_team_member(db, ticket.team_id, current_user.id)
    if not can_user_view_status_history(current_user, ticket, current_user_is_team_member):
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
    

@router.patch("/{ticket_id}/assign-team", response_model=TicketRead)
def ticket_team_assignment(
    ticket_id: UUID,
    assignment: TicketTeamAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    try:
        # El service busca ticket/team y valida que no quede un agente de otro equipo asignado.
        return assign_ticket_to_team(db, ticket_id, assignment.team_id)
    except (TicketNotFoundError, TicketTeamNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketTeamAssignmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{ticket_id}/assign", response_model=TicketRead)
def ticket_assignment(
    ticket_id: UUID,
    assignment: TicketAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    try:
        # ADMIN asigna libremente; TEAM LEAD solo dentro de su equipo.
        return assign_ticket(db, ticket_id, assignment.assigned_to, current_user)
    except (TicketNotFoundError, AssignedUserNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketAlreadyAssignedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except InvalidAssignedUserError as exc:
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

    current_user_is_team_member = is_team_member(db, ticket.team_id, current_user.id)
    if not can_user_view_assignment_history(current_user, ticket, current_user_is_team_member):
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
