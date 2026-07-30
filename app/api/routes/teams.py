from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_roles
from app.db.session import get_db
from app.models.team import Team, TeamMember
from app.models.ticket import Ticket
from app.models.user import User, UserRole
from app.schemas.team import TeamCreate, TeamMemberCreate, TeamMemberRead, TeamRead
from app.schemas.ticket import TicketRead
from app.services.team_service import (
    InvalidTeamLeadError,
    InvalidTeamMemberError,
    InvalidTeamNameError,
    TeamServiceError,
    TeamAlreadyExistsError,
    TeamDataConflictError,
    TeamLeadNotFoundError,
    TeamLeadRemovalError,
    TeamMemberAlreadyExistsError,
    TeamMemberNotFoundError,
    TeamNotFoundError,
    UserNotFoundError,
    add_team_member_service,
    create_team_service,
    remove_team_member_service,
)
from app.services.team_queries import is_team_member

router = APIRouter(prefix="/teams", tags=["teams"])
PaginationSkip = Annotated[int, Query(ge=0)]
PaginationLimit = Annotated[int, Query(ge=1, le=100)]


def _team_service_error_to_http(exc: TeamServiceError) -> HTTPException:
    if isinstance(exc, (TeamNotFoundError, TeamLeadNotFoundError, UserNotFoundError, TeamMemberNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))

    if isinstance(exc, (TeamAlreadyExistsError, TeamMemberAlreadyExistsError, TeamDataConflictError)):
        return HTTPException(status_code=409, detail=str(exc))

    if isinstance(exc, (InvalidTeamNameError, InvalidTeamLeadError, InvalidTeamMemberError, TeamLeadRemovalError)):
        return HTTPException(status_code=400, detail=str(exc))

    return HTTPException(status_code=400, detail=str(exc))


@router.post("/", response_model=TeamRead, status_code=201)
def create_team(
    team_in: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    try:
        # Crear team es un caso de uso de negocio: el service busca y valida al lead.
        return create_team_service(db, team_in)
    except TeamServiceError as exc:
        raise _team_service_error_to_http(exc) from exc


@router.get("/", response_model=list[TeamRead])
def get_teams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    # ADMIN ve todos los equipos; AGENT solo ve los equipos donde pertenece.
    query = db.query(Team).order_by(Team.name)

    if current_user.role == UserRole.ADMIN:
        return query.offset(skip).limit(limit).all()

    if current_user.role == UserRole.AGENT:
        team_ids = select(TeamMember.team_id).where(TeamMember.user_id == current_user.id)
        return query.filter(Team.id.in_(team_ids)).offset(skip).limit(limit).all()

    raise HTTPException(status_code=403, detail="Not enough permissions")


@router.get("/{team_id}", response_model=TeamRead)
def get_team(
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Este endpoint muestra un equipo solo si el usuario tiene alcance sobre el.
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if current_user.role != UserRole.ADMIN and not is_team_member(db, team.id, current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return team


@router.post("/{team_id}/members", response_model=TeamMemberRead, status_code=201)
def add_team_member(
    team_id: UUID,
    member_in: TeamMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    try:
        # El service valida que el team exista, que el usuario exista y que sea AGENT activo.
        return add_team_member_service(db, team_id, member_in.user_id)
    except TeamServiceError as exc:
        raise _team_service_error_to_http(exc) from exc


@router.delete("/{team_id}/members/{user_id}", status_code=204)
def remove_team_member(
    team_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    try:
        # El service protege la invariante: todo lead debe seguir siendo miembro.
        remove_team_member_service(db, team_id, user_id)
    except TeamServiceError as exc:
        raise _team_service_error_to_http(exc) from exc


@router.get("/{team_id}/tickets", response_model=list[TicketRead])
def get_team_tickets(
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    # La cola del equipo puede verla ADMIN o cualquier miembro del team.
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if current_user.role != UserRole.ADMIN and not is_team_member(db, team.id, current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return (
        db.query(Ticket)
        .filter(Ticket.team_id == team.id)
        .order_by(Ticket.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
