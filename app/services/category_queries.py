"""Consultas reutilizables sobre la relación entre categorías y equipos."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.category import CategoryTeam


def is_category_associated_with_team(db: Session, category_id: UUID, team_id: UUID) -> bool:
    """Indica si el equipo está habilitado para atender la categoría."""

    return (
        db.query(CategoryTeam.id)
        .filter(CategoryTeam.category_id == category_id, CategoryTeam.team_id == team_id)
        .first()
        is not None
    )
