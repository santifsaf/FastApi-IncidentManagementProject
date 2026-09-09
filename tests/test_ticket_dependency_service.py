"""Tests unitarios de dependencias entre tickets."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.ticket import (
    Ticket,
    TicketDependency,
    TicketPriority,
    TicketStatus,
    TicketStatusHistory,
)
from app.services.ticket_dependency_service import (
    add_ticket_dependency,
    create_blocking_ticket,
    get_blocked_tickets_service,
    remove_ticket_dependency,
)
from app.services.ticket_exceptions import (
    TicketBlockedByOpenDependenciesError,
    TicketDependencyError,
    TicketDependencyNotFoundError,
    TicketPermissionError,
)
from app.services.ticket_lifecycle_service import change_ticket_status
from tests.ticket_service_fakes import TeamAwareFakeDb


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
    ticket = SimpleNamespace(id=uuid4(), status=TicketStatus.IN_PROGRESS, assigned_to=None)
    db = TeamAwareFakeDb(ticket=ticket, open_dependency=SimpleNamespace(id=uuid4()))
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    with pytest.raises(TicketBlockedByOpenDependenciesError, match="open dependencies"):
        change_ticket_status(db, ticket.id, TicketStatus.RESOLVED, current_user)

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
