"""Consultas reutilizables sobre membresías y liderazgo de equipos."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.team import TeamLead, TeamMember


def is_team_member(db: Session, team_id: UUID | None, user_id: UUID) -> bool:
    """Indica si el usuario pertenece al equipo; ``None`` nunca es un equipo válido."""

    if team_id is None:
        return False

    return (
        db.query(TeamMember.id)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .first()
        is not None
    )


def is_team_lead(db: Session, team_id: UUID, user_id: UUID) -> bool:
    """Consulta TeamLead, la fuente de verdad para el liderazgo del equipo."""

    return (
        db.query(TeamLead.id)
        .filter(TeamLead.team_id == team_id, TeamLead.user_id == user_id)
        .first()
        is not None
    )
