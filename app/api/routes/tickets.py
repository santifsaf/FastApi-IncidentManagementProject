"""Endpoints HTTP para el ciclo de vida y la operación de tickets."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_roles
from app.db.session import get_db
from app.models.user import User
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
from app.services.ticket_assignment_service import (
    assign_ticket,
    assign_ticket_to_team,
    change_ticket_category,
    claim_ticket,
    get_ticket_assignment_history_service,
    get_ticket_category_history_service,
    get_ticket_team_history_service,
)
from app.services.ticket_comment_service import create_ticket_comment, get_ticket_comments
from app.services.ticket_dependency_service import (
    add_ticket_dependency,
    create_blocking_ticket,
    get_blocked_tickets_service,
    get_ticket_dependencies_service,
    remove_ticket_dependency,
)
from app.services.ticket_exceptions import (
    AssignedUserNotFoundError,
    TicketCategoryNotFoundError,
    TicketDependencyNotFoundError,
    TicketNotFoundError,
    TicketPermissionError,
    TicketTeamNotFoundError,
    TicketTeamPermissionError,
    TicketServiceError,
)
from app.services.ticket_lifecycle_service import (
    archive_ticket,
    change_ticket_status,
    get_ticket_status_history_service,
    unarchive_ticket,
)
from app.services.ticket_service import (
    create_ticket_service,
    get_ticket_detail,
    get_tickets_assigned_to_user,
    get_tickets_created_by_user,
    get_visible_tickets,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])
PaginationSkip = Annotated[int, Query(ge=0)]
PaginationLimit = Annotated[int, Query(ge=1, le=100)]


TICKET_NOT_FOUND_ERRORS = (
    TicketNotFoundError,
    AssignedUserNotFoundError,
    TicketCategoryNotFoundError,
    TicketDependencyNotFoundError,
    TicketTeamNotFoundError,
)

TICKET_PERMISSION_ERRORS = (
    TicketPermissionError,
    TicketTeamPermissionError,
)


def _ticket_service_error_to_http(exc: TicketServiceError) -> HTTPException:
    """Traduce errores del dominio a respuestas HTTP de forma uniforme."""

    if isinstance(exc, TICKET_NOT_FOUND_ERRORS):
        return HTTPException(status_code=404, detail=str(exc))

    if isinstance(exc, TICKET_PERMISSION_ERRORS):
        return HTTPException(status_code=403, detail=str(exc))

    return HTTPException(status_code=400, detail=str(exc))


# -----------------------------------------------------------------------------
# Creacion y listados
# -----------------------------------------------------------------------------


@router.post("/", response_model=TicketRead, status_code=201)
def create_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Crea un ticket abierto para el usuario autenticado."""

    try:
        return create_ticket_service(db, ticket, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.get("/created-by-me", response_model=list[TicketRead])
def get_tickets_created_by_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    """Lista de forma paginada los tickets creados por el usuario actual."""

    return get_tickets_created_by_user(db, current_user, skip, limit)


@router.get("/assigned-to-me", response_model=list[TicketRead])
def get_tickets_assigned_to_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("AGENT", "ADMIN")),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    """Lista los tickets asignados directamente al usuario operativo actual."""

    try:
        return get_tickets_assigned_to_user(db, current_user, skip, limit)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.get("/", response_model=list[TicketRead])
def get_all_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("AGENT", "ADMIN")),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    """Lista los tickets visibles según el alcance del agente o administrador."""

    try:
        return get_visible_tickets(db, current_user, skip, limit)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket_detail_endpoint(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Devuelve el detalle de un ticket si el usuario puede verlo."""

    try:
        return get_ticket_detail(db, ticket_id, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


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
    """Archiva administrativamente un ticket cerrado."""

    try:
        return archive_ticket(db, ticket_id, current_user, archive_in.reason)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.patch("/{ticket_id}/unarchive", response_model=TicketRead)
def unarchive_ticket_endpoint(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Vuelve a mostrar en las operaciones normales un ticket archivado."""

    try:
        return unarchive_ticket(db, ticket_id, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


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
    """Solicita un cambio de estado y registra su motivo cuando corresponde."""

    try:
        return change_ticket_status(db, ticket_id, ticket_update.status, current_user, ticket_update.reason)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.patch("/{ticket_id}/assign-team", response_model=TicketRead)
def ticket_team_assignment(
    ticket_id: UUID,
    assignment: TicketTeamAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    """Asigna el ticket a un equipo con alcance para atenderlo."""

    try:
        return assign_ticket_to_team(db, ticket_id, assignment.team_id, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.patch("/{ticket_id}/category", response_model=TicketRead)
def update_ticket_category(
    ticket_id: UUID,
    category_update: TicketCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    """Cambia la categoría y exige un motivo de auditoría."""

    try:
        return change_ticket_category(
            db,
            ticket_id,
            category_update.category_id,
            current_user,
            category_update.reason,
        )
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.patch("/{ticket_id}/assign", response_model=TicketRead)
def ticket_assignment(
    ticket_id: UUID,
    assignment: TicketAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    """Asigna como responsable a un miembro activo del equipo del ticket."""

    try:
        return assign_ticket(db, ticket_id, assignment.assigned_to, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.patch("/{ticket_id}/claim", response_model=TicketRead)
def claim_unassigned_ticket(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("AGENT", "ADMIN")),
):
    """Permite a un miembro operativo reclamar un ticket de su equipo."""

    try:
        return claim_ticket(db, ticket_id, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


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
    """Relaciona el ticket con otro ticket existente que lo bloquea."""

    try:
        return add_ticket_dependency(
            db,
            ticket_id,
            dependency_in.depends_on_ticket_id,
            current_user,
            dependency_in.reason,
        )
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.get("/{ticket_id}/dependencies", response_model=list[TicketDependencyRead])
def get_ticket_dependencies(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lista las dependencias activas del ticket."""

    try:
        return get_ticket_dependencies_service(db, ticket_id, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.get("/{ticket_id}/blocked-tickets", response_model=list[TicketRead])
def get_blocked_tickets(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lista los tickets que dependen del ticket actual."""

    try:
        return get_blocked_tickets_service(db, ticket_id, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.patch("/{ticket_id}/dependencies/{dependency_id}/remove", response_model=TicketDependencyRead)
def remove_ticket_dependency_endpoint(
    ticket_id: UUID,
    dependency_id: UUID,
    dependency_remove: TicketDependencyRemove,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    """Desactiva una dependencia y conserva sus datos de auditoría."""

    try:
        return remove_ticket_dependency(db, ticket_id, dependency_id, current_user, dependency_remove.reason)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.post("/{ticket_id}/dependencies/create-blocking-ticket", response_model=BlockingTicketRead, status_code=201)
def create_ticket_blocking_ticket(
    ticket_id: UUID,
    blocking_ticket_in: BlockingTicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "AGENT")),
):
    """Crea el ticket bloqueante y su dependencia en una sola transacción."""

    try:
        return create_blocking_ticket(db, ticket_id, blocking_ticket_in, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


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
    """Publica un comentario con la visibilidad solicitada."""

    try:
        return create_ticket_comment(db, ticket_id, comment_in, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.get("/{ticket_id}/comments", response_model=list[TicketCommentRead])
def get_ticket_comments_endpoint(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    """Lista comentarios paginados y filtra los internos según el usuario."""

    try:
        return get_ticket_comments(db, ticket_id, current_user, skip, limit)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


# -----------------------------------------------------------------------------
# Historiales
# -----------------------------------------------------------------------------


@router.get("/{ticket_id}/status-history", response_model=list[TicketStatusHistoryRead])
def get_ticket_status_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Devuelve el historial de estados visible para el usuario actual."""

    try:
        return get_ticket_status_history_service(db, ticket_id, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.get("/{ticket_id}/category-history", response_model=list[TicketCategoryHistoryRead])
def get_ticket_category_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Devuelve el historial operativo de categorías del ticket."""

    try:
        return get_ticket_category_history_service(db, ticket_id, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.get("/{ticket_id}/assignment-history", response_model=list[TicketAssignmentHistoryRead])
def get_ticket_assignment_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Devuelve el historial operativo de responsables del ticket."""

    try:
        return get_ticket_assignment_history_service(db, ticket_id, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc


@router.get("/{ticket_id}/team-history", response_model=list[TicketTeamHistoryRead])
def get_ticket_team_history(
    ticket_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Devuelve el historial operativo de equipos del ticket."""

    try:
        return get_ticket_team_history_service(db, ticket_id, current_user)
    except TicketServiceError as exc:
        raise _ticket_service_error_to_http(exc) from exc
