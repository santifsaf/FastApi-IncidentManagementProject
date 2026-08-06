from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.category import CategoryTeam, TicketCategory
from app.models.team import Team, TeamMember
from app.models.ticket import Ticket, TicketStatus
from app.models.user import UserRole
from app.services.category_service import (
    CategoryAlreadyExistsError,
    CategoryPermissionError,
    CategoryTeamAlreadyExistsError,
    InvalidCategoryNameError,
    add_category_team_service,
    create_category_service,
    get_category_ticket_queue_service,
)


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

    def offset(self, skip):
        self.items = self.items[skip:]
        return self

    def limit(self, limit):
        self.items = self.items[:limit]
        return self

    def first(self):
        return self.item

    def all(self):
        return self.items


class FakeDb:
    def __init__(self, category=None, team=None, category_team=None, category_team_member=None, tickets=None):
        self.category = category
        self.team = team
        self.category_team = category_team
        self.category_team_member = category_team_member
        self.tickets = tickets or []
        self.added = []
        self.committed = False
        self.refreshed = None
        self.rolled_back = False

    def query(self, model):
        model_class = getattr(model, "class_", None)
        if model is TicketCategory or model_class is TicketCategory:
            return FakeQuery(self.category)
        if model is Ticket or model_class is Ticket:
            return FakeQuery(items=self.tickets)
        if model is Team or model_class is Team:
            return FakeQuery(self.team)
        if model is CategoryTeam or model_class is CategoryTeam:
            return FakeQuery(self.category_team or self.category_team_member)
        if model is TeamMember or model_class is TeamMember:
            return FakeQuery(self.category_team_member)
        raise AssertionError(f"Unexpected model queried: {model}")

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = obj

    def rollback(self):
        self.rolled_back = True


def test_create_category_service_creates_active_category_with_normalized_name():
    db = FakeDb(category=None)
    category_in = SimpleNamespace(name="  Hardware  ", description="Devices")

    result = create_category_service(db, category_in)

    assert isinstance(result, TicketCategory)
    assert result.name == "Hardware"
    assert result.description == "Devices"
    assert result.is_active is True
    assert db.committed is True
    assert db.refreshed is result


def test_create_category_service_rejects_empty_name():
    db = FakeDb()
    category_in = SimpleNamespace(name="   ", description=None)

    with pytest.raises(InvalidCategoryNameError, match="cannot be empty"):
        create_category_service(db, category_in)

    assert db.added == []


def test_create_category_service_rejects_case_insensitive_duplicate():
    existing_category = SimpleNamespace(id=uuid4(), name="Hardware")
    db = FakeDb(category=existing_category)
    category_in = SimpleNamespace(name=" hardware ", description=None)

    with pytest.raises(CategoryAlreadyExistsError, match="already exists"):
        create_category_service(db, category_in)

    assert db.added == []
    assert db.committed is False


def test_add_category_team_service_creates_relation():
    category = SimpleNamespace(id=uuid4(), is_active=True)
    team = SimpleNamespace(id=uuid4())
    db = FakeDb(category=category, team=team, category_team=None)

    result = add_category_team_service(db, category.id, team.id)

    assert isinstance(result, CategoryTeam)
    assert result.category_id == category.id
    assert result.team_id == team.id
    assert db.committed is True
    assert db.refreshed is result


def test_add_category_team_service_rejects_duplicate_relation():
    category = SimpleNamespace(id=uuid4(), is_active=True)
    team = SimpleNamespace(id=uuid4())
    existing_relation = SimpleNamespace(id=uuid4())
    db = FakeDb(category=category, team=team, category_team=existing_relation)

    with pytest.raises(CategoryTeamAlreadyExistsError, match="already associated"):
        add_category_team_service(db, category.id, team.id)

    assert db.added == []


def test_admin_can_view_category_ticket_queue():
    category = SimpleNamespace(id=uuid4())
    tickets = [
        SimpleNamespace(id=uuid4(), category_id=category.id, team_id=None, status=TicketStatus.OPEN),
        SimpleNamespace(id=uuid4(), category_id=category.id, team_id=None, status=TicketStatus.ON_HOLD),
    ]
    current_user = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN)
    db = FakeDb(category=category, tickets=tickets)

    result = get_category_ticket_queue_service(db, category.id, current_user)

    assert result == tickets


def test_agent_in_associated_team_can_view_category_ticket_queue():
    category = SimpleNamespace(id=uuid4())
    category_team_member = SimpleNamespace(id=uuid4())
    ticket = SimpleNamespace(id=uuid4(), category_id=category.id, team_id=None, status=TicketStatus.OPEN)
    current_user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT)
    db = FakeDb(category=category, category_team_member=category_team_member, tickets=[ticket])

    result = get_category_ticket_queue_service(db, category.id, current_user)

    assert result == [ticket]


def test_agent_outside_associated_teams_cannot_view_category_ticket_queue():
    category = SimpleNamespace(id=uuid4())
    current_user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT)
    db = FakeDb(category=category, category_team_member=None, tickets=[])

    with pytest.raises(CategoryPermissionError, match="Not enough permissions"):
        get_category_ticket_queue_service(db, category.id, current_user)


def test_user_cannot_view_category_ticket_queue():
    category = SimpleNamespace(id=uuid4())
    current_user = SimpleNamespace(id=uuid4(), role=UserRole.USER)
    db = FakeDb(category=category, tickets=[])

    with pytest.raises(CategoryPermissionError, match="Not enough permissions"):
        get_category_ticket_queue_service(db, category.id, current_user)


def test_category_ticket_queue_applies_pagination():
    category = SimpleNamespace(id=uuid4())
    tickets = [
        SimpleNamespace(id=uuid4(), category_id=category.id, team_id=None, status=TicketStatus.OPEN),
        SimpleNamespace(id=uuid4(), category_id=category.id, team_id=None, status=TicketStatus.OPEN),
        SimpleNamespace(id=uuid4(), category_id=category.id, team_id=None, status=TicketStatus.OPEN),
    ]
    current_user = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN)
    db = FakeDb(category=category, tickets=tickets)

    result = get_category_ticket_queue_service(db, category.id, current_user, skip=1, limit=1)

    assert result == [tickets[1]]
