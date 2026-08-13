from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.ticket_rules import (
    can_user_assign_ticket,
    can_user_change_status,
    can_user_view_assignment_history,
    is_status_change_reason_required,
    is_valid_status_transition,
)
from app.models.category import TicketCategory
from app.models.team import Team
from app.models.ticket import (
    Ticket,
    TicketAssignmentHistory,
    TicketCategoryHistory,
    TicketDependency,
    TicketStatus,
    TicketStatusHistory,
    TicketTeamHistory,
)
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCreate
from app.services.category_queries import is_category_associated_with_team
from app.services.team_queries import is_team_lead, is_team_member


class TicketServiceError(Exception):
    pass


class TicketNotFoundError(TicketServiceError):
    pass


class AssignedUserNotFoundError(TicketServiceError):
    pass


class TicketPermissionError(TicketServiceError):
    pass


class InvalidStatusTransitionError(TicketServiceError):
    pass


class TicketAlreadyAssignedError(TicketServiceError):
    pass


class MissingStatusChangeReasonError(TicketServiceError):
    pass


class TicketTeamAssignmentError(TicketServiceError):
    pass


class TicketTeamNotFoundError(TicketServiceError):
    pass


class TicketTeamPermissionError(TicketServiceError):
    pass


class InvalidAssignedUserError(TicketServiceError):
    pass


class TicketCategoryNotFoundError(TicketServiceError):
    pass


class InvalidTicketCategoryError(TicketServiceError):
    pass


class InvalidTicketCategoryChangeError(TicketServiceError):
    pass


class MissingCategoryChangeReasonError(TicketServiceError):
    pass


class TicketDependencyError(TicketServiceError):
    pass


class TicketDependencyNotFoundError(TicketServiceError):
    pass


class TicketBlockedByOpenDependenciesError(TicketServiceError):
    pass


def _commit_and_refresh(db: Session, entity):
    try:
        db.commit()
        db.refresh(entity)
        return entity
    except Exception:
        db.rollback()
        raise


def _normalize_optional_reason(reason: str | None) -> str | None:
    normalized_reason = reason.strip() if reason else None
    return normalized_reason or None


def _can_user_manage_ticket_dependencies(db: Session, ticket: Ticket, current_user: User) -> bool:
    if current_user.role == UserRole.ADMIN:
        return True

    if current_user.role != UserRole.AGENT or ticket.team_id is None:
        return False

    # El team lead del equipo actual puede crear dependencias para destrabar el flujo.
    return is_team_lead(db, ticket.team_id, current_user.id)


def _ticket_has_open_dependencies(db: Session, ticket_id: UUID) -> bool:
    """Indica si el ticket depende de otro ticket que todavia no esta cerrado/resuelto."""

    return (
        db.query(TicketDependency.id)
        .join(Ticket, Ticket.id == TicketDependency.depends_on_ticket_id)
        .filter(
            TicketDependency.ticket_id == ticket_id,
            TicketDependency.is_active.is_(True),
            Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED]),
        )
        .first()
        is not None
    )


def _create_ticket_dependency(
    db: Session,
    ticket: Ticket,
    depends_on_ticket: Ticket,
    current_user: User,
    reason: str | None = None,
) -> TicketDependency:
    if ticket.id == depends_on_ticket.id:
        raise TicketDependencyError("A ticket cannot depend on itself")

    if ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise TicketDependencyError("Resolved or closed tickets cannot receive new dependencies")

    if depends_on_ticket.status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
        raise TicketDependencyError("A ticket cannot depend on a resolved or closed ticket")

    existing_dependency = (
        db.query(TicketDependency.id)
        .filter(
            TicketDependency.ticket_id == ticket.id,
            TicketDependency.depends_on_ticket_id == depends_on_ticket.id,
            TicketDependency.is_active.is_(True),
        )
        .first()
    )
    if existing_dependency:
        raise TicketDependencyError("Dependency already exists")

    reverse_dependency = (
        db.query(TicketDependency.id)
        .filter(
            TicketDependency.ticket_id == depends_on_ticket.id,
            TicketDependency.depends_on_ticket_id == ticket.id,
            TicketDependency.is_active.is_(True),
        )
        .first()
    )
    if reverse_dependency:
        raise TicketDependencyError("Circular dependency is not allowed")

    dependency = TicketDependency(
        ticket_id=ticket.id,
        depends_on_ticket_id=depends_on_ticket.id,
        reason=_normalize_optional_reason(reason),
        created_by=current_user.id,
    )
    db.add(dependency)
    return dependency


def _assign_ticket_to_user(db: Session, ticket: Ticket, new_user_id: UUID, changed_by_id: UUID) -> Ticket:
    old_assigned_to = ticket.assigned_to

    if old_assigned_to == new_user_id:
        raise TicketAlreadyAssignedError("Ticket already assigned to this user")

    ticket.assigned_to = new_user_id

    # El historial forma parte de la asignacion: se guarda en la misma transaccion.
    db.add(
        TicketAssignmentHistory(
            ticket_id=ticket.id,
            old_assigned_to=old_assigned_to,
            new_assigned_to=new_user_id,
            changed_by=changed_by_id,
        )
    )

    return _commit_and_refresh(db, ticket)


def create_ticket_service(db: Session, ticket_in: TicketCreate, current_user: User) -> Ticket:
    category = db.query(TicketCategory).filter(TicketCategory.id == ticket_in.category_id).first()
    if category is None:
        raise TicketCategoryNotFoundError("Category not found")

    if not category.is_active:
        raise InvalidTicketCategoryError("Inactive categories cannot be used for new tickets")

    new_ticket = Ticket(
        title=ticket_in.title,
        description=ticket_in.description,
        status=TicketStatus.OPEN,
        priority=ticket_in.priority,
        created_by=current_user.id,
        category_id=category.id,
    )

    try:
        db.add(new_ticket)
        db.commit()
        db.refresh(new_ticket)
        return new_ticket
    except Exception:
        db.rollback()
        raise


def change_ticket_status(db: Session, ticket: Ticket, new_status: TicketStatus, user: User, reason=None) -> Ticket:
    # El service revalida permisos y transiciones para no depender solo del router.
    if not can_user_change_status(user, ticket, new_status):
        raise TicketPermissionError("Not enough permissions to change ticket status")

    if not is_valid_status_transition(ticket.status, new_status):
        raise InvalidStatusTransitionError("Invalid transition")

    if new_status == TicketStatus.RESOLVED and _ticket_has_open_dependencies(db, ticket.id):
        raise TicketBlockedByOpenDependenciesError("Ticket has open dependencies")

    normalized_reason = reason.strip() if reason else None
    if is_status_change_reason_required(ticket.status, new_status) and not normalized_reason:
        raise MissingStatusChangeReasonError("Reason is required for this status change")

    old_status = ticket.status
    ticket.status = new_status

    db.add(
        TicketStatusHistory(
            ticket_id=ticket.id,
            old_status=old_status,
            new_status=new_status,
            reason=normalized_reason,
            changed_by=user.id,
        )
    )

    return _commit_and_refresh(db, ticket)


def assign_ticket_to_team(db: Session, ticket_id: UUID, team_id: UUID, current_user: User) -> Ticket:
    """Asigna un ticket a un equipo y audita el cambio.

    ADMIN puede asignar cualquier equipo. Un TEAM LEAD solo puede llevar a su
    team tickets sin team cuya categoria este asociada a ese team.
    """

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    team = db.query(Team).filter(Team.id == team_id).first()
    if team is None:
        raise TicketTeamNotFoundError("Team not found")

    if ticket.team_id == team.id:
        raise TicketTeamAssignmentError("Ticket already assigned to this team")

    if current_user.role != UserRole.ADMIN:
        if ticket.team_id is not None:
            raise TicketTeamPermissionError("Team lead can only assign tickets without team")

        if not is_team_lead(db, team.id, current_user.id):
            raise TicketTeamPermissionError("Not enough permissions to assign ticket to this team")

        if not is_category_associated_with_team(db, ticket.category_id, team.id):
            raise TicketTeamPermissionError("Ticket category is not associated with this team")

    # Si el ticket ya tiene agente, no permitimos moverlo a un equipo donde
    # ese agente no pertenece. Evita inconsistencias entre team_id y assigned_to.
    if ticket.assigned_to is not None and not is_team_member(db, team.id, ticket.assigned_to):
        raise TicketTeamAssignmentError("Assigned user does not belong to target team")

    old_team_id = ticket.team_id
    ticket.team_id = team.id

    # El cambio de equipo representa responsabilidad operativa, por eso se audita.
    db.add(
        TicketTeamHistory(
            ticket_id=ticket.id,
            old_team_id=old_team_id,
            new_team_id=team.id,
            changed_by=current_user.id,
        )
    )

    return _commit_and_refresh(db, ticket)


def change_ticket_category(
    db: Session,
    ticket_id: UUID,
    new_category_id: UUID,
    current_user: User,
    reason: str | None,
) -> Ticket:
    """Cambia la categoria principal del ticket y deja auditoria completa.

    Recategorizar significa que el equipo/agente actual pueden dejar de
    corresponder, por eso limpiamos team_id y assigned_to dentro de la misma
    transaccion y auditamos esos cambios si existian.
    """

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    new_category = db.query(TicketCategory).filter(TicketCategory.id == new_category_id).first()
    if new_category is None:
        raise TicketCategoryNotFoundError("Category not found")

    if not new_category.is_active:
        raise InvalidTicketCategoryError("Inactive categories cannot be used for tickets")

    if ticket.category_id == new_category.id:
        raise InvalidTicketCategoryChangeError("Ticket already belongs to this category")

    normalized_reason = reason.strip() if reason else None
    if not normalized_reason:
        raise MissingCategoryChangeReasonError("Reason is required for category change")

    if current_user.role == UserRole.ADMIN:
        if ticket.status == TicketStatus.CLOSED:
            raise InvalidTicketCategoryChangeError("Closed tickets cannot change category")
    elif current_user.role == UserRole.AGENT:
        allowed_statuses = {TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.ON_HOLD}
        if ticket.status not in allowed_statuses:
            raise InvalidTicketCategoryChangeError(
                "Category can only be changed while ticket is open, in progress, or on hold"
            )

        if ticket.team_id is None or not is_team_lead(db, ticket.team_id, current_user.id):
            raise TicketPermissionError("Only the current team lead can change ticket category")
    else:
        raise TicketPermissionError("Not enough permissions to change ticket category")

    old_category_id = ticket.category_id
    old_team_id = ticket.team_id
    old_assigned_to = ticket.assigned_to

    ticket.category_id = new_category.id
    ticket.team_id = None
    ticket.assigned_to = None

    db.add(
        TicketCategoryHistory(
            ticket_id=ticket.id,
            old_category_id=old_category_id,
            new_category_id=new_category.id,
            reason=normalized_reason,
            changed_by=current_user.id,
        )
    )

    if old_team_id is not None:
        db.add(
            TicketTeamHistory(
                ticket_id=ticket.id,
                old_team_id=old_team_id,
                new_team_id=None,
                changed_by=current_user.id,
            )
        )

    if old_assigned_to is not None:
        db.add(
            TicketAssignmentHistory(
                ticket_id=ticket.id,
                old_assigned_to=old_assigned_to,
                new_assigned_to=None,
                changed_by=current_user.id,
            )
        )

    return _commit_and_refresh(db, ticket)


def get_ticket_category_history_service(db: Session, ticket_id: UUID, current_user: User) -> list[TicketCategoryHistory]:
    """Devuelve el historial de categoria aplicando permisos de lectura interna."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    current_user_is_team_member = is_team_member(db, ticket.team_id, current_user.id)
    if not can_user_view_assignment_history(current_user, ticket, current_user_is_team_member):
        raise TicketPermissionError("Not enough permissions to view ticket category history")

    return (
        db.query(TicketCategoryHistory)
        .filter(TicketCategoryHistory.ticket_id == ticket_id)
        .order_by(TicketCategoryHistory.changed_at.desc())
        .all()
    )


def get_ticket_team_history_service(db: Session, ticket_id: UUID, current_user: User) -> list[TicketTeamHistory]:
    """Devuelve el historial de equipos de un ticket aplicando permisos.

    El router no deberia conocer esta regla porque pertenece al caso de uso:
    primero se valida que el ticket exista, despues que el usuario pueda verlo.
    """

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    current_user_is_team_member = is_team_member(db, ticket.team_id, current_user.id)
    if not can_user_view_assignment_history(current_user, ticket, current_user_is_team_member):
        raise TicketPermissionError("Not enough permissions to view ticket team history")

    return (
        db.query(TicketTeamHistory)
        .filter(TicketTeamHistory.ticket_id == ticket_id)
        .order_by(TicketTeamHistory.changed_at.desc())
        .all()
    )


def add_ticket_dependency(
    db: Session,
    ticket_id: UUID,
    depends_on_ticket_id: UUID,
    current_user: User,
    reason: str | None = None,
) -> TicketDependency:
    """Vincula el ticket actual con otro ticket existente que lo bloquea."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    depends_on_ticket = db.query(Ticket).filter(Ticket.id == depends_on_ticket_id).first()
    if depends_on_ticket is None:
        raise TicketDependencyNotFoundError("Blocking ticket not found")

    if not _can_user_manage_ticket_dependencies(db, ticket, current_user):
        raise TicketPermissionError("Not enough permissions to manage ticket dependencies")

    dependency = _create_ticket_dependency(db, ticket, depends_on_ticket, current_user, reason)

    return _commit_and_refresh(db, dependency)


def get_ticket_dependencies_service(db: Session, ticket_id: UUID, current_user: User) -> list[TicketDependency]:
    """Lista los tickets de los que depende el ticket actual."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    current_user_is_team_member = is_team_member(db, ticket.team_id, current_user.id)
    if not can_user_view_assignment_history(current_user, ticket, current_user_is_team_member):
        raise TicketPermissionError("Not enough permissions to view ticket dependencies")

    return (
        db.query(TicketDependency)
        .filter(TicketDependency.ticket_id == ticket.id, TicketDependency.is_active.is_(True))
        .order_by(TicketDependency.created_at.desc())
        .all()
    )


def get_blocked_tickets_service(db: Session, ticket_id: UUID, current_user: User) -> list[Ticket]:
    """Lista tickets que estan bloqueados por el ticket actual.

    Es la vista inversa de dependencies: si A depende de B, entonces B tiene a
    A como blocked ticket. Solo devolvemos relaciones activas y tickets aun no
    resueltos/cerrados porque esos son los que siguen bloqueados operativamente.
    """

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    current_user_is_team_member = is_team_member(db, ticket.team_id, current_user.id)
    if not can_user_view_assignment_history(current_user, ticket, current_user_is_team_member):
        raise TicketPermissionError("Not enough permissions to view blocked tickets")

    return (
        db.query(Ticket)
        .join(TicketDependency, TicketDependency.ticket_id == Ticket.id)
        .filter(
            TicketDependency.depends_on_ticket_id == ticket.id,
            TicketDependency.is_active.is_(True),
            Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED]),
        )
        .order_by(Ticket.created_at.desc())
        .all()
    )


def remove_ticket_dependency(
    db: Session,
    ticket_id: UUID,
    dependency_id: UUID,
    current_user: User,
    reason: str | None,
) -> TicketDependency:
    """Marca una dependencia como removida sin borrarla de la base.

    Buscamos por dependency_id y ticket_id juntos para no borrar por error una
    dependencia que pertenezca a otro ticket. El motivo queda auditado.
    """

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    if not _can_user_manage_ticket_dependencies(db, ticket, current_user):
        raise TicketPermissionError("Not enough permissions to manage ticket dependencies")

    dependency = (
        db.query(TicketDependency)
        .filter(
            TicketDependency.id == dependency_id,
            TicketDependency.ticket_id == ticket.id,
            TicketDependency.is_active.is_(True),
        )
        .first()
    )
    if dependency is None:
        raise TicketDependencyNotFoundError("Dependency not found")

    normalized_reason = _normalize_optional_reason(reason)
    if not normalized_reason:
        raise TicketDependencyError("Reason is required to remove dependency")

    dependency.is_active = False
    dependency.removed_by = current_user.id
    dependency.removed_at = func.now()
    dependency.removed_reason = normalized_reason

    # Ya no llamamos db.delete(): la fila queda como historial auditable.
    return _commit_and_refresh(db, dependency)


def create_blocking_ticket(
    db: Session,
    ticket_id: UUID,
    blocking_ticket_in,
    current_user: User,
) -> dict:
    """Crea un ticket bloqueante y deja el ticket actual en ON_HOLD.

    Todo se hace en una sola transaccion: nuevo ticket, dependencia y cambio de
    estado. Si falla una parte, no queda el flujo a medio crear.
    """

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    if not _can_user_manage_ticket_dependencies(db, ticket, current_user):
        raise TicketPermissionError("Not enough permissions to manage ticket dependencies")

    normalized_reason = _normalize_optional_reason(blocking_ticket_in.reason)
    if not normalized_reason:
        raise MissingStatusChangeReasonError("Reason is required to create a blocking ticket")

    category = db.query(TicketCategory).filter(TicketCategory.id == blocking_ticket_in.category_id).first()
    if category is None:
        raise TicketCategoryNotFoundError("Category not found")

    if not category.is_active:
        raise InvalidTicketCategoryError("Inactive categories cannot be used for new tickets")

    blocking_ticket = Ticket(
        title=blocking_ticket_in.title,
        description=blocking_ticket_in.description,
        status=TicketStatus.OPEN,
        priority=blocking_ticket_in.priority,
        created_by=current_user.id,
        category_id=category.id,
    )
    db.add(blocking_ticket)
    # flush ejecuta el INSERT dentro de la transaccion para que blocking_ticket.id exista,
    # pero todavia no confirma nada. Si luego falla algo, el rollback revierte todo.
    db.flush()

    dependency = _create_ticket_dependency(db, ticket, blocking_ticket, current_user, normalized_reason)

    if ticket.status != TicketStatus.ON_HOLD:
        old_status = ticket.status
        ticket.status = TicketStatus.ON_HOLD
        db.add(
            TicketStatusHistory(
                ticket_id=ticket.id,
                old_status=old_status,
                new_status=TicketStatus.ON_HOLD,
                reason=normalized_reason,
                changed_by=current_user.id,
            )
        )

    try:
        db.commit()
        db.refresh(ticket)
        db.refresh(blocking_ticket)
        db.refresh(dependency)
        return {
            "current_ticket": ticket,
            "blocking_ticket": blocking_ticket,
            "dependency": dependency,
        }
    except Exception:
        db.rollback()
        raise


def assign_ticket(db: Session, ticket_id: UUID, assigned_user_id: UUID, current_user: User) -> Ticket:
    """Asigna un ticket a un agente.

    ADMIN puede asignar libremente. Un AGENT solo puede hacerlo si es lead
    del equipo del ticket y el agente destino pertenece al mismo equipo.
    """

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    assigned_user = db.query(User).filter(User.id == assigned_user_id).first()
    if assigned_user is None:
        raise AssignedUserNotFoundError("Assigned user not found")

    if not assigned_user.is_active:
        raise InvalidAssignedUserError("Assigned user must be active")

    is_current_user_team_lead = False
    is_assigned_user_team_member = False

    if ticket.team_id is not None:
        is_current_user_team_lead = is_team_lead(db, ticket.team_id, current_user.id)
        is_assigned_user_team_member = is_team_member(db, ticket.team_id, assigned_user.id)

    if not can_user_assign_ticket(
        current_user,
        assigned_user,
        ticket,
        is_current_user_team_lead,
        is_assigned_user_team_member,
    ):
        raise TicketPermissionError("Not enough permissions or invalid assignment")

    return _assign_ticket_to_user(db, ticket, assigned_user.id, current_user.id)
