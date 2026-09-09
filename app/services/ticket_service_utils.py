"""Utilidades tecnicas compartidas por los services de tickets."""

from typing import TypeVar

from sqlalchemy.orm import Session


Entity = TypeVar("Entity")


def commit_and_refresh(db: Session, entity: Entity) -> Entity:
    """Confirma la transaccion y sincroniza la entidad con la base de datos."""

    try:
        db.commit()
        db.refresh(entity)
        return entity
    except Exception:
        # Un commit fallido deja la sesion inutilizable hasta hacer rollback.
        db.rollback()
        raise


def normalize_optional_reason(reason: str | None) -> str | None:
    """Elimina espacios y representa motivos vacios como None."""

    normalized_reason = reason.strip() if reason else None
    return normalized_reason or None
