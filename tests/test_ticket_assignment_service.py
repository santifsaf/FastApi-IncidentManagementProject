"""Tests unitarios de asignacion, equipos y categorias de tickets."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.ticket import (
    TicketAssignmentHistory,
    TicketCategoryHistory,
    TicketStatus,
    TicketTeamHistory,
)
from app.services.ticket_assignment_service import (
    assign_ticket,
    assign_ticket_to_team,
    change_ticket_category,
)
from app.services.ticket_exceptions import (
    InvalidAssignedUserError,
    InvalidTicketCategoryChangeError,
    InvalidTicketCategoryError,
    MissingCategoryChangeReasonError,
    TicketAlreadyAssignedError,
    TicketPermissionError,
    TicketTeamAssignmentError,
    TicketTeamPermissionError,
)
from tests.ticket_service_fakes import FailingTeamAwareFakeDb, TeamAwareFakeDb


def test_assign_ticket_updates_ticket_and_creates_history():
    """
    Caso exitoso:
    - Un ADMIN asigna un ticket a un AGENT.
    - El ticket cambia su assigned_to.
    - Se crea un registro en TicketAssignmentHistory.
    - Se confirma la transaccion.
    """

    # Simulamos que el ticket ya estaba asignado a otro usuario.
    old_assigned_id = uuid4()

    # SimpleNamespace crea objetos simples con atributos.
    # Lo usamos para no depender de SQLAlchemy ni de una base real.
    team_id = uuid4()
    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=old_assigned_id,
        team_id=team_id,
    )

    # Usuario que realiza la accion.
    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    # Usuario destino de la asignacion.
    assigned_user = SimpleNamespace(
        id=uuid4(),
        role="AGENT",
        is_active=True,
    )
    db = TeamAwareFakeDb(
        ticket=ticket,
        assigned_user=assigned_user,
        member=SimpleNamespace(team_id=team_id, user_id=assigned_user.id),
    )

    result = assign_ticket(db, ticket.id, assigned_user.id, current_user)

    # El service devuelve el mismo ticket que recibio, pero actualizado.
    assert result is ticket

    # assigned_to debe pasar a ser el ID del nuevo agente.
    assert ticket.assigned_to == assigned_user.id

    # El service debe confirmar la operacion.
    assert db.committed is True

    # El service debe refrescar el ticket despues del commit.
    assert db.refreshed is ticket

    assert db.rolled_back is False

    # El service deberia agregar un solo objeto: el historial.
    assert len(db.added) == 1

    history = db.added[0]

    # Confirmamos que lo agregado sea un historial de asignacion.
    assert isinstance(history, TicketAssignmentHistory)

    # El historial debe apuntar al ticket modificado.
    assert history.ticket_id == ticket.id

    # Debe guardar quien tenia el ticket antes.
    assert history.old_assigned_to == old_assigned_id

    # Debe guardar quien quedo asignado ahora.
    assert history.new_assigned_to == assigned_user.id

    # Debe guardar quien hizo el cambio.
    assert history.changed_by == current_user.id


def test_cannot_assign_teamless_ticket_to_active_admin():
    ticket = SimpleNamespace(id=uuid4(), assigned_to=None, team_id=None)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    assigned_admin = SimpleNamespace(id=uuid4(), role="ADMIN", is_active=True)
    db = TeamAwareFakeDb(ticket=ticket, assigned_user=assigned_admin)

    with pytest.raises(TicketTeamAssignmentError, match="must belong to a team"):
        assign_ticket(db, ticket.id, assigned_admin.id, current_user)

    assert ticket.assigned_to is None
    assert db.added == []
    assert db.committed is False


def test_assign_ticket_raises_permission_error_when_user_cannot_assign():
    """
    Caso invalido:
    - Un USER intenta asignar un ticket.
    - La regla no lo permite.
    - El service lanza TicketPermissionError.
    - No modifica el ticket.
    - No crea historial.
    """

    team_id = uuid4()
    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=None,
        team_id=team_id,
    )

    current_user = SimpleNamespace(
        id=uuid4(),
        role="USER",
    )

    assigned_user = SimpleNamespace(
        id=uuid4(),
        role="AGENT",
        is_active=True,
    )
    db = TeamAwareFakeDb(
        ticket=ticket,
        assigned_user=assigned_user,
        member=SimpleNamespace(team_id=team_id, user_id=assigned_user.id),
    )

    with pytest.raises(TicketPermissionError):
        assign_ticket(db, ticket.id, assigned_user.id, current_user)

    # Como fallo por permisos, el ticket no deberia modificarse.
    assert ticket.assigned_to is None

    # No deberia haberse creado historial.
    assert db.added == []

    # No deberia confirmarse ninguna transaccion.
    assert db.committed is False

    # No deberia refrescarse el ticket.
    assert db.refreshed is None

    assert db.rolled_back is False


def test_assign_ticket_raises_value_error_when_agent_is_already_assigned():
    """
    Si no cambia el agente asignado, no hay accion real para auditar.
    """

    assigned_user_id = uuid4()

    team_id = uuid4()
    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=assigned_user_id,
        team_id=team_id,
    )

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    assigned_user = SimpleNamespace(
        id=assigned_user_id,
        role="AGENT",
        is_active=True,
    )
    db = TeamAwareFakeDb(
        ticket=ticket,
        assigned_user=assigned_user,
        member=SimpleNamespace(team_id=team_id, user_id=assigned_user.id),
    )

    with pytest.raises(TicketAlreadyAssignedError, match="Ticket already assigned"):
        assign_ticket(db, ticket.id, assigned_user.id, current_user)

    assert ticket.assigned_to == assigned_user_id
    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None
    assert db.rolled_back is False


def test_assign_ticket_rejects_inactive_agent():
    team_id = uuid4()
    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=None,
        team_id=team_id,
    )
    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )
    assigned_user = SimpleNamespace(
        id=uuid4(),
        role="AGENT",
        is_active=False,
    )
    db = TeamAwareFakeDb(ticket=ticket, assigned_user=assigned_user)

    with pytest.raises(InvalidAssignedUserError, match="must be active"):
        assign_ticket(db, ticket.id, assigned_user.id, current_user)

    assert ticket.assigned_to is None
    assert db.added == []
    assert db.committed is False


def test_assign_ticket_rejects_inactive_admin():
    ticket = SimpleNamespace(id=uuid4(), assigned_to=None, team_id=uuid4())
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    assigned_admin = SimpleNamespace(id=uuid4(), role="ADMIN", is_active=False)
    db = TeamAwareFakeDb(ticket=ticket, assigned_user=assigned_admin)

    with pytest.raises(InvalidAssignedUserError, match="must be active"):
        assign_ticket(db, ticket.id, assigned_admin.id, current_user)

    assert ticket.assigned_to is None
    assert db.added == []
    assert db.committed is False


def test_assign_ticket_rolls_back_when_commit_fails():
    """
    Si falla la persistencia, el service debe limpiar la sesion.
    """

    team_id = uuid4()
    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=None,
        team_id=team_id,
    )

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    assigned_user = SimpleNamespace(
        id=uuid4(),
        role="AGENT",
        is_active=True,
    )
    db = FailingTeamAwareFakeDb(
        ticket=ticket,
        assigned_user=assigned_user,
        member=SimpleNamespace(team_id=team_id, user_id=assigned_user.id),
    )

    with pytest.raises(RuntimeError, match="Commit failed"):
        assign_ticket(db, ticket.id, assigned_user.id, current_user)

    assert db.rolled_back is True


def test_team_lead_assigns_ticket_to_team_member():
    team_id = uuid4()
    lead_id = uuid4()
    assigned_user_id = uuid4()
    db = TeamAwareFakeDb(
        ticket=SimpleNamespace(id=uuid4(), assigned_to=None, team_id=team_id),
        assigned_user=SimpleNamespace(id=assigned_user_id, role="AGENT", is_active=True),
        team=SimpleNamespace(id=team_id),
        team_lead=SimpleNamespace(id=uuid4(), team_id=team_id, user_id=lead_id),
        member=SimpleNamespace(team_id=team_id, user_id=assigned_user_id),
    )
    ticket = db.ticket
    current_user = SimpleNamespace(id=lead_id, role="AGENT")
    assigned_user = db.assigned_user

    result = assign_ticket(db, ticket.id, assigned_user.id, current_user)

    assert result is ticket
    assert ticket.assigned_to == assigned_user_id
    assert db.committed is True
    assert isinstance(db.added[0], TicketAssignmentHistory)


def test_admin_assigns_ticket_to_team_member():
    team_id = uuid4()
    assigned_user_id = uuid4()
    ticket = SimpleNamespace(id=uuid4(), assigned_to=None, team_id=team_id)
    assigned_user = SimpleNamespace(id=assigned_user_id, role="AGENT", is_active=True)
    db = TeamAwareFakeDb(
        ticket=ticket,
        assigned_user=assigned_user,
        member=SimpleNamespace(team_id=team_id, user_id=assigned_user_id),
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    result = assign_ticket(db, ticket.id, assigned_user.id, current_user)

    assert result is ticket
    assert ticket.assigned_to == assigned_user_id
    assert db.committed is True
    assert isinstance(db.added[0], TicketAssignmentHistory)


def test_team_lead_assigns_ticket_to_admin_member():
    team_id = uuid4()
    lead_id = uuid4()
    assigned_admin_id = uuid4()
    ticket = SimpleNamespace(id=uuid4(), assigned_to=None, team_id=team_id)
    assigned_admin = SimpleNamespace(id=assigned_admin_id, role="ADMIN", is_active=True)
    db = TeamAwareFakeDb(
        ticket=ticket,
        assigned_user=assigned_admin,
        team_lead=SimpleNamespace(id=uuid4(), team_id=team_id, user_id=lead_id),
        member=SimpleNamespace(team_id=team_id, user_id=assigned_admin_id),
    )
    current_user = SimpleNamespace(id=lead_id, role="AGENT")

    result = assign_ticket(db, ticket.id, assigned_admin.id, current_user)

    assert result is ticket
    assert ticket.assigned_to == assigned_admin_id
    assert db.committed is True
    assert isinstance(db.added[0], TicketAssignmentHistory)


def test_admin_cannot_assign_ticket_to_agent_outside_team():
    team_id = uuid4()
    ticket = SimpleNamespace(id=uuid4(), assigned_to=None, team_id=team_id)
    assigned_user = SimpleNamespace(id=uuid4(), role="AGENT", is_active=True)
    db = TeamAwareFakeDb(ticket=ticket, assigned_user=assigned_user, member=None)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    with pytest.raises(TicketPermissionError, match="invalid assignment"):
        assign_ticket(db, ticket.id, assigned_user.id, current_user)

    assert ticket.assigned_to is None
    assert db.added == []
    assert db.committed is False


def test_assign_ticket_to_team_updates_ticket_team():
    team = SimpleNamespace(id=uuid4())
    ticket = SimpleNamespace(id=uuid4(), assigned_to=None, team_id=None)
    db = TeamAwareFakeDb(ticket=ticket, team=team)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    result = assign_ticket_to_team(db, ticket.id, team.id, current_user)

    assert result is ticket
    assert ticket.team_id == team.id
    assert db.committed is True
    assert isinstance(db.added[0], TicketTeamHistory)
    assert db.added[0].old_team_id is None
    assert db.added[0].new_team_id == team.id
    assert db.added[0].changed_by == current_user.id


def test_assign_ticket_to_same_team_raises_error():
    team = SimpleNamespace(id=uuid4())
    ticket = SimpleNamespace(id=uuid4(), assigned_to=None, team_id=team.id)
    db = TeamAwareFakeDb(ticket=ticket, team=team)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    with pytest.raises(TicketTeamAssignmentError, match="already assigned"):
        assign_ticket_to_team(db, ticket.id, team.id, current_user)


def test_assign_ticket_to_team_rejects_assigned_user_outside_target_team():
    assigned_user_id = uuid4()
    team = SimpleNamespace(id=uuid4())
    ticket = SimpleNamespace(id=uuid4(), assigned_to=assigned_user_id, team_id=None)
    db = TeamAwareFakeDb(ticket=ticket, team=team, member=None)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    with pytest.raises(TicketTeamAssignmentError, match="does not belong"):
        assign_ticket_to_team(db, ticket.id, team.id, current_user)

    assert ticket.team_id is None
    assert db.committed is False


def test_team_lead_assigns_unassigned_ticket_to_own_team_when_category_matches():
    team_id = uuid4()
    category_id = uuid4()
    lead_id = uuid4()
    team = SimpleNamespace(id=team_id)
    ticket = SimpleNamespace(id=uuid4(), assigned_to=None, team_id=None, category_id=category_id)
    category_team = SimpleNamespace(id=uuid4(), category_id=category_id, team_id=team_id)
    current_user = SimpleNamespace(id=lead_id, role="AGENT")
    team_lead = SimpleNamespace(id=uuid4(), team_id=team_id, user_id=lead_id)
    db = TeamAwareFakeDb(ticket=ticket, team=team, category_team=category_team, team_lead=team_lead)

    result = assign_ticket_to_team(db, ticket.id, team.id, current_user)

    assert result is ticket
    assert ticket.team_id == team.id
    assert db.committed is True
    assert isinstance(db.added[0], TicketTeamHistory)


def test_team_lead_cannot_assign_ticket_if_category_is_not_associated():
    team_id = uuid4()
    category_id = uuid4()
    lead_id = uuid4()
    team = SimpleNamespace(id=team_id)
    ticket = SimpleNamespace(id=uuid4(), assigned_to=None, team_id=None, category_id=category_id)
    current_user = SimpleNamespace(id=lead_id, role="AGENT")
    team_lead = SimpleNamespace(id=uuid4(), team_id=team_id, user_id=lead_id)
    db = TeamAwareFakeDb(ticket=ticket, team=team, category_team=None, team_lead=team_lead)

    with pytest.raises(TicketTeamPermissionError, match="category is not associated"):
        assign_ticket_to_team(db, ticket.id, team.id, current_user)

    assert ticket.team_id is None
    assert db.committed is False


def test_admin_changes_ticket_category_and_clears_team_and_assignee():
    old_category_id = uuid4()
    new_category = SimpleNamespace(id=uuid4(), is_active=True)
    old_team_id = uuid4()
    old_assigned_to = uuid4()
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.IN_PROGRESS,
        category_id=old_category_id,
        team_id=old_team_id,
        assigned_to=old_assigned_to,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, category=new_category)

    result = change_ticket_category(db, ticket.id, new_category.id, current_user, " Categoria incorrecta ")

    assert result is ticket
    assert ticket.category_id == new_category.id
    assert ticket.team_id is None
    assert ticket.assigned_to is None
    assert db.committed is True

    category_history = db.added[0]
    assert isinstance(category_history, TicketCategoryHistory)
    assert category_history.old_category_id == old_category_id
    assert category_history.new_category_id == new_category.id
    assert category_history.reason == "Categoria incorrecta"
    assert category_history.changed_by == current_user.id

    team_history = db.added[1]
    assert isinstance(team_history, TicketTeamHistory)
    assert team_history.old_team_id == old_team_id
    assert team_history.new_team_id is None

    assignment_history = db.added[2]
    assert isinstance(assignment_history, TicketAssignmentHistory)
    assert assignment_history.old_assigned_to == old_assigned_to
    assert assignment_history.new_assigned_to is None


def test_change_ticket_category_requires_reason():
    new_category = SimpleNamespace(id=uuid4(), is_active=True)
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.OPEN,
        category_id=uuid4(),
        team_id=None,
        assigned_to=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, category=new_category)

    with pytest.raises(MissingCategoryChangeReasonError, match="Reason is required"):
        change_ticket_category(db, ticket.id, new_category.id, current_user, "   ")

    assert ticket.category_id != new_category.id
    assert db.added == []
    assert db.committed is False


def test_change_ticket_category_rejects_inactive_category():
    new_category = SimpleNamespace(id=uuid4(), is_active=False)
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.OPEN,
        category_id=uuid4(),
        team_id=None,
        assigned_to=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, category=new_category)

    with pytest.raises(InvalidTicketCategoryError, match="Inactive categories"):
        change_ticket_category(db, ticket.id, new_category.id, current_user, "Correccion")

    assert db.added == []
    assert db.committed is False


def test_change_ticket_category_rejects_same_category():
    category_id = uuid4()
    new_category = SimpleNamespace(id=category_id, is_active=True)
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.OPEN,
        category_id=category_id,
        team_id=None,
        assigned_to=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, category=new_category)

    with pytest.raises(InvalidTicketCategoryChangeError, match="already belongs"):
        change_ticket_category(db, ticket.id, new_category.id, current_user, "Correccion")

    assert db.added == []
    assert db.committed is False


def test_team_lead_changes_category_for_ticket_in_own_team():
    team_id = uuid4()
    lead_id = uuid4()
    new_category = SimpleNamespace(id=uuid4(), is_active=True)
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.ON_HOLD,
        category_id=uuid4(),
        team_id=team_id,
        assigned_to=None,
    )
    current_user = SimpleNamespace(id=lead_id, role="AGENT")
    team = SimpleNamespace(id=team_id)
    team_lead = SimpleNamespace(id=uuid4(), team_id=team_id, user_id=lead_id)
    db = TeamAwareFakeDb(ticket=ticket, category=new_category, team=team, team_lead=team_lead)

    result = change_ticket_category(db, ticket.id, new_category.id, current_user, "No corresponde al team")

    assert result is ticket
    assert ticket.category_id == new_category.id
    assert ticket.team_id is None
    assert db.committed is True
    assert isinstance(db.added[0], TicketCategoryHistory)
    assert isinstance(db.added[1], TicketTeamHistory)


def test_agent_without_team_lead_permission_cannot_change_category():
    new_category = SimpleNamespace(id=uuid4(), is_active=True)
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.ON_HOLD,
        category_id=uuid4(),
        team_id=uuid4(),
        assigned_to=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="AGENT")
    db = TeamAwareFakeDb(ticket=ticket, category=new_category, team=None)

    with pytest.raises(TicketPermissionError, match="Only the current team lead"):
        change_ticket_category(db, ticket.id, new_category.id, current_user, "No corresponde")

    assert db.added == []
    assert db.committed is False
