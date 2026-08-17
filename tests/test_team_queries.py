"""Tests de consultas reutilizables de teams.

Estas funciones expresan permisos derivados de TeamLead y TeamMember. Se prueban
separadas porque services de tickets y teams dependen de ellas.
"""

from types import SimpleNamespace
from uuid import uuid4

from app.models.team import TeamLead, TeamMember
from app.services.team_queries import is_team_lead, is_team_member


class FakeDb:
    def __init__(self, team_lead=None, team_member=None):
        self.team_lead = team_lead
        self.team_member = team_member

    def query(self, model):
        model_class = getattr(model, "class_", None)
        if model is TeamLead or model_class is TeamLead:
            return FakeQuery(self.team_lead)
        if model is TeamMember or model_class is TeamMember:
            return FakeQuery(self.team_member)
        raise AssertionError(f"Unexpected model queried: {model}")


class FakeQuery:
    def __init__(self, item=None):
        self.item = item

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.item


def test_is_team_lead_accepts_registered_team_lead():
    team_id = uuid4()
    user_id = uuid4()
    db = FakeDb(
        team_lead=SimpleNamespace(id=uuid4(), team_id=team_id, user_id=user_id),
    )

    assert is_team_lead(db, team_id, user_id) is True


def test_is_team_lead_returns_false_without_registered_team_lead():
    db = FakeDb(team_lead=None)

    assert is_team_lead(db, uuid4(), uuid4()) is False


def test_is_team_member_returns_false_without_team():
    db = FakeDb()

    assert is_team_member(db, None, uuid4()) is False
