"""Tests de reglas puras de tickets.

Estas funciones no deberian depender de FastAPI ni de SQLAlchemy. Por eso son
tests baratos, rapidos y faciles de leer.
"""

import pytest

from app.core.ticket_rules import (
    can_user_assign_ticket,
    can_user_change_status,
    can_user_view_ticket,
    can_user_view_assignment_history,
    can_user_view_status_history,
    is_status_change_reason_required,
    is_valid_status_transition,
)
from app.models.ticket import TicketStatus


class FakeUser:

    def __init__(self, role, id=None):
        self.role = role
        self.id = id


class FakeTicket:

    def __init__(self, created_by=None, assigned_to=None, team_id=None):
        self.created_by = created_by
        self.assigned_to = assigned_to
        self.team_id = team_id


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


def test_team_lead_can_assign_ticket_to_member_of_own_team():
    current_user = FakeUser(role="AGENT", id="lead-id")
    assigned_user = FakeUser(role="AGENT", id="agent-id")
    ticket = FakeTicket(team_id="team-id")

    result = can_user_assign_ticket(
        current_user,
        assigned_user,
        ticket,
        is_current_user_team_lead=True,
        is_assigned_user_team_member=True,
    )

    assert result is True


def test_team_lead_cannot_assign_ticket_to_agent_outside_team():
    current_user = FakeUser(role="AGENT", id="lead-id")
    assigned_user = FakeUser(role="AGENT", id="agent-id")
    ticket = FakeTicket(team_id="team-id")

    result = can_user_assign_ticket(
        current_user,
        assigned_user,
        ticket,
        is_current_user_team_lead=True,
        is_assigned_user_team_member=False,
    )

    assert result is False


def test_cannot_assign_ticket_to_missing_user():
    current_user = FakeUser(role="ADMIN")

    result = can_user_assign_ticket(current_user, None)

    assert result is False


@pytest.mark.parametrize(
    "role, user_id, created_by, assigned_to, is_team_member, expected",
    [
        ("ADMIN", "admin-id", "other-user", "other-agent", False, True),
        ("USER", "user-id", "user-id", None, False, True),
        ("USER", "user-id", "other-user", None, False, False),
        ("AGENT", "agent-id", "other-user", "agent-id", False, True),
        ("AGENT", "agent-id", "other-user", "other-agent", True, True),
        ("AGENT", "agent-id", "other-user", "other-agent", False, False),
    ],
)
def test_can_user_view_ticket(
    role,
    user_id,
    created_by,
    assigned_to,
    is_team_member,
    expected,
):
    """Cubre todos los caminos de visibilidad usados por el detalle."""

    user = FakeUser(role=role, id=user_id)
    ticket = FakeTicket(created_by=created_by, assigned_to=assigned_to, team_id="team-id")

    result = can_user_view_ticket(user, ticket, is_team_member=is_team_member)

    assert result is expected


@pytest.mark.parametrize(
    "role, assigned_to, current_status, new_status, expected",
    [
        ("ADMIN", None, TicketStatus.OPEN, TicketStatus.IN_PROGRESS, True),
        ("ADMIN", None, TicketStatus.OPEN, TicketStatus.CLOSED, True),
        ("AGENT", "agent-id", TicketStatus.OPEN, TicketStatus.IN_PROGRESS, True),
        ("AGENT", "other-agent", TicketStatus.OPEN, TicketStatus.IN_PROGRESS, False),
        ("AGENT", "agent-id", TicketStatus.OPEN, TicketStatus.CLOSED, False),
        ("USER", None, TicketStatus.OPEN, TicketStatus.IN_PROGRESS, False),
        ("USER", None, TicketStatus.CLOSED, TicketStatus.OPEN, False),
    ],
)
def test_can_user_change_status(role, assigned_to, current_status, new_status, expected):
    user = FakeUser(role=role, id="agent-id" if role == "AGENT" else "user-id")
    ticket = FakeTicket(assigned_to=assigned_to)

    result = can_user_change_status(user, ticket, new_status)

    assert result is expected


@pytest.mark.parametrize(
    "current_status, new_status, expected",
    [
        (TicketStatus.OPEN, TicketStatus.IN_PROGRESS, True),
        (TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, True),
        (TicketStatus.RESOLVED, TicketStatus.OPEN, True),
        (TicketStatus.OPEN, TicketStatus.CLOSED, False),
        (TicketStatus.CLOSED, TicketStatus.OPEN, False),
    ],
)
def test_is_valid_status_transition(current_status, new_status, expected):
    result = is_valid_status_transition(current_status, new_status)

    assert result is expected


@pytest.mark.parametrize(
    "current_status, new_status, expected",
    [
        (TicketStatus.OPEN, TicketStatus.ON_HOLD, True),
        (TicketStatus.RESOLVED, TicketStatus.CLOSED, True),
        (TicketStatus.RESOLVED, TicketStatus.OPEN, True),
        (TicketStatus.OPEN, TicketStatus.IN_PROGRESS, False),
        (TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, False),
    ],
)
def test_is_status_change_reason_required(current_status, new_status, expected):
    result = is_status_change_reason_required(current_status, new_status)

    assert result is expected


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
