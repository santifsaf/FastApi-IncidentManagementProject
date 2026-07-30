from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.category import CategoryTeam, TicketCategory
from app.models.team import Team
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
