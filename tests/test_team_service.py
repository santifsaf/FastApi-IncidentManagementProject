from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.team_service import InvalidTeamLeadError, InvalidTeamNameError, create_team_service


class FakeDb:
    def __init__(self, existing_team=None, lead_user=None):
        self.existing_team = existing_team
        self.lead_user = lead_user
        self.added = []
        self.committed = False
        self.refreshed = None
        self.rolled_back = False

    def query(self, model):
        if model is Team:
            return FakeQuery(self.existing_team)
        if model is User:
            return FakeQuery(self.lead_user)
        raise AssertionError(f"Unexpected model queried: {model}")

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        # En PostgreSQL real, flush inserta el Team y SQLAlchemy completa el id.
        for obj in self.added:
            if isinstance(obj, Team) and obj.id is None:
                obj.id = uuid4()

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = obj

    def rollback(self):
        self.rolled_back = True


class FakeQuery:
    def __init__(self, item=None):
        self.item = item

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.item


def test_create_team_service_creates_team_and_adds_lead_as_member():
    team_in = SimpleNamespace(name="Support", lead_id=uuid4())
    lead_user = SimpleNamespace(id=team_in.lead_id, role="AGENT", is_active=True)
    db = FakeDb(lead_user=lead_user)

    result = create_team_service(db, team_in)

    assert isinstance(result, Team)
    assert result.name == "Support"
    assert result.lead_id == lead_user.id
    assert db.committed is True
    assert db.refreshed is result

    member = db.added[1]
    assert isinstance(member, TeamMember)
    assert member.team_id == result.id
    assert member.user_id == lead_user.id


def test_create_team_service_rejects_non_agent_lead():
    team_in = SimpleNamespace(name="Support", lead_id=uuid4())
    lead_user = SimpleNamespace(id=team_in.lead_id, role="USER", is_active=True)
    db = FakeDb(lead_user=lead_user)

    with pytest.raises(InvalidTeamLeadError, match="Team lead must be an agent"):
        create_team_service(db, team_in)

    assert db.added == []


def test_create_team_service_rejects_empty_name():
    db = FakeDb()
    team_in = SimpleNamespace(name="   ", lead_id=uuid4())

    with pytest.raises(InvalidTeamNameError, match="Team name cannot be empty"):
        create_team_service(db, team_in)

    assert db.added == []
