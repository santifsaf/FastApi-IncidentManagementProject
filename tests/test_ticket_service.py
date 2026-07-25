from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.ticket import Ticket, TicketAssignmentHistory, TicketPriority, TicketStatusHistory
from app.services.ticket_service import (
    InvalidStatusTransitionError,
    MissingStatusChangeReasonError,
    TicketAlreadyAssignedError,
    TicketPermissionError,
    assign_ticket,
    change_ticket_status,
    create_ticket_service,
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

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = obj

    def rollback(self):
        self.rolled_back = True


class FailingCommitDb(FakeDb):
    def commit(self):
        raise RuntimeError("Commit failed")


def test_create_ticket_service_creates_ticket():
    db = FakeDb()
    ticket_in = SimpleNamespace(
        title="Error login",
        description="No puedo ingresar",
        priority=TicketPriority.HIGH,
    )
    current_user = SimpleNamespace(id=uuid4())

    result = create_ticket_service(db, ticket_in, current_user)

    assert isinstance(result, Ticket)
    assert result.title == ticket_in.title
    assert result.description == ticket_in.description
    assert result.priority == TicketPriority.HIGH
    assert result.created_by == current_user.id
    assert db.added == [result]
    assert db.committed is True
    assert db.refreshed is result
    assert db.rolled_back is False


def test_create_ticket_service_rolls_back_when_commit_fails():
    db = FailingCommitDb()
    ticket_in = SimpleNamespace(
        title="Error login",
        description="No puedo ingresar",
        priority=TicketPriority.HIGH,
    )
    current_user = SimpleNamespace(id=uuid4())

    with pytest.raises(RuntimeError, match="Commit failed"):
        create_ticket_service(db, ticket_in, current_user)

    assert len(db.added) == 1
    assert db.rolled_back is True


def test_assign_ticket_updates_ticket_and_creates_history():
    """
    Caso exitoso:
    - Un ADMIN asigna un ticket a un AGENT.
    - El ticket cambia su assigned_to.
    - Se crea un registro en TicketAssignmentHistory.
    - Se confirma la transaccion.
    """

    db = FakeDb()

    # Simulamos que el ticket ya estaba asignado a otro usuario.
    old_assigned_id = uuid4()

    # SimpleNamespace crea objetos simples con atributos.
    # Lo usamos para no depender de SQLAlchemy ni de una base real.
    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=old_assigned_id,
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
    )

    result = assign_ticket(db, ticket, current_user, assigned_user)

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

    db = FakeDb()

    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=None,
    )

    current_user = SimpleNamespace(
        id=uuid4(),
        role="USER",
    )

    assigned_user = SimpleNamespace(
        id=uuid4(),
        role="AGENT",
    )

    with pytest.raises(TicketPermissionError):
        assign_ticket(db, ticket, current_user, assigned_user)

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

    db = FakeDb()
    assigned_user_id = uuid4()

    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=assigned_user_id,
    )

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    assigned_user = SimpleNamespace(
        id=assigned_user_id,
        role="AGENT",
    )

    with pytest.raises(TicketAlreadyAssignedError, match="Ticket already assigned"):
        assign_ticket(db, ticket, current_user, assigned_user)

    assert ticket.assigned_to == assigned_user_id
    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None
    assert db.rolled_back is False


def test_assign_ticket_rolls_back_when_commit_fails():
    """
    Si falla la persistencia, el service debe limpiar la sesion.
    """

    db = FailingCommitDb()

    ticket = SimpleNamespace(
        id=uuid4(),
        assigned_to=None,
    )

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    assigned_user = SimpleNamespace(
        id=uuid4(),
        role="AGENT",
    )

    with pytest.raises(RuntimeError, match="Commit failed"):
        assign_ticket(db, ticket, current_user, assigned_user)

    assert db.rolled_back is True


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
