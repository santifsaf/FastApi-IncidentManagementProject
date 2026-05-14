import pytest

from app.core.ticket_rules import (
    can_user_assign_ticket,
    can_user_view_assignment_history,
    can_user_view_status_history,
)


class FakeUser:

    def __init__(self, role, id=None):
        self.role = role
        self.id = id


class FakeTicket:

    def __init__(self, created_by=None, assigned_to=None):
        self.created_by = created_by
        self.assigned_to = assigned_to


@pytest.mark.parametrize(
    "current_role, assigned_role, expected",
    [
        ("ADMIN", "AGENT", True),
        ("ADMIN", "USER", False),
        ("ADMIN", "ADMIN", False),
        ("AGENT", "AGENT", False),
        ("USER", "AGENT", False),
    ],
)
def test_can_user_assign_ticket_by_role(current_role, assigned_role, expected):
    current_user = FakeUser(role=current_role)
    assigned_user = FakeUser(role=assigned_role)

    result = can_user_assign_ticket(current_user, assigned_user)

    assert result is expected


def test_cannot_assign_ticket_to_missing_user():
    current_user = FakeUser(role="ADMIN")

    result = can_user_assign_ticket(current_user, None)

    assert result is False


@pytest.mark.parametrize(
    "role, user_id, created_by, assigned_to, expected",
    [
        ("ADMIN", "admin-id", "other-user", "other-agent", True),
        ("AGENT", "agent-id", "other-user", "agent-id", True),
        ("AGENT", "agent-id", "other-user", "other-agent", False),
        ("USER", "user-id", "user-id", None, True),
        ("USER", "user-id", "other-user", None, False),
    ],
)
def test_can_user_view_status_history(role, user_id, created_by, assigned_to, expected):
    user = FakeUser(role=role, id=user_id)
    ticket = FakeTicket(created_by=created_by, assigned_to=assigned_to)

    result = can_user_view_status_history(user, ticket)

    assert result is expected


@pytest.mark.parametrize(
    "role, user_id, assigned_to, expected",
    [
        ("ADMIN", "admin-id", "other-agent", True),
        ("AGENT", "agent-id", "agent-id", True),
        ("AGENT", "agent-id", "other-agent", False),
        ("USER", "user-id", "user-id", False),
    ],
)
def test_can_user_view_assignment_history(role, user_id, assigned_to, expected):
    user = FakeUser(role=role, id=user_id)
    ticket = FakeTicket(created_by=user_id, assigned_to=assigned_to)

    result = can_user_view_assignment_history(user, ticket)

    assert result is expected
