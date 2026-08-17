from uuid import UUID

from sqlalchemy.orm import Session

from app.models.team import TeamLead, TeamMember


def is_team_member(db: Session, team_id: UUID | None, user_id: UUID) -> bool:
    if team_id is None:
        return False

    # Consultamos solo el id porque no necesitamos cargar el objeto completo.
    return (
        db.query(TeamMember.id)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .first()
        is not None
    )


def is_team_lead(db: Session, team_id: UUID, user_id: UUID) -> bool:
    # TeamLead es la fuente de verdad: si existe esta fila, el usuario opera como lead.
    return (
        db.query(TeamLead.id)
        .filter(TeamLead.team_id == team_id, TeamLead.user_id == user_id)
        .first()
        is not None
    )
