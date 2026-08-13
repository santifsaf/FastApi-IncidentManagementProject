from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import tickets as tickets_routes
from app.models.user import UserRole


class FakeQuery:
    def __init__(self, items):
        self.items = items

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, skip):
        self.items = self.items[skip:]
        return self

    def limit(self, limit):
        self.items = self.items[:limit]
        return self

    def first(self):
        return self.items[0] if self.items else None

    def all(self):
        return self.items


class FakeSession:
    def __init__(self, ticket=None, tickets=None, history=None):
        self.tickets = tickets if tickets is not None else ([ticket] if ticket else [])
        self.history = history or []

    def query(self, model):
        if model.__name__ == "Ticket":
            return FakeQuery(self.tickets)
        if model.__name__ in {
            "TicketStatusHistory",
            "TicketAssignmentHistory",
            "TicketTeamHistory",
            "TicketCategoryHistory",
        }:
            return FakeQuery(self.history)
        raise AssertionError(f"Unexpected model queried: {model}")


def test_created_by_me_endpoint_returns_created_tickets():
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER)
    ticket = SimpleNamespace(id=uuid4(), created_by=user.id, assigned_to=None, team_id=None)
    fake_session = FakeSession(ticket=ticket)

    result = tickets_routes.get_tickets_created_by_me(fake_session, user)

    assert result == [ticket]


def test_assigned_to_me_endpoint_returns_assigned_tickets():
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT)
    ticket = SimpleNamespace(id=uuid4(), created_by=uuid4(), assigned_to=user.id, team_id=None)
    fake_session = FakeSession(ticket=ticket)

    result = tickets_routes.get_tickets_assigned_to_me(fake_session, user)

    assert result == [ticket]


def test_get_all_tickets_endpoint_applies_pagination():
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN)
    tickets = [
        SimpleNamespace(id=uuid4(), team_id=None),
        SimpleNamespace(id=uuid4(), team_id=None),
        SimpleNamespace(id=uuid4(), team_id=None),
    ]
    fake_session = FakeSession(tickets=tickets)

    result = tickets_routes.get_all_tickets(fake_session, admin, skip=1, limit=1)

    assert result == [tickets[1]]


def test_status_history_endpoint_returns_403_for_unauthorized_user(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER)
    ticket = SimpleNamespace(id=uuid4(), created_by=uuid4(), assigned_to=None, team_id=None)
    fake_session = FakeSession(ticket=ticket, history=[])

    monkeypatch.setattr(tickets_routes, "get_db", lambda: fake_session)
    monkeypatch.setattr(tickets_routes, "get_current_active_user", lambda: user)

    with pytest.raises(HTTPException) as exc_info:
        tickets_routes.get_ticket_status_history(ticket.id, fake_session, user)

    assert exc_info.value.status_code == 403


def test_assignment_history_endpoint_returns_200_for_assigned_agent(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT)
    ticket = SimpleNamespace(id=uuid4(), created_by=uuid4(), assigned_to=user.id, team_id=None)
    history_item = SimpleNamespace(
        ticket_id=ticket.id,
        old_assigned_to=None,
        new_assigned_to=user.id,
        changed_by=user.id,
        changed_at="2024-01-01T00:00:00",
    )
    fake_session = FakeSession(ticket=ticket, history=[history_item])

    monkeypatch.setattr(tickets_routes, "get_db", lambda: fake_session)
    monkeypatch.setattr(tickets_routes, "get_current_active_user", lambda: user)

    result = tickets_routes.get_ticket_assignment_history(ticket.id, fake_session, user)

    assert len(result) == 1
    assert result[0].new_assigned_to == user.id


def test_team_history_endpoint_returns_200_for_assigned_agent(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT)
    ticket = SimpleNamespace(id=uuid4(), created_by=uuid4(), assigned_to=user.id, team_id=None)
    history_item = SimpleNamespace(
        ticket_id=ticket.id,
        old_team_id=None,
        new_team_id=uuid4(),
        changed_by=user.id,
        changed_at="2024-01-01T00:00:00",
    )
    fake_session = FakeSession(ticket=ticket, history=[history_item])

    monkeypatch.setattr(tickets_routes, "get_db", lambda: fake_session)
    monkeypatch.setattr(tickets_routes, "get_current_active_user", lambda: user)

    result = tickets_routes.get_ticket_team_history(ticket.id, fake_session, user)

    assert len(result) == 1
    assert result[0].new_team_id == history_item.new_team_id


def test_category_history_endpoint_returns_200_for_assigned_agent(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT)
    ticket = SimpleNamespace(id=uuid4(), created_by=uuid4(), assigned_to=user.id, team_id=None)
    history_item = SimpleNamespace(
        ticket_id=ticket.id,
        old_category_id=uuid4(),
        new_category_id=uuid4(),
        reason="Categoria incorrecta",
        changed_by=user.id,
        changed_at="2024-01-01T00:00:00",
    )
    fake_session = FakeSession(ticket=ticket, history=[history_item])

    monkeypatch.setattr(tickets_routes, "get_db", lambda: fake_session)
    monkeypatch.setattr(tickets_routes, "get_current_active_user", lambda: user)

    result = tickets_routes.get_ticket_category_history(ticket.id, fake_session, user)

    assert len(result) == 1
    assert result[0].new_category_id == history_item.new_category_id


def test_blocked_tickets_endpoint_returns_service_result(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT)
    ticket_id = uuid4()
    blocked_ticket = SimpleNamespace(
        id=uuid4(),
        title="Ticket bloqueado",
        description="Depende del ticket actual",
        status="ON_HOLD",
        priority="MEDIUM",
        created_by=uuid4(),
        assigned_to=None,
        team_id=None,
        category_id=uuid4(),
    )
    fake_session = FakeSession()

    monkeypatch.setattr(
        tickets_routes,
        "get_blocked_tickets_service",
        lambda db, current_ticket_id, current_user: [blocked_ticket],
    )

    result = tickets_routes.get_blocked_tickets(ticket_id, fake_session, user)

    assert result == [blocked_ticket]
