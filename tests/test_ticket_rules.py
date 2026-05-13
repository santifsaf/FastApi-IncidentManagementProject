import pytest

from app.core.ticket_rules import can_user_assign_ticket


class FakeUser:

    def __init__(self, role):
        self.role = role


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
