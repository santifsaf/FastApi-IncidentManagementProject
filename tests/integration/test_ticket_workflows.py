"""Flujos criticos de tickets ejecutados contra PostgreSQL real."""

from uuid import uuid4

import pytest

from app.models.category import TicketCategory
from app.models.team import Team, TeamMember
from app.models.ticket import (
    Ticket,
    TicketCommentVisibility,
    TicketDependency,
    TicketStatus,
    TicketStatusHistory,
)
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCommentCreate, TicketCreate
from app.services.ticket_service import (
    TicketBlockedByOpenDependenciesError,
    TicketPermissionError,
    add_ticket_dependency,
    change_ticket_status,
    create_ticket_comment,
    create_ticket_service,
    get_ticket_comments,
    get_ticket_detail,
)


# Marca todos los tests del archivo para poder incluirlos o excluirlos con -m.
pytestmark = pytest.mark.integration


def _create_user(db, role: UserRole) -> User:
    """Inserta un usuario minimo y deja disponible su UUID sin hacer commit."""

    user = User(
        # El UUID en el email evita colisiones entre ejecuciones o tests.
        email=f"{uuid4()}@example.com",
        password_hash="hash-de-test",
        role=role,
        is_active=True,
    )
    db.add(user)
    # flush ejecuta el INSERT dentro de la transaccion actual y asigna user.id.
    db.flush()
    return user


def _create_category(db) -> TicketCategory:
    """Inserta una categoria activa requerida por los tickets de prueba."""

    category = TicketCategory(name=f"Categoria {uuid4()}", is_active=True)
    db.add(category)
    db.flush()
    return category


def _create_ticket(db, creator: User, category: TicketCategory, **overrides) -> Ticket:
    """Crea un ticket base y permite reemplazar campos para cada escenario."""

    values = {
        "title": "Ticket de integracion",
        "description": "Comprueba persistencia real",
        "status": TicketStatus.OPEN,
        "created_by": creator.id,
        "category_id": category.id,
    }
    # Ejemplo: assigned_to=agent.id reemplaza solo ese campo del escenario base.
    values.update(overrides)
    ticket = Ticket(**values)
    db.add(ticket)
    db.flush()
    return ticket


def test_create_ticket_persists_server_managed_fields(integration_db):
    """El service completa estado, creador y fecha usando PostgreSQL real."""

    # Preparacion: entidades que el caso de uso necesita por foreign key.
    user = _create_user(integration_db, UserRole.USER)
    category = _create_category(integration_db)

    # Ejecucion: se usa TicketCreate y el service real, incluido su commit().
    ticket = create_ticket_service(
        integration_db,
        TicketCreate(
            title="Error de login",
            description="No puedo ingresar",
            category_id=category.id,
        ),
        user,
    )

    # Verificacion: el objeto confirmado conserva los valores del servidor.
    persisted_ticket = integration_db.get(Ticket, ticket.id)
    assert persisted_ticket is not None
    assert persisted_ticket.status == TicketStatus.OPEN
    assert persisted_ticket.created_by == user.id
    assert persisted_ticket.category_id == category.id
    assert persisted_ticket.created_at is not None


def test_team_member_can_read_ticket_detail(integration_db):
    """Comprueba la consulta real de membresia usada por el service."""

    creator = _create_user(integration_db, UserRole.USER)
    agent = _create_user(integration_db, UserRole.AGENT)
    category = _create_category(integration_db)
    team = Team(name=f"Team {uuid4()}")
    integration_db.add(team)
    integration_db.flush()
    integration_db.add(TeamMember(team_id=team.id, user_id=agent.id))
    integration_db.flush()
    ticket = _create_ticket(integration_db, creator, category, team_id=team.id)

    result = get_ticket_detail(integration_db, ticket.id, agent)

    assert result.id == ticket.id


def test_unrelated_user_cannot_read_ticket_detail(integration_db):
    creator = _create_user(integration_db, UserRole.USER)
    unrelated_user = _create_user(integration_db, UserRole.USER)
    category = _create_category(integration_db)
    ticket = _create_ticket(integration_db, creator, category)

    with pytest.raises(TicketPermissionError, match="Not enough permissions to view ticket"):
        get_ticket_detail(integration_db, ticket.id, unrelated_user)


def test_status_change_persists_ticket_and_history_atomically(integration_db):
    """Un cambio valido actualiza el ticket y genera su evento de auditoria."""

    # El AGENT debe estar asignado directamente para poder cambiar el estado.
    agent = _create_user(integration_db, UserRole.AGENT)
    category = _create_category(integration_db)
    team = Team(name=f"Team {uuid4()}")
    integration_db.add(team)
    integration_db.flush()
    integration_db.add(TeamMember(team_id=team.id, user_id=agent.id))
    integration_db.flush()
    ticket = _create_ticket(
        integration_db,
        agent,
        category,
        team_id=team.id,
        assigned_to=agent.id,
    )

    result = change_ticket_status(
        integration_db,
        ticket,
        TicketStatus.IN_PROGRESS,
        agent,
    )

    # Esta consulta real comprueba que el service inserto la fila de historial.
    history = (
        integration_db.query(TicketStatusHistory)
        .filter(TicketStatusHistory.ticket_id == ticket.id)
        .one()
    )
    assert result.status == TicketStatus.IN_PROGRESS
    assert history.old_status == TicketStatus.OPEN
    assert history.new_status == TicketStatus.IN_PROGRESS
    assert history.changed_by == agent.id
    assert history.changed_at is not None


def test_open_dependency_prevents_resolving_ticket(integration_db):
    """Una dependencia activa impide resolver el ticket que esta bloqueado."""

    admin = _create_user(integration_db, UserRole.ADMIN)
    category = _create_category(integration_db)
    blocked_ticket = _create_ticket(
        integration_db,
        admin,
        category,
        status=TicketStatus.IN_PROGRESS,
    )
    blocking_ticket = _create_ticket(integration_db, admin, category)

    # blocked_ticket no puede resolverse mientras blocking_ticket siga abierto.
    dependency = add_ticket_dependency(
        integration_db,
        blocked_ticket.id,
        blocking_ticket.id,
        admin,
        reason="Falta resolver el ticket bloqueante",
    )

    # Esperamos una excepcion de dominio, no una respuesta HTTP del router.
    with pytest.raises(TicketBlockedByOpenDependenciesError):
        change_ticket_status(
            integration_db,
            blocked_ticket,
            TicketStatus.RESOLVED,
            admin,
        )

    # El intento fallido no elimina la dependencia ni cambia el estado actual.
    persisted_dependency = integration_db.get(TicketDependency, dependency.id)
    assert persisted_dependency is not None
    assert persisted_dependency.is_active is True
    assert blocked_ticket.status == TicketStatus.IN_PROGRESS


def test_requester_receives_only_public_comments(integration_db):
    """El filtro de visibilidad se comprueba con consultas SQL reales."""

    requester = _create_user(integration_db, UserRole.USER)
    admin = _create_user(integration_db, UserRole.ADMIN)
    category = _create_category(integration_db)
    ticket = _create_ticket(integration_db, requester, category)

    public_comment = create_ticket_comment(
        integration_db,
        ticket.id,
        TicketCommentCreate(
            body="Respuesta visible para el solicitante",
            visibility=TicketCommentVisibility.REQUESTER_VISIBLE,
        ),
        requester,
    )
    create_ticket_comment(
        integration_db,
        ticket.id,
        TicketCommentCreate(
            body="Nota operativa que el solicitante no debe ver",
            visibility=TicketCommentVisibility.INTERNAL,
        ),
        admin,
    )

    requester_comments = get_ticket_comments(integration_db, ticket.id, requester)
    admin_comments = get_ticket_comments(integration_db, ticket.id, admin)

    assert [comment.id for comment in requester_comments] == [public_comment.id]
    assert len(admin_comments) == 2
