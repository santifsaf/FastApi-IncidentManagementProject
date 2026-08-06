from uuid import UUID

from sqlalchemy.orm import Session

from app.models.category import CategoryTeam


def is_category_associated_with_team(db: Session, category_id: UUID, team_id: UUID) -> bool:
    # Consultamos solo el id porque alcanza con saber si la relacion existe.
    return (
        db.query(CategoryTeam.id)
        .filter(CategoryTeam.category_id == category_id, CategoryTeam.team_id == team_id)
        .first()
        is not None
    )
