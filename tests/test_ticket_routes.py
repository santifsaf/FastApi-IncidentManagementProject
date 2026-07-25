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

    def first(self):
        return self.items[0] if self.items else None

    def all(self):
        return self.items


class FakeSession:
    def __init__(self, ticket=None, history=None):
        self.ticket = ticket
        self.history = history or []

    def query(self, model):
        if model.__name__ == "Ticket":
            return FakeQuery([self.ticket] if self.ticket else [])
        if model.__name__ in {"TicketStatusHistory", "TicketAssignmentHistory"}:
            return FakeQuery(self.history)
        raise AssertionError(f"Unexpected model queried: {model}")


def test_created_by_me_endpoint_returns_created_tickets():
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER)
    ticket = SimpleNamespace(id=uuid4(), created_by=user.id, assigned_to=None)
    fake_session = FakeSession(ticket=ticket)

    result = tickets_routes.get_tickets_created_by_me(fake_session, user)

    assert result == [ticket]


def test_assigned_to_me_endpoint_returns_assigned_tickets():
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT)
    ticket = SimpleNamespace(id=uuid4(), created_by=uuid4(), assigned_to=user.id)
    fake_session = FakeSession(ticket=ticket)

    result = tickets_routes.get_tickets_assigned_to_me(fake_session, user)

    assert result == [ticket]


def test_status_history_endpoint_returns_403_for_unauthorized_user(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER)
    ticket = SimpleNamespace(id=uuid4(), created_by=uuid4(), assigned_to=None)
    fake_session = FakeSession(ticket=ticket, history=[])

    monkeypatch.setattr(tickets_routes, "get_db", lambda: fake_session)
    monkeypatch.setattr(tickets_routes, "get_current_active_user", lambda: user)

    with pytest.raises(HTTPException) as exc_info:
        tickets_routes.get_ticket_status_history(ticket.id, fake_session, user)

    assert exc_info.value.status_code == 403


def test_assignment_history_endpoint_returns_200_for_assigned_agent(monkeypatch):
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT)
    ticket = SimpleNamespace(id=uuid4(), created_by=uuid4(), assigned_to=user.id)
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
