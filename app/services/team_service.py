"""Casos de uso para equipos, miembros, leads y políticas de asignación."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.team import AssignmentStrategy, Team, TeamLead, TeamMember
from app.models.user import User, UserRole
from app.schemas.team import TeamCreate


# Un lead puede ser un agente operativo o un administrador que tambien
# coordina el trabajo cotidiano de un equipo.
TEAM_LEAD_ROLES = {UserRole.AGENT, UserRole.ADMIN}

# La membresia indica que el usuario trabaja en el equipo; no implica que lo lidere.
TEAM_MEMBER_ROLES = {UserRole.AGENT, UserRole.ADMIN}


class TeamServiceError(Exception):
    pass


class TeamNotFoundError(TeamServiceError):
    pass


class TeamLeadNotFoundError(TeamServiceError):
    pass


class InvalidTeamLeadError(TeamServiceError):
    pass


class TeamAlreadyExistsError(TeamServiceError):
    pass


class InvalidTeamNameError(TeamServiceError):
    pass


class UserNotFoundError(TeamServiceError):
    pass


class InvalidTeamMemberError(TeamServiceError):
    pass


class TeamMemberAlreadyExistsError(TeamServiceError):
    pass


class TeamMemberNotFoundError(TeamServiceError):
    pass


class TeamLeadRemovalError(TeamServiceError):
    pass


class TeamLeadAlreadyExistsError(TeamServiceError):
    pass


class TeamDataConflictError(TeamServiceError):
    pass


class InvalidTeamAssignmentSettingsError(TeamServiceError):
    pass


def _normalize_team_name(name: str) -> str:
    normalized_name = name.strip()
    if not normalized_name:
        raise InvalidTeamNameError("Team name cannot be empty")

    return normalized_name


def create_team_service(db: Session, team_in: TeamCreate) -> Team:
    """Crea un equipo y registra su primer lead.

    Esta funcion representa el caso de uso completo: normaliza el nombre,
    busca el lead inicial, valida que sea AGENT o ADMIN activo y persiste todo junto.
    El lead vive en TeamLead; Team ya no guarda una columna lead_id propia.
    """

    normalized_name = _normalize_team_name(team_in.name)

    existing_team = db.query(Team).filter(Team.name == normalized_name).first()
    if existing_team:
        raise TeamAlreadyExistsError("Team already exists")

    lead_user = db.query(User).filter(User.id == team_in.lead_id).first()
    if lead_user is None:
        raise TeamLeadNotFoundError("Team lead not found")

    if lead_user.role not in TEAM_LEAD_ROLES:
        raise InvalidTeamLeadError("Team lead must be an agent or administrator")

    if not lead_user.is_active:
        raise InvalidTeamLeadError("Inactive users cannot lead a team")

    team = Team(
        name=normalized_name,
        self_assignment_enabled=team_in.self_assignment_enabled,
    )

    try:
        db.add(team)
        db.flush()

        # Crear team, lead y miembro en la misma transaccion evita equipos
        # incompletos si falla una de las operaciones.
        db.add(TeamLead(team_id=team.id, user_id=lead_user.id))
        db.add(TeamMember(team_id=team.id, user_id=lead_user.id))
        db.commit()
        db.refresh(team)
        return team
    except IntegrityError as exc:
        db.rollback()
        raise TeamDataConflictError("The team could not be created because of a data conflict") from exc
    except Exception:
        db.rollback()
        raise


def add_team_lead_service(db: Session, team_id: UUID, user_id: UUID) -> TeamLead:
    """Agrega un lead al equipo.

    Todo lead tambien debe ser miembro. Por eso, si todavia no existe la
    membresia, se crea dentro de la misma transaccion.
    """

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise TeamNotFoundError("Team not found")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise UserNotFoundError("User not found")

    if user.role not in TEAM_LEAD_ROLES:
        raise InvalidTeamLeadError("Team lead must be an agent or administrator")

    if not user.is_active:
        raise InvalidTeamLeadError("Inactive users cannot lead a team")

    existing_lead = (
        db.query(TeamLead.id)
        .filter(TeamLead.team_id == team.id, TeamLead.user_id == user.id)
        .first()
    )
    if existing_lead:
        raise TeamLeadAlreadyExistsError("User already leads this team")

    lead = TeamLead(team_id=team.id, user_id=user.id)

    existing_member = (
        db.query(TeamMember.id)
        .filter(TeamMember.team_id == team.id, TeamMember.user_id == user.id)
        .first()
    )

    try:
        db.add(lead)
        # Todo lead tambien debe ser miembro del equipo.
        if not existing_member:
            db.add(TeamMember(team_id=team.id, user_id=user.id))
        db.commit()
        db.refresh(lead)
        return lead
    except IntegrityError as exc:
        db.rollback()
        raise TeamLeadAlreadyExistsError("User already leads this team") from exc
    except Exception:
        db.rollback()
        raise


def get_team_leads_service(db: Session, team_id: UUID) -> list[TeamLead]:
    """Lista los leads del equipo en el orden en que fueron incorporados."""

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise TeamNotFoundError("Team not found")

    return (
        db.query(TeamLead)
        .filter(TeamLead.team_id == team.id)
        .order_by(TeamLead.created_at.asc())
        .all()
    )


def update_team_self_assignment_service(db: Session, team_id: UUID, enabled: bool) -> Team:
    """Activa o desactiva el reclamo voluntario de tickets para un equipo."""

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise TeamNotFoundError("Team not found")

    team.self_assignment_enabled = enabled
    try:
        db.commit()
        db.refresh(team)
        return team
    except Exception:
        db.rollback()
        raise


def update_team_auto_assignment_service(
    db: Session,
    team_id: UUID,
    enabled: bool,
    delay_minutes: int,
    strategy: AssignmentStrategy,
) -> Team:
    """Configura si, cuando y con que criterio se autoasigna el team."""

    if delay_minutes < 0:
        raise InvalidTeamAssignmentSettingsError("Auto-assignment delay cannot be negative")

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise TeamNotFoundError("Team not found")

    team.auto_assignment_enabled = enabled
    team.auto_assignment_delay_minutes = delay_minutes
    team.assignment_strategy = strategy

    try:
        db.commit()
        db.refresh(team)
        return team
    except Exception:
        db.rollback()
        raise


def remove_team_lead_service(db: Session, team_id: UUID, user_id: UUID) -> None:
    """Quita un lead sin permitir que el equipo quede sin responsables.

    Como TeamLead es la fuente de verdad, antes de borrar validamos que exista
    mas de un lead en el equipo.
    """

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise TeamNotFoundError("Team not found")

    lead = (
        db.query(TeamLead)
        .filter(TeamLead.team_id == team.id, TeamLead.user_id == user_id)
        .first()
    )
    if lead is None:
        raise TeamLeadNotFoundError("Team lead not found")

    lead_count = db.query(TeamLead.id).filter(TeamLead.team_id == team.id).count()
    if lead_count <= 1:
        raise TeamLeadRemovalError("Team must have at least one lead")

    try:
        db.delete(lead)
        db.commit()
    except Exception:
        db.rollback()
        raise


def add_team_member_service(db: Session, team_id: UUID, user_id: UUID) -> TeamMember:
    """Agrega un AGENT o ADMIN activo a un equipo existente."""

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise TeamNotFoundError("Team not found")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise UserNotFoundError("User not found")

    if user.role not in TEAM_MEMBER_ROLES:
        raise InvalidTeamMemberError("Team member must be an agent or administrator")

    if not user.is_active:
        raise InvalidTeamMemberError("Inactive users cannot join a team")

    existing_member = (
        db.query(TeamMember.id)
        .filter(TeamMember.team_id == team.id, TeamMember.user_id == user.id)
        .first()
    )
    if existing_member:
        raise TeamMemberAlreadyExistsError("User already belongs to this team")

    member = TeamMember(team_id=team.id, user_id=user.id)

    try:
        db.add(member)
        db.commit()
        db.refresh(member)
        return member
    except IntegrityError as exc:
        db.rollback()
        raise TeamMemberAlreadyExistsError("User already belongs to this team") from exc
    except Exception:
        db.rollback()
        raise


def remove_team_member_service(db: Session, team_id: UUID, user_id: UUID) -> None:
    """Quita un miembro sin permitir romper la regla de lead obligatorio."""

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise TeamNotFoundError("Team not found")

    existing_lead = (
        db.query(TeamLead.id)
        .filter(TeamLead.team_id == team.id, TeamLead.user_id == user_id)
        .first()
    )
    if existing_lead:
        raise TeamLeadRemovalError("Team lead cannot be removed from the team")

    member = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team.id, TeamMember.user_id == user_id)
        .first()
    )
    if not member:
        raise TeamMemberNotFoundError("Team member not found")

    try:
        db.delete(member)
        db.commit()
    except Exception:
        db.rollback()
        raise
