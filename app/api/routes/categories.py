from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, require_roles
from app.db.session import get_db
from app.models.category import TicketCategory
from app.models.user import User, UserRole
from app.schemas.category import (
    CategoryTeamCreate,
    CategoryTeamRead,
    TicketCategoryCreate,
    TicketCategoryRead,
)
from app.schemas.ticket import TicketRead
from app.services.category_service import (
    CategoryAlreadyExistsError,
    CategoryDataConflictError,
    CategoryInactiveError,
    CategoryNotFoundError,
    CategoryPermissionError,
    CategoryServiceError,
    CategoryTeamAlreadyExistsError,
    CategoryTeamNotFoundError,
    InvalidCategoryNameError,
    add_category_team_service,
    create_category_service,
    get_category_ticket_queue_service,
)

router = APIRouter(prefix="/ticket-categories", tags=["ticket-categories"])
PaginationSkip = Annotated[int, Query(ge=0)]
PaginationLimit = Annotated[int, Query(ge=1, le=100)]


def _category_service_error_to_http(exc: CategoryServiceError) -> HTTPException:
    if isinstance(exc, (CategoryNotFoundError, CategoryTeamNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))

    if isinstance(exc, CategoryPermissionError):
        return HTTPException(status_code=403, detail=str(exc))

    if isinstance(exc, (CategoryAlreadyExistsError, CategoryTeamAlreadyExistsError, CategoryDataConflictError)):
        return HTTPException(status_code=409, detail=str(exc))

    if isinstance(exc, (InvalidCategoryNameError, CategoryInactiveError)):
        return HTTPException(status_code=400, detail=str(exc))

    return HTTPException(status_code=400, detail=str(exc))


@router.post("/", response_model=TicketCategoryRead, status_code=201)
def create_category(
    category_in: TicketCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    try:
        # Las categorias las administra ADMIN; el service valida nombre y duplicados.
        return create_category_service(db, category_in)
    except CategoryServiceError as exc:
        raise _category_service_error_to_http(exc) from exc


@router.get("/", response_model=list[TicketCategoryRead])
def get_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
    include_inactive: bool = False,
):
    # Los usuarios activos necesitan ver categorias para crear tickets.
    # Solo ADMIN puede pedir tambien categorias inactivas.
    query = db.query(TicketCategory).order_by(TicketCategory.name)

    if current_user.role != UserRole.ADMIN or not include_inactive:
        query = query.filter(TicketCategory.is_active.is_(True))

    return query.offset(skip).limit(limit).all()


@router.get("/{category_id}/ticket-queue", response_model=list[TicketRead])
def get_category_ticket_queue(
    category_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    skip: PaginationSkip = 0,
    limit: PaginationLimit = 20,
):
    try:
        # Cola manual: tickets de la categoria que todavia no tienen team.
        # La autoasignacion de team queda para una etapa posterior.
        return get_category_ticket_queue_service(db, category_id, current_user, skip, limit)
    except CategoryServiceError as exc:
        raise _category_service_error_to_http(exc) from exc


@router.post("/{category_id}/teams", response_model=CategoryTeamRead, status_code=201)
def add_category_team(
    category_id: UUID,
    category_team_in: CategoryTeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    try:
        # Esta asociacion define que un team atiende una categoria,
        # pero no asigna automaticamente tickets a ese team todavia.
        return add_category_team_service(db, category_id, category_team_in.team_id)
    except CategoryServiceError as exc:
        raise _category_service_error_to_http(exc) from exc
