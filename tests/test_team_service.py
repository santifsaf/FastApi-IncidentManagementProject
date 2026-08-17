from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.team import Team, TeamLead, TeamMember
from app.models.user import User
from app.services.team_service import (
    InvalidTeamLeadError,
    InvalidTeamNameError,
    TeamLeadRemovalError,
    add_team_lead_service,
    create_team_service,
    get_team_leads_service,
    remove_team_lead_service,
    remove_team_member_service,
)


class FakeDb:
    def __init__(self, existing_team=None, lead_user=None, existing_lead=None, existing_member=None):
        self.existing_team = existing_team
        self.lead_user = lead_user
        self.existing_lead = existing_lead
        self.existing_member = existing_member
        self.added = []
        self.deleted = []
        self.committed = False
        self.refreshed = None
        self.rolled_back = False

    def query(self, model):
        model_class = getattr(model, "class_", None)
        if model is Team:
            return FakeQuery(self.existing_team)
        if model is User:
            return FakeQuery(self.lead_user)
        if model is TeamLead or model_class is TeamLead:
            return FakeQuery(self.existing_lead)
        if model is TeamMember or model_class is TeamMember:
            return FakeQuery(self.existing_member)
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

    def delete(self, obj):
        self.deleted.append(obj)


class FakeQuery:
    def __init__(self, item=None):
        self.item = item

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        if isinstance(self.item, list):
            return self.item[0] if self.item else None
        return self.item

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        if isinstance(self.item, list):
            return self.item
        return [] if self.item is None else [self.item]

    def count(self):
        if isinstance(self.item, list):
            return len(self.item)
        return 1 if self.item is not None else 0


def test_create_team_service_creates_team_and_adds_lead_as_member():
    team_in = SimpleNamespace(name="Support", lead_id=uuid4())
    lead_user = SimpleNamespace(id=team_in.lead_id, role="AGENT", is_active=True)
    db = FakeDb(lead_user=lead_user)

    result = create_team_service(db, team_in)

    assert isinstance(result, Team)
    assert result.name == "Support"
    assert db.committed is True
    assert db.refreshed is result

    lead = db.added[1]
    assert isinstance(lead, TeamLead)
    assert lead.team_id == result.id
    assert lead.user_id == lead_user.id

    member = db.added[2]
    assert isinstance(member, TeamMember)
    assert member.team_id == result.id
    assert member.user_id == lead_user.id


def test_add_team_lead_service_creates_lead_and_member_if_needed():
    team = SimpleNamespace(id=uuid4())
    new_lead_user = SimpleNamespace(id=uuid4(), role="AGENT", is_active=True)
    db = FakeDb(existing_team=team, lead_user=new_lead_user, existing_lead=None, existing_member=None)

    result = add_team_lead_service(db, team.id, new_lead_user.id)

    assert isinstance(result, TeamLead)
    assert result.team_id == team.id
    assert result.user_id == new_lead_user.id
    assert isinstance(db.added[0], TeamLead)
    assert isinstance(db.added[1], TeamMember)
    assert db.committed is True
    assert db.refreshed is result


def test_get_team_leads_service_returns_team_leads():
    team = SimpleNamespace(id=uuid4())
    leads = [
        SimpleNamespace(id=uuid4(), team_id=team.id, user_id=uuid4()),
        SimpleNamespace(id=uuid4(), team_id=team.id, user_id=uuid4()),
    ]
    db = FakeDb(existing_team=team, existing_lead=leads)

    result = get_team_leads_service(db, team.id)

    assert result == leads


def test_remove_team_lead_service_rejects_last_team_lead():
    team = SimpleNamespace(id=uuid4())
    lead_id = uuid4()
    lead = SimpleNamespace(id=uuid4(), team_id=team.id, user_id=lead_id)
    db = FakeDb(existing_team=team, existing_lead=[lead])

    with pytest.raises(TeamLeadRemovalError, match="at least one lead"):
        remove_team_lead_service(db, team.id, lead_id)

    assert db.deleted == []
    assert db.committed is False


def test_remove_team_lead_service_removes_lead_when_team_keeps_another_lead():
    team = SimpleNamespace(id=uuid4())
    lead_id = uuid4()
    lead = SimpleNamespace(id=uuid4(), team_id=team.id, user_id=lead_id)
    other_lead = SimpleNamespace(id=uuid4(), team_id=team.id, user_id=uuid4())
    db = FakeDb(existing_team=team, existing_lead=[lead, other_lead])

    remove_team_lead_service(db, team.id, lead_id)

    assert db.deleted == [lead]
    assert db.committed is True


def test_remove_team_member_service_rejects_additional_lead():
    team = SimpleNamespace(id=uuid4())
    additional_lead_id = uuid4()
    existing_lead = SimpleNamespace(id=uuid4(), team_id=team.id, user_id=additional_lead_id)
    db = FakeDb(existing_team=team, existing_lead=existing_lead)

    with pytest.raises(TeamLeadRemovalError, match="Team lead cannot be removed"):
        remove_team_member_service(db, team.id, additional_lead_id)

    assert db.deleted == []
    assert db.committed is False


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
