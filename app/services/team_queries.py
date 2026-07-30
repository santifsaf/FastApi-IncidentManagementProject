from uuid import UUID

from sqlalchemy.orm import Session

from app.models.team import Team, TeamMember


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
    # Un usuario es lead si existe un team con ese id y ese lead_id.
    return (
        db.query(Team.id)
        .filter(Team.id == team_id, Team.lead_id == user_id)
        .first()
        is not None
    )
