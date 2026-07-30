from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.category import CategoryTeam, TicketCategory
from app.models.team import Team
from app.services.category_service import (
    CategoryAlreadyExistsError,
    CategoryTeamAlreadyExistsError,
    InvalidCategoryNameError,
    add_category_team_service,
    create_category_service,
)


class FakeQuery:
    def __init__(self, item=None):
        self.item = item

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.item


class FakeDb:
    def __init__(self, category=None, team=None, category_team=None):
        self.category = category
        self.team = team
        self.category_team = category_team
        self.added = []
        self.committed = False
        self.refreshed = None
        self.rolled_back = False

    def query(self, model):
        model_class = getattr(model, "class_", None)
        if model is TicketCategory or model_class is TicketCategory:
            return FakeQuery(self.category)
        if model is Team or model_class is Team:
            return FakeQuery(self.team)
        if model is CategoryTeam or model_class is CategoryTeam:
            return FakeQuery(self.category_team)
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
