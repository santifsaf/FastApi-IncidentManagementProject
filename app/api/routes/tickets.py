from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_roles
from app.db.session import get_db
from app.models.team import TeamMember
from app.models.ticket import Ticket, TicketAssignmentHistory, TicketStatusHistory
from app.models.user import User, UserRole
from app.schemas.ticket import (
    BlockingTicketCreate,
    BlockingTicketRead,
    TicketAssignmentHistoryRead,
    TicketAssignmentUpdate,
    TicketArchiveUpdate,
    TicketCategoryHistoryRead,
    TicketCategoryUpdate,
    TicketCommentCreate,
    TicketCommentRead,
    TicketCreate,
    TicketDependencyCreate,
    TicketDependencyRemove,
    TicketDependencyRead,
    TicketRead,
    TicketStatusHistoryRead,
    TicketTeamHistoryRead,
    TicketTeamAssignmentUpdate,
    UpdateTicketStatus,
)
from app.services.ticket_service import (
    InvalidStatusTransitionError,
    AssignedUserNotFoundError,
    InvalidAssignedUserError,
    MissingStatusChangeReasonError,
    MissingCategoryChangeReasonError,
    TicketAlreadyAssignedError,
    TicketCategoryNotFoundError,
    TicketNotFoundError,
    TicketPermissionError,
    TicketTeamAssignmentError,
    TicketTeamNotFoundError,
    TicketTeamPermissionError,
    InvalidTicketCategoryError,
    InvalidTicketCategoryChangeError,
    TicketBlockedByOpenDependenciesError,
    TicketArchiveError,
    TicketCommentError,
    TicketDependencyError,
    TicketDependencyNotFoundError,
    add_ticket_dependency,
    archive_ticket,
    assign_ticket,
    assign_ticket_to_team,
    change_ticket_category,
    change_ticket_status,
    create_blocking_ticket,
    create_ticket_comment,
    create_ticket_service,
    get_blocked_tickets_service,
    get_ticket_detail,
    get_ticket_dependencies_service,
    get_ticket_category_history_service,
    get_ticket_comments,
    get_ticket_team_history_service,
    remove_ticket_dependency,
    unarchive_ticket,
)
from app.core.ticket_rules import (
    can_user_view_assignment_history,
    can_user_view_status_history,
)
from app.services.team_queries import is_team_member

router = APIRouter(prefix="/tickets", tags=["tickets"])
PaginationSkip = Annotated[int, Query(ge=0)]
PaginationLimit = Annotated[int, Query(ge=1, le=100)]


# -----------------------------------------------------------------------------
# Creacion y listados
# -----------------------------------------------------------------------------


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
        .filter(Ticket.created_by == current_user.id, Ticket.archived_at.is_(None))
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
        .filter(Ticket.assigned_to == current_user.id, Ticket.archived_at.is_(None))
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
    query = db.query(Ticket).filter(Ticket.archived_at.is_(None)).order_by(Ticket.created_at.desc())

    if current_user.role == UserRole.AGENT:
        team_ids = select(TeamMember.team_id).where(TeamMember.user_id == current_user.id)
        query = query.filter(
            or_(
                Ticket.assigned_to == current_user.id,
                Ticket.team_id.in_(team_ids),
            )
        )

    return query.offset(skip).limit(limit).all()


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket_detail_endpoint(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Consulta el detalle sin mezclar permisos ni queries en el router."""

    try:
        return get_ticket_detail(db, ticket_id, current_user)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


# -----------------------------------------------------------------------------
# Archivado administrativo
# -----------------------------------------------------------------------------


@router.patch("/{ticket_id}/archive", response_model=TicketRead)
def archive_ticket_endpoint(
    ticket_id: UUID,
    archive_in: TicketArchiveUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    try:
        return archive_ticket(db, ticket_id, current_user, archive_in.reason)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.patch("/{ticket_id}/unarchive", response_model=TicketRead)
def unarchive_ticket_endpoint(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    try:
        return unarchive_ticket(db, ticket_id, current_user)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


# -----------------------------------------------------------------------------
# Operacion del ticket
# -----------------------------------------------------------------------------


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
    except (
        InvalidStatusTransitionError,
        MissingStatusChangeReasonError,
        TicketBlockedByOpenDependenciesError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    

@router.patch("/{ticket_id}/assign-team", response_model=TicketRead)
def ticket_team_assignment(
    ticket_id: UUID,
    assignment: TicketTeamAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    try:
        # ADMIN asigna cualquier team. Un TEAM LEAD solo puede tomar para su
        # equipo tickets sin team y de categorias asociadas a ese team.
        return assign_ticket_to_team(db, ticket_id, assignment.team_id, current_user)
    except (TicketNotFoundError, TicketTeamNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketTeamAssignmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TicketTeamPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.patch("/{ticket_id}/category", response_model=TicketRead)
def update_ticket_category(
    ticket_id: UUID,
    category_update: TicketCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    try:
        # El service decide si el usuario puede recategorizar y limpia team/agente
        # cuando la categoria cambia para no dejar asignaciones inconsistentes.
        return change_ticket_category(
            db,
            ticket_id,
            category_update.category_id,
            current_user,
            category_update.reason,
        )
    except (TicketNotFoundError, TicketCategoryNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (
        InvalidTicketCategoryError,
        InvalidTicketCategoryChangeError,
        MissingCategoryChangeReasonError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


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


# -----------------------------------------------------------------------------
# Dependencias entre tickets
# -----------------------------------------------------------------------------


@router.post("/{ticket_id}/dependencies", response_model=TicketDependencyRead, status_code=201)
def create_ticket_dependency(
    ticket_id: UUID,
    dependency_in: TicketDependencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    try:
        # Vincula el ticket actual con otro ticket existente que lo bloquea.
        return add_ticket_dependency(
            db,
            ticket_id,
            dependency_in.depends_on_ticket_id,
            current_user,
            dependency_in.reason,
        )
    except (TicketNotFoundError, TicketDependencyNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketDependencyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{ticket_id}/dependencies", response_model=list[TicketDependencyRead])
def get_ticket_dependencies(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return get_ticket_dependencies_service(db, ticket_id, current_user)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/{ticket_id}/blocked-tickets", response_model=list[TicketRead])
def get_blocked_tickets(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        # Vista inversa de dependencies: tickets que dependen del ticket actual.
        return get_blocked_tickets_service(db, ticket_id, current_user)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.patch("/{ticket_id}/dependencies/{dependency_id}/remove", response_model=TicketDependencyRead)
def remove_ticket_dependency_endpoint(
    ticket_id: UUID,
    dependency_id: UUID,
    dependency_remove: TicketDependencyRemove,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    try:
        # Soft delete: deja de bloquear, pero conserva quien la removio y por que.
        return remove_ticket_dependency(db, ticket_id, dependency_id, current_user, dependency_remove.reason)
    except (TicketNotFoundError, TicketDependencyNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketDependencyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{ticket_id}/dependencies/create-blocking-ticket", response_model=BlockingTicketRead, status_code=201)
def create_ticket_blocking_ticket(
    ticket_id: UUID,
    blocking_ticket_in: BlockingTicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    try:
        # Crea el ticket bloqueante, crea la dependencia y deja el ticket actual en ON_HOLD.
        return create_blocking_ticket(db, ticket_id, blocking_ticket_in, current_user)
    except (TicketNotFoundError, TicketCategoryNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (TicketDependencyError, InvalidTicketCategoryError, MissingStatusChangeReasonError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


# -----------------------------------------------------------------------------
# Comentarios
# -----------------------------------------------------------------------------


@router.post("/{ticket_id}/comments", response_model=TicketCommentRead, status_code=201)
def create_ticket_comment_endpoint(
    ticket_id: UUID,
    comment_in: TicketCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Recibe la peticion HTTP; permisos y persistencia viven en el service."""

    try:
        return create_ticket_comment(db, ticket_id, comment_in, current_user)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except TicketCommentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{ticket_id}/comments", response_model=list[TicketCommentRead])
def get_ticket_comments_endpoint(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    """Delega al service el acceso y el filtro de comentarios internos."""

    try:
        return get_ticket_comments(db, ticket_id, current_user, skip, limit)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


# -----------------------------------------------------------------------------
# Historiales
# -----------------------------------------------------------------------------


@router.get("/{ticket_id}/status-history", response_model=list[TicketStatusHistoryRead])
def get_ticket_status_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    # Primero validamos que el ticket exista para no devolver un historial vacio
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


@router.get("/{ticket_id}/category-history", response_model=list[TicketCategoryHistoryRead])
def get_ticket_category_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        # Misma idea que assignment/team history: es historial operativo interno.
        return get_ticket_category_history_service(db, ticket_id, current_user)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
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


@router.get("/{ticket_id}/team-history", response_model=list[TicketTeamHistoryRead])
def get_ticket_team_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        # El service resuelve existencia, permisos y consulta del historial.
        return get_ticket_team_history_service(db, ticket_id, current_user)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TicketPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
