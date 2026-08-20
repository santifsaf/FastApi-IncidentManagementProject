from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.category import CategoryTeam, TicketCategory
from app.models.team import Team, TeamMember
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User, UserRole
from app.schemas.category import TicketCategoryCreate


class CategoryServiceError(Exception):
    pass


class InvalidCategoryNameError(CategoryServiceError):
    pass


class CategoryAlreadyExistsError(CategoryServiceError):
    pass


class CategoryNotFoundError(CategoryServiceError):
    pass


class CategoryInactiveError(CategoryServiceError):
    pass


class CategoryTeamAlreadyExistsError(CategoryServiceError):
    pass


class CategoryDataConflictError(CategoryServiceError):
    pass


class CategoryTeamNotFoundError(CategoryServiceError):
    pass


class CategoryPermissionError(CategoryServiceError):
    pass


def _normalize_category_name(name: str) -> str:
    normalized_name = name.strip()
    if not normalized_name:
        raise InvalidCategoryNameError("Category name cannot be empty")

    return normalized_name


def create_category_service(db: Session, category_in: TicketCategoryCreate) -> TicketCategory:
    normalized_name = _normalize_category_name(category_in.name)

    existing_category = (
        db.query(TicketCategory)
        .filter(func.lower(TicketCategory.name) == normalized_name.lower())
        .first()
    )
    if existing_category:
        raise CategoryAlreadyExistsError("Category already exists")

    category = TicketCategory(
        name=normalized_name,
        description=category_in.description,
        is_active=True,
    )

    try:
        db.add(category)
        db.commit()
        db.refresh(category)
        return category
    except IntegrityError as exc:
        db.rollback()
        raise CategoryDataConflictError("The category could not be created because of a data conflict") from exc
    except Exception:
        db.rollback()
        raise


def add_category_team_service(db: Session, category_id: UUID, team_id: UUID) -> CategoryTeam:
    category = db.query(TicketCategory).filter(TicketCategory.id == category_id).first()
    if category is None:
        raise CategoryNotFoundError("Category not found")

    if not category.is_active:
        raise CategoryInactiveError("Inactive categories cannot receive team associations")

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise CategoryTeamNotFoundError("Team not found")

    existing_relation = (
        db.query(CategoryTeam.id)
        .filter(CategoryTeam.category_id == category.id, CategoryTeam.team_id == team.id)
        .first()
    )
    if existing_relation:
        raise CategoryTeamAlreadyExistsError("Team already associated with this category")

    relation = CategoryTeam(category_id=category.id, team_id=team.id)

    try:
        db.add(relation)
        db.commit()
        db.refresh(relation)
        return relation
    except IntegrityError as exc:
        db.rollback()
        raise CategoryTeamAlreadyExistsError("Team already associated with this category") from exc
    except Exception:
        db.rollback()
        raise


def get_category_ticket_queue_service(
    db: Session,
    category_id: UUID,
    current_user: User,
    skip: int = 0,
    limit: int = 20,
) -> list[Ticket]:
    """Devuelve tickets pendientes de asignar a team dentro de una categoria.

    Esta cola es operativa: muestra tickets con categoria definida pero todavia
    sin equipo responsable. La autoasignacion queda para una etapa posterior.
    """

    category = db.query(TicketCategory).filter(TicketCategory.id == category_id).first()
    if category is None:
        raise CategoryNotFoundError("Category not found")

    if current_user.role == UserRole.ADMIN:
        can_view_queue = True
    elif current_user.role == UserRole.AGENT:
        # Un AGENT ve la cola si pertenece a algun team asociado a esta categoria.
        can_view_queue = (
            db.query(CategoryTeam.id)
            .join(TeamMember, TeamMember.team_id == CategoryTeam.team_id)
            .filter(
                CategoryTeam.category_id == category.id,
                TeamMember.user_id == current_user.id,
            )
            .first()
            is not None
        )
    else:
        can_view_queue = False

    if not can_view_queue:
        raise CategoryPermissionError("Not enough permissions to view category ticket queue")

    return (
        db.query(Ticket)
        .filter(
            Ticket.category_id == category.id,
            Ticket.team_id.is_(None),
            Ticket.status != TicketStatus.CLOSED,
            Ticket.archived_at.is_(None),
        )
        # Por ahora priorizamos antiguedad: primero los tickets que mas esperan.
        .order_by(Ticket.created_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
