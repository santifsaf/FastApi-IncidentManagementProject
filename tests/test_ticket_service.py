"""Tests unitarios de creacion y consulta principal de tickets."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.category import TeamAssignmentStrategy
from app.models.user import UserRole
from app.services.ticket_exceptions import (
    InvalidTicketCategoryError,
    TicketCategoryNotFoundError,
    TicketNotFoundError,
    TicketPermissionError,
)
from app.services.ticket_service import create_ticket_service, get_ticket_detail
from tests.ticket_service_fakes import FailingTeamAwareFakeDb, TeamAwareFakeDb


def test_create_ticket_service_creates_ticket():
    category = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        auto_team_assignment_enabled=False,
        team_assignment_delay_minutes=0,
        team_assignment_strategy=TeamAssignmentStrategy.LEAST_LOAD_PER_MEMBER,
    )
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
    category = SimpleNamespace(
        id=uuid4(),
        is_active=True,
        auto_team_assignment_enabled=False,
        team_assignment_delay_minutes=0,
        team_assignment_strategy=TeamAssignmentStrategy.LEAST_LOAD_PER_MEMBER,
    )
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


def test_get_ticket_detail_returns_archived_ticket_created_by_user():
    """Archivar lo quita de listados, pero el creador conserva acceso puntual."""

    user = SimpleNamespace(id=uuid4(), role=UserRole.USER)
    ticket = SimpleNamespace(
        id=uuid4(),
        created_by=user.id,
        assigned_to=None,
        team_id=None,
        archived_at=datetime.now(timezone.utc),
    )
    db = TeamAwareFakeDb(ticket=ticket)

    result = get_ticket_detail(db, ticket.id, user)

    assert result is ticket


def test_get_ticket_detail_returns_ticket_to_agent_from_team():
    """El AGENT puede consultar tickets del team aunque no sea el asignado."""

    agent = SimpleNamespace(id=uuid4(), role=UserRole.AGENT)
    ticket = SimpleNamespace(
        id=uuid4(),
        created_by=uuid4(),
        assigned_to=None,
        team_id=uuid4(),
        archived_at=None,
    )
    membership = SimpleNamespace(id=uuid4(), team_id=ticket.team_id, user_id=agent.id)
    db = TeamAwareFakeDb(ticket=ticket, member=membership)

    result = get_ticket_detail(db, ticket.id, agent)

    assert result is ticket


def test_get_ticket_detail_rejects_user_without_permission():
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER)
    ticket = SimpleNamespace(
        id=uuid4(),
        created_by=uuid4(),
        assigned_to=None,
        team_id=None,
        archived_at=None,
    )
    db = TeamAwareFakeDb(ticket=ticket)

    with pytest.raises(TicketPermissionError, match="Not enough permissions to view ticket"):
        get_ticket_detail(db, ticket.id, user)


def test_get_ticket_detail_rejects_missing_ticket():
    user = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN)
    db = TeamAwareFakeDb(ticket=None)

    with pytest.raises(TicketNotFoundError, match="Ticket not found"):
        get_ticket_detail(db, uuid4(), user)
