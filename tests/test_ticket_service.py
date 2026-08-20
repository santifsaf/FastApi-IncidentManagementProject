"""Tests del service de tickets.

Este archivo cubre los casos de uso principales: crear tickets, asignar agente
y team, cambiar estado/categoria, auditar historial y manejar dependencias.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.category import CategoryTeam, TicketCategory
from app.models.team import Team, TeamLead, TeamMember
from app.models.ticket import (
    Ticket,
    TicketAssignmentHistory,
    TicketCategoryHistory,
    TicketDependency,
    TicketPriority,
    TicketStatus,
    TicketStatusHistory,
    TicketTeamHistory,
)
from app.models.user import User
from app.services.ticket_service import (
    InvalidStatusTransitionError,
    InvalidAssignedUserError,
    InvalidTicketCategoryChangeError,
    InvalidTicketCategoryError,
    MissingCategoryChangeReasonError,
    MissingStatusChangeReasonError,
    TicketBlockedByOpenDependenciesError,
    TicketAlreadyAssignedError,
    TicketCategoryNotFoundError,
    TicketDependencyError,
    TicketDependencyNotFoundError,
    TicketArchiveError,
    TicketTeamAssignmentError,
    TicketTeamPermissionError,
    TicketPermissionError,
    add_ticket_dependency,
    archive_old_closed_tickets,
    archive_ticket,
    assign_ticket,
    assign_ticket_to_team,
    change_ticket_category,
    change_ticket_status,
    create_blocking_ticket,
    create_ticket_service,
    get_blocked_tickets_service,
    remove_ticket_dependency,
    unarchive_ticket,
)


class FakeDb:
    """
    Simula una sesion de base de datos.

    No usamos PostgreSQL real en este test. Solo necesitamos comprobar que
    el service llama a db.add(), db.commit() y db.refresh().
    """

    def __init__(self):
        # Guarda los objetos que el service intenta agregar a la base.
        self.added = []

        # Permite saber si el service confirmo la transaccion.
        self.committed = False

        # Permite saber que objeto se refresco despues del commit.
        self.refreshed = None

        # Permite saber si el service limpio la sesion luego de un error.
        self.rolled_back = False

        # Permite verificar flujos donde necesitamos INSERT antes del commit.
        self.flushed = False

        # Guarda los objetos que el service intenta eliminar.
        self.deleted = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = obj

    def rollback(self):
        self.rolled_back = True

    def flush(self):
        self.flushed = True
        # Simula que SQLAlchemy/base asignan el UUID al hacer INSERT.
        for obj in self.added:
            if isinstance(obj, Ticket) and getattr(obj, "id", None) is None:
                obj.id = uuid4()

    def delete(self, obj):
        self.deleted.append(obj)


class FailingCommitDb(FakeDb):
    def commit(self):
        raise RuntimeError("Commit failed")


class FakeQuery:
    def __init__(self, item=None, items=None):
        self.item = item
        self.items = items if items is not None else ([] if item is None else [item])

    def filter(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        if isinstance(self.item, list):
            return self.item[0] if self.item else None
        return self.item

    def all(self):
        return self.items


class TeamAwareFakeDb(FakeDb):
    def __init__(
        self,
        ticket=None,
        assigned_user=None,
        team=None,
        member=None,
        category=None,
        category_team=None,
        team_lead=None,
        dependency=None,
        dependencies=None,
        depends_on_ticket=None,
        missing_depends_on_ticket=False,
        reverse_dependency=None,
        open_dependency=None,
        blocked_tickets=None,
        tickets=None,
    ):
        super().__init__()
        self.ticket = ticket
        self.assigned_user = assigned_user
        self.team = team
        self.member = member
        self.category = category
        self.category_team = category_team
        self.team_lead = team_lead
        self.dependency = dependency
        self.dependencies = dependencies
        self.depends_on_ticket = depends_on_ticket
        self.missing_depends_on_ticket = missing_depends_on_ticket
        self.reverse_dependency = reverse_dependency
        self.open_dependency = open_dependency
        self.blocked_tickets = blocked_tickets
        self.tickets = tickets
        self.ticket_query_count = 0
        self.dependency_id_query_count = 0

    def query(self, model):
        model_class = getattr(model, "class_", None)
        if model is TicketDependency:
            first_dependency = self.dependencies[0] if self.dependencies else None
            return FakeQuery(item=first_dependency, items=self.dependencies or [])
        if model_class is TicketDependency:
            self.dependency_id_query_count += 1
            if self.dependency_id_query_count == 1:
                return FakeQuery(self.open_dependency or self.dependency)
            if self.dependency_id_query_count == 2:
                return FakeQuery(self.reverse_dependency)
            return FakeQuery(None)
        if model is CategoryTeam or model_class is CategoryTeam:
            return FakeQuery(self.category_team)
        if model is TicketCategory or model_class is TicketCategory:
            return FakeQuery(self.category)
        if model is Ticket or model_class is Ticket:
            self.ticket_query_count += 1
            if self.tickets is not None:
                return FakeQuery(item=None, items=self.tickets)
            if self.ticket_query_count == 2 and self.blocked_tickets is not None:
                return FakeQuery(item=None, items=self.blocked_tickets)
            if self.ticket_query_count == 2 and self.missing_depends_on_ticket:
                return FakeQuery(None)
            if self.ticket_query_count == 2 and self.depends_on_ticket is not None:
                return FakeQuery(self.depends_on_ticket)
            return FakeQuery(self.ticket)
        if model is User or model_class is User:
            return FakeQuery(self.assigned_user)
        if model is Team or model_class is Team:
            return FakeQuery(self.team)
        if model is TeamLead or model_class is TeamLead:
            return FakeQuery(self.team_lead)
        if model is TeamMember or model_class is TeamMember:
            return FakeQuery(self.member)
        raise AssertionError(f"Unexpected model queried: {model}")


class FailingTeamAwareFakeDb(TeamAwareFakeDb):
    def commit(self):
        raise RuntimeError("Commit failed")


def test_create_ticket_service_creates_ticket():
    category = SimpleNamespace(id=uuid4(), is_active=True)
    db = TeamAwareFakeDb(category=category)
    ticket_in = SimpleNamespace(
        title="Error login",
        description="No puedo ingresar",
        category_id=category.id,
        priority=TicketPriority.HIGH,
    )
    current_user = SimpleNamespace(id=uuid4())

    result = create_ticket_service(db, ticket_in, current_user)

    assert isinstance(result, Ticket)
    assert result.title == ticket_in.title
    assert result.description == ticket_in.description
    assert result.status == TicketStatus.OPEN
    assert result.priority == TicketPriority.HIGH
    assert result.created_by == current_user.id
    assert result.category_id == category.id
    assert db.added == [result]
    assert db.committed is True
    assert db.refreshed is result
    assert db.rolled_back is False


def test_create_ticket_service_rolls_back_when_commit_fails():
    category = SimpleNamespace(id=uuid4(), is_active=True)
    db = FailingTeamAwareFakeDb(category=category)
    ticket_in = SimpleNamespace(
        title="Error login",
        description="No puedo ingresar",
        category_id=category.id,
        priority=TicketPriority.HIGH,
    )
    current_user = SimpleNamespace(id=uuid4())

    with pytest.raises(RuntimeError, match="Commit failed"):
        create_ticket_service(db, ticket_in, current_user)

    assert len(db.added) == 1
    assert db.rolled_back is True


def test_create_ticket_service_rejects_missing_category():
    db = TeamAwareFakeDb(category=None)
    ticket_in = SimpleNamespace(
        title="Error login",
        description="No puedo ingresar",
        category_id=uuid4(),
        priority=TicketPriority.HIGH,
    )
    current_user = SimpleNamespace(id=uuid4())

    with pytest.raises(TicketCategoryNotFoundError, match="Category not found"):
        create_ticket_service(db, ticket_in, current_user)

    assert db.added == []


def test_create_ticket_service_rejects_inactive_category():
    category = SimpleNamespace(id=uuid4(), is_active=False)
    db = TeamAwareFakeDb(category=category)
    ticket_in = SimpleNamespace(
        title="Error login",
        description="No puedo ingresar",
        category_id=category.id,
        priority=TicketPriority.HIGH,
    )
    current_user = SimpleNamespace(id=uuid4())

    with pytest.raises(InvalidTicketCategoryError, match="Inactive categories"):
        create_ticket_service(db, ticket_in, current_user)

    assert db.added == []


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
    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=old_assigned_id,
        team_id=None,
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
    db = TeamAwareFakeDb(ticket=ticket, assigned_user=assigned_user)

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


def test_assign_ticket_raises_permission_error_when_user_cannot_assign():
    """
    Caso invalido:
    - Un USER intenta asignar un ticket.
    - La regla no lo permite.
    - El service lanza TicketPermissionError.
    - No modifica el ticket.
    - No crea historial.
    """

    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=None,
        team_id=None,
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
    db = TeamAwareFakeDb(ticket=ticket, assigned_user=assigned_user)

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

    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=assigned_user_id,
        team_id=None,
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
    db = TeamAwareFakeDb(ticket=ticket, assigned_user=assigned_user)

    with pytest.raises(TicketAlreadyAssignedError, match="Ticket already assigned"):
        assign_ticket(db, ticket.id, assigned_user.id, current_user)

    assert ticket.assigned_to == assigned_user_id
    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None
    assert db.rolled_back is False


def test_assign_ticket_rejects_inactive_agent():
    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=None,
        team_id=None,
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


def test_assign_ticket_rolls_back_when_commit_fails():
    """
    Si falla la persistencia, el service debe limpiar la sesion.
    """

    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=None,
        team_id=None,
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
    db = FailingTeamAwareFakeDb(ticket=ticket, assigned_user=assigned_user)

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


def test_admin_adds_existing_ticket_dependency():
    ticket = SimpleNamespace(id=uuid4(), status=TicketStatus.IN_PROGRESS, team_id=None)
    depends_on_ticket = SimpleNamespace(id=uuid4(), status=TicketStatus.OPEN)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, depends_on_ticket=depends_on_ticket)

    result = add_ticket_dependency(db, ticket.id, depends_on_ticket.id, current_user, "Necesita revision externa")

    assert isinstance(result, TicketDependency)
    assert result.ticket_id == ticket.id
    assert result.depends_on_ticket_id == depends_on_ticket.id
    assert result.reason == "Necesita revision externa"
    assert result.created_by == current_user.id
    assert db.committed is True


def test_add_ticket_dependency_rejects_self_dependency():
    ticket_id = uuid4()
    ticket = SimpleNamespace(id=ticket_id, status=TicketStatus.IN_PROGRESS, team_id=None)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, depends_on_ticket=ticket)

    with pytest.raises(TicketDependencyError, match="cannot depend on itself"):
        add_ticket_dependency(db, ticket.id, ticket.id, current_user)

    assert db.added == []
    assert db.committed is False


def test_add_ticket_dependency_rejects_missing_blocking_ticket():
    ticket = SimpleNamespace(id=uuid4(), status=TicketStatus.IN_PROGRESS, team_id=None)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, missing_depends_on_ticket=True)

    with pytest.raises(TicketDependencyNotFoundError, match="Blocking ticket not found"):
        add_ticket_dependency(db, ticket.id, uuid4(), current_user)

    assert db.added == []
    assert db.committed is False


def test_create_blocking_ticket_creates_ticket_dependency_and_sets_current_ticket_on_hold():
    category = SimpleNamespace(id=uuid4(), is_active=True)
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.IN_PROGRESS,
        team_id=None,
    )
    blocking_ticket_in = SimpleNamespace(
        title="Revisar VPN",
        description="Validar conectividad remota",
        category_id=category.id,
        priority=TicketPriority.HIGH,
        reason="No se puede continuar hasta revisar VPN",
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, category=category)

    result = create_blocking_ticket(db, ticket.id, blocking_ticket_in, current_user)

    assert result["current_ticket"] is ticket
    assert ticket.status == TicketStatus.ON_HOLD
    assert db.flushed is True
    assert db.committed is True

    blocking_ticket = result["blocking_ticket"]
    assert isinstance(blocking_ticket, Ticket)
    assert blocking_ticket.id is not None
    assert blocking_ticket.status == TicketStatus.OPEN
    assert blocking_ticket.category_id == category.id
    assert blocking_ticket.created_by == current_user.id

    dependency = result["dependency"]
    assert isinstance(dependency, TicketDependency)
    assert dependency.ticket_id == ticket.id
    assert dependency.depends_on_ticket_id == blocking_ticket.id

    assert isinstance(db.added[0], Ticket)
    assert isinstance(db.added[1], TicketDependency)
    assert isinstance(db.added[2], TicketStatusHistory)
    assert db.added[2].old_status == TicketStatus.IN_PROGRESS
    assert db.added[2].new_status == TicketStatus.ON_HOLD


def test_change_ticket_status_cannot_resolve_with_open_dependencies():
    db = TeamAwareFakeDb(open_dependency=SimpleNamespace(id=uuid4()))
    ticket = SimpleNamespace(id=uuid4(), status=TicketStatus.IN_PROGRESS, assigned_to=None)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    with pytest.raises(TicketBlockedByOpenDependenciesError, match="open dependencies"):
        change_ticket_status(db, ticket, TicketStatus.RESOLVED, current_user)

    assert ticket.status == TicketStatus.IN_PROGRESS
    assert db.added == []
    assert db.committed is False


def test_admin_removes_ticket_dependency():
    ticket = SimpleNamespace(id=uuid4(), status=TicketStatus.ON_HOLD, team_id=None)
    dependency = SimpleNamespace(id=uuid4(), ticket_id=ticket.id, is_active=True)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, dependencies=[dependency])

    result = remove_ticket_dependency(db, ticket.id, dependency.id, current_user, "Ya no bloquea")

    assert result is dependency
    assert dependency.is_active is False
    assert dependency.removed_by == current_user.id
    assert dependency.removed_at is not None
    assert dependency.removed_reason == "Ya no bloquea"
    assert db.deleted == []
    assert db.committed is True


def test_remove_ticket_dependency_rejects_missing_dependency():
    ticket = SimpleNamespace(id=uuid4(), status=TicketStatus.ON_HOLD, team_id=None)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, dependencies=[])

    with pytest.raises(TicketDependencyNotFoundError, match="Dependency not found"):
        remove_ticket_dependency(db, ticket.id, uuid4(), current_user, "No corresponde")

    assert db.deleted == []
    assert db.committed is False


def test_admin_views_tickets_blocked_by_current_ticket():
    blocking_ticket = SimpleNamespace(id=uuid4(), team_id=None, assigned_to=None, created_by=uuid4())
    blocked_tickets = [
        SimpleNamespace(id=uuid4(), status=TicketStatus.IN_PROGRESS),
        SimpleNamespace(id=uuid4(), status=TicketStatus.ON_HOLD),
    ]
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=blocking_ticket, blocked_tickets=blocked_tickets)

    result = get_blocked_tickets_service(db, blocking_ticket.id, current_user)

    assert result == blocked_tickets


def test_user_cannot_view_blocked_tickets():
    blocking_ticket = SimpleNamespace(id=uuid4(), team_id=None, assigned_to=None, created_by=uuid4())
    current_user = SimpleNamespace(id=uuid4(), role="USER")
    db = TeamAwareFakeDb(ticket=blocking_ticket, blocked_tickets=[])

    with pytest.raises(TicketPermissionError, match="Not enough permissions"):
        get_blocked_tickets_service(db, blocking_ticket.id, current_user)


def test_remove_ticket_dependency_requires_reason():
    ticket = SimpleNamespace(id=uuid4(), status=TicketStatus.ON_HOLD, team_id=None)
    dependency = SimpleNamespace(id=uuid4(), ticket_id=ticket.id, is_active=True)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket, dependencies=[dependency])

    with pytest.raises(TicketDependencyError, match="Reason is required"):
        remove_ticket_dependency(db, ticket.id, dependency.id, current_user, "   ")

    assert dependency.is_active is True
    assert db.committed is False


def test_agent_without_team_lead_permission_cannot_remove_dependency():
    ticket = SimpleNamespace(id=uuid4(), status=TicketStatus.ON_HOLD, team_id=uuid4())
    dependency = SimpleNamespace(id=uuid4(), ticket_id=ticket.id, is_active=True)
    current_user = SimpleNamespace(id=uuid4(), role="AGENT")
    db = TeamAwareFakeDb(ticket=ticket, dependencies=[dependency], team=None)

    with pytest.raises(TicketPermissionError, match="Not enough permissions"):
        remove_ticket_dependency(db, ticket.id, dependency.id, current_user, "No corresponde")

    assert db.deleted == []
    assert db.committed is False


def test_change_ticket_status_updates_ticket_and_creates_history():
    db = FakeDb()

    ticket = SimpleNamespace(
        id=uuid4(),
        status="OPEN",
    )

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    result = change_ticket_status(db, ticket, "IN_PROGRESS", current_user)

    assert result is ticket
    assert ticket.status == "IN_PROGRESS"
    assert db.committed is True
    assert db.refreshed is ticket
    assert len(db.added) == 1

    history = db.added[0]
    assert isinstance(history, TicketStatusHistory)
    assert history.ticket_id == ticket.id
    assert history.old_status == "OPEN"
    assert history.new_status == "IN_PROGRESS"
    assert history.reason is None
    assert history.changed_by == current_user.id


def test_change_ticket_status_saves_reason_when_provided():
    db = FakeDb()

    ticket = SimpleNamespace(
        id=uuid4(),
        status="OPEN",
    )

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    result = change_ticket_status(db, ticket, "ON_HOLD", current_user, "Waiting for provider")

    assert result is ticket
    assert ticket.status == "ON_HOLD"

    history = db.added[0]
    assert history.reason == "Waiting for provider"


def test_change_ticket_status_sets_closed_at_when_closing_ticket():
    db = FakeDb()
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.RESOLVED,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    result = change_ticket_status(db, ticket, TicketStatus.CLOSED, current_user, "Confirmado")

    assert result is ticket
    assert ticket.status == TicketStatus.CLOSED
    assert ticket.closed_at is not None
    assert db.committed is True


def test_change_ticket_status_requires_reason_for_sensitive_status_change():
    db = FakeDb()

    ticket = SimpleNamespace(
        id=uuid4(),
        status="OPEN",
    )

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    with pytest.raises(MissingStatusChangeReasonError, match="Reason is required"):
        change_ticket_status(db, ticket, "ON_HOLD", current_user)

    assert ticket.status == "OPEN"
    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None


def test_admin_archives_closed_ticket():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        archived_at=None,
        archived_by=None,
        archive_reason=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket)

    result = archive_ticket(db, ticket.id, current_user, " Limpieza operativa ")

    assert result is ticket
    assert ticket.archived_at is not None
    assert ticket.archived_by == current_user.id
    assert ticket.archive_reason == "Limpieza operativa"
    assert db.committed is True


def test_archive_ticket_rejects_non_closed_ticket():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.IN_PROGRESS,
        archived_at=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket)

    with pytest.raises(TicketArchiveError, match="Only closed tickets"):
        archive_ticket(db, ticket.id, current_user, "Limpieza")

    assert ticket.archived_at is None
    assert db.committed is False


def test_archive_ticket_requires_reason():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        archived_at=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket)

    with pytest.raises(TicketArchiveError, match="Reason is required"):
        archive_ticket(db, ticket.id, current_user, "   ")

    assert ticket.archived_at is None
    assert db.committed is False


def test_admin_unarchives_archived_ticket():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        archived_at=object(),
        archived_by=uuid4(),
        archive_reason="Limpieza",
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket)

    result = unarchive_ticket(db, ticket.id, current_user)

    assert result is ticket
    assert ticket.archived_at is None
    assert ticket.archived_by is None
    assert ticket.archive_reason is None
    assert db.committed is True


def test_unarchive_ticket_rejects_visible_ticket():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        archived_at=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket)

    with pytest.raises(TicketArchiveError, match="not archived"):
        unarchive_ticket(db, ticket.id, current_user)

    assert db.committed is False


def test_archive_old_closed_tickets_archives_matching_tickets():
    old_closed_ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        closed_at=datetime.now(timezone.utc) - timedelta(days=45),
        archived_at=None,
        archived_by=None,
        archive_reason=None,
    )
    db = TeamAwareFakeDb(tickets=[old_closed_ticket])

    archived_count = archive_old_closed_tickets(db, days=30)

    assert archived_count == 1
    assert old_closed_ticket.archived_at is not None
    assert old_closed_ticket.archived_by is None
    assert old_closed_ticket.archive_reason == "Archivado automaticamente luego de 30 dias cerrado"
    assert db.committed is True


def test_archive_old_closed_tickets_rejects_invalid_days():
    db = TeamAwareFakeDb(tickets=[])

    with pytest.raises(TicketArchiveError, match="Days must be greater than zero"):
        archive_old_closed_tickets(db, days=0)

    assert db.committed is False


def test_archive_old_closed_tickets_rolls_back_when_commit_fails():
    old_closed_ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        closed_at=datetime.now(timezone.utc) - timedelta(days=45),
        archived_at=None,
        archived_by=None,
        archive_reason=None,
    )
    db = FailingTeamAwareFakeDb(tickets=[old_closed_ticket])

    with pytest.raises(RuntimeError, match="Commit failed"):
        archive_old_closed_tickets(db, days=30)

    assert db.rolled_back is True


def test_change_ticket_status_treats_blank_reason_as_missing():
    db = FakeDb()

    ticket = SimpleNamespace(
        id=uuid4(),
        status="RESOLVED",
    )

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    with pytest.raises(MissingStatusChangeReasonError, match="Reason is required"):
        change_ticket_status(db, ticket, "OPEN", current_user, "   ")

    assert ticket.status == "RESOLVED"
    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None


def test_change_ticket_status_raises_value_error_for_invalid_transition():
    db = FakeDb()

    ticket = SimpleNamespace(id=uuid4(), status="CLOSED")
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    with pytest.raises(InvalidStatusTransitionError, match="Invalid transition"):
        change_ticket_status(db, ticket, "OPEN", current_user)

    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None


def test_change_ticket_status_raises_permission_error_for_unauthorized_user():
    db = FakeDb()

    ticket = SimpleNamespace(id=uuid4(), status="OPEN")
    current_user = SimpleNamespace(id=uuid4(), role="USER")

    with pytest.raises(TicketPermissionError, match="Not enough permissions"):
        change_ticket_status(db, ticket, "IN_PROGRESS", current_user)

    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None
