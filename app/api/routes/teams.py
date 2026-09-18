"""Endpoints HTTP para equipos, miembros, leads y políticas de asignación."""

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
from app.schemas.team import (
    TeamCreate,
    TeamAutoAssignmentUpdate,
    TeamLeadCreate,
    TeamLeadRead,
    TeamMemberCreate,
    TeamMemberRead,
    TeamRead,
    TeamSelfAssignmentUpdate,
)
from app.schemas.ticket import TicketRead
from app.services.team_service import (
    InvalidTeamLeadError,
    InvalidTeamAssignmentSettingsError,
    InvalidTeamMemberError,
    InvalidTeamNameError,
    TeamServiceError,
    TeamAlreadyExistsError,
    TeamDataConflictError,
    TeamLeadNotFoundError,
    TeamLeadRemovalError,
    TeamLeadAlreadyExistsError,
    TeamMemberAlreadyExistsError,
    TeamMemberNotFoundError,
    TeamNotFoundError,
    UserNotFoundError,
    add_team_lead_service,
    add_team_member_service,
    create_team_service,
    get_team_leads_service,
    remove_team_lead_service,
    remove_team_member_service,
    update_team_auto_assignment_service,
    update_team_self_assignment_service,
)
from app.services.team_queries import is_team_member

router = APIRouter(prefix="/teams", tags=["teams"])
PaginationSkip = Annotated[int, Query(ge=0)]
PaginationLimit = Annotated[int, Query(ge=1, le=100)]


def _team_service_error_to_http(exc: TeamServiceError) -> HTTPException:
    """Traduce errores de equipos a códigos HTTP estables."""

    if isinstance(exc, (TeamNotFoundError, TeamLeadNotFoundError, UserNotFoundError, TeamMemberNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))

    if isinstance(exc, (TeamAlreadyExistsError, TeamMemberAlreadyExistsError, TeamLeadAlreadyExistsError, TeamDataConflictError)):
        return HTTPException(status_code=409, detail=str(exc))

    if isinstance(
        exc,
        (
            InvalidTeamNameError,
            InvalidTeamLeadError,
            InvalidTeamMemberError,
            InvalidTeamAssignmentSettingsError,
            TeamLeadRemovalError,
        ),
    ):
        return HTTPException(status_code=400, detail=str(exc))

    return HTTPException(status_code=400, detail=str(exc))


@router.post("/", response_model=TeamRead, status_code=201)
def create_team(
    team_in: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Crea un equipo con su primer lead y miembro."""

    try:
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
    """Lista todos los equipos para admins y las membresías propias para agentes."""

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
    """Devuelve un equipo visible para el admin o uno de sus miembros."""

    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if current_user.role != UserRole.ADMIN and not is_team_member(db, team.id, current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return team


@router.patch("/{team_id}/self-assignment", response_model=TeamRead)
def update_team_self_assignment(
    team_id: UUID,
    settings_in: TeamSelfAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Configura si los miembros pueden reclamar tickets del equipo."""

    try:
        return update_team_self_assignment_service(
            db,
            team_id,
            settings_in.self_assignment_enabled,
        )
    except TeamServiceError as exc:
        raise _team_service_error_to_http(exc) from exc


@router.patch("/{team_id}/auto-assignment", response_model=TeamRead)
def update_team_auto_assignment(
    team_id: UUID,
    settings_in: TeamAutoAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Guarda la política que se copiará a los tickets que ingresen al team."""

    try:
        return update_team_auto_assignment_service(
            db,
            team_id,
            settings_in.auto_assignment_enabled,
            settings_in.auto_assignment_delay_minutes,
            settings_in.assignment_strategy,
        )
    except TeamServiceError as exc:
        raise _team_service_error_to_http(exc) from exc


@router.post("/{team_id}/members", response_model=TeamMemberRead, status_code=201)
def add_team_member(
    team_id: UUID,
    member_in: TeamMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Agrega un agente o administrador activo como miembro del equipo."""

    try:
        return add_team_member_service(db, team_id, member_in.user_id)
    except TeamServiceError as exc:
        raise _team_service_error_to_http(exc) from exc


@router.get("/{team_id}/leads", response_model=list[TeamLeadRead])
def get_team_leads(
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Lista los responsables de liderazgo del equipo."""

    try:
        return get_team_leads_service(db, team_id)
    except TeamServiceError as exc:
        raise _team_service_error_to_http(exc) from exc


@router.post("/{team_id}/leads", response_model=TeamLeadRead, status_code=201)
def add_team_lead(
    team_id: UUID,
    lead_in: TeamLeadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Agrega un lead y garantiza que también sea miembro del equipo."""

    try:
        return add_team_lead_service(db, team_id, lead_in.user_id)
    except TeamServiceError as exc:
        raise _team_service_error_to_http(exc) from exc


@router.delete("/{team_id}/leads/{user_id}", status_code=204)
def remove_team_lead(
    team_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Quita un lead sin permitir que el equipo quede sin liderazgo."""

    try:
        remove_team_lead_service(db, team_id, user_id)
    except TeamServiceError as exc:
        raise _team_service_error_to_http(exc) from exc


@router.delete("/{team_id}/members/{user_id}", status_code=204)
def remove_team_member(
    team_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Quita un miembro que no sea lead del equipo."""

    try:
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
    """Lista tickets no archivados del equipo para admins y miembros."""

    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if current_user.role != UserRole.ADMIN and not is_team_member(db, team.id, current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return (
        db.query(Ticket)
        .filter(Ticket.team_id == team.id, Ticket.archived_at.is_(None))
        .order_by(Ticket.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
