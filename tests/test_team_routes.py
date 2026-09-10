"""Tests HTTP de endpoints de teams.

Estos casos no repiten toda la logica de team_service.py. Se enfocan en que
FastAPI resuelva dependencias, permisos, status codes y response_model.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.team import AssignmentStrategy
from app.models.user import UserRole
from app.services.team_service import TeamLeadRemovalError


def make_team(**overrides):
    data = {
        "id": uuid4(),
        "name": "Soporte",
        "self_assignment_enabled": False,
        "auto_assignment_enabled": False,
        "auto_assignment_delay_minutes": 0,
        "assignment_strategy": AssignmentStrategy.LEAST_ACTIVE,
        "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_team_lead(**overrides):
    data = {
        "id": uuid4(),
        "team_id": uuid4(),
        "user_id": uuid4(),
        "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_admin_can_create_team(client, monkeypatch, override_current_user, override_db):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    lead_id = uuid4()
    created_team = make_team(name="Soporte Nivel 1")

    override_current_user(admin)
    override_db()

    from app.api.routes import teams as teams_routes

    def fake_create_team_service(db, team_in):
        assert team_in.name == "Soporte Nivel 1"
        assert team_in.lead_id == lead_id
        return created_team

    monkeypatch.setattr(teams_routes, "create_team_service", fake_create_team_service)

    response = client.post(
        "/teams/",
        json={
            "name": "Soporte Nivel 1",
            "lead_id": str(lead_id),
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Soporte Nivel 1"
    assert "lead_id" not in response.json()


def test_admin_can_enable_team_self_assignment(client, monkeypatch, override_current_user, override_db):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    team_id = uuid4()
    updated_team = make_team(id=team_id, self_assignment_enabled=True)

    override_current_user(admin)
    override_db()

    from app.api.routes import teams as teams_routes

    def fake_update_team_self_assignment(db, current_team_id, enabled):
        assert current_team_id == team_id
        assert enabled is True
        return updated_team

    monkeypatch.setattr(
        teams_routes,
        "update_team_self_assignment_service",
        fake_update_team_self_assignment,
    )

    response = client.patch(
        f"/teams/{team_id}/self-assignment",
        json={"self_assignment_enabled": True},
    )

    assert response.status_code == 200
    assert response.json()["self_assignment_enabled"] is True


def test_agent_cannot_change_team_self_assignment(client, override_current_user, override_db):
    agent = SimpleNamespace(id=uuid4(), role=UserRole.AGENT, is_active=True)
    override_current_user(agent)
    override_db()

    response = client.patch(
        f"/teams/{uuid4()}/self-assignment",
        json={"self_assignment_enabled": True},
    )

    assert response.status_code == 403


def test_admin_configures_team_auto_assignment(client, monkeypatch, override_current_user, override_db):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    team_id = uuid4()
    updated_team = make_team(
        id=team_id,
        auto_assignment_enabled=True,
        auto_assignment_delay_minutes=20,
        assignment_strategy=AssignmentStrategy.LONGEST_IDLE,
    )
    override_current_user(admin)
    override_db()

    from app.api.routes import teams as teams_routes

    def fake_update_auto_assignment(db, current_team_id, enabled, delay_minutes, strategy):
        assert current_team_id == team_id
        assert enabled is True
        assert delay_minutes == 20
        assert strategy == AssignmentStrategy.LONGEST_IDLE
        return updated_team

    monkeypatch.setattr(
        teams_routes,
        "update_team_auto_assignment_service",
        fake_update_auto_assignment,
    )

    response = client.patch(
        f"/teams/{team_id}/auto-assignment",
        json={
            "auto_assignment_enabled": True,
            "auto_assignment_delay_minutes": 20,
            "assignment_strategy": "LONGEST_IDLE",
        },
    )

    assert response.status_code == 200
    assert response.json()["auto_assignment_enabled"] is True
    assert response.json()["auto_assignment_delay_minutes"] == 20
    assert response.json()["assignment_strategy"] == "LONGEST_IDLE"


def test_team_auto_assignment_rejects_negative_delay(client, override_current_user, override_db):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    override_current_user(admin)
    override_db()

    response = client.patch(
        f"/teams/{uuid4()}/auto-assignment",
        json={
            "auto_assignment_enabled": True,
            "auto_assignment_delay_minutes": -1,
            "assignment_strategy": "LEAST_ACTIVE",
        },
    )

    assert response.status_code == 422


def test_user_cannot_create_team(client, override_current_user, override_db):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER, is_active=True)

    override_current_user(user)
    override_db()

    response = client.post(
        "/teams/",
        json={
            "name": "Soporte Nivel 1",
            "lead_id": str(uuid4()),
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"


def test_admin_can_list_team_leads(client, monkeypatch, override_current_user, override_db):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    team_id = uuid4()
    leads = [
        make_team_lead(team_id=team_id),
        make_team_lead(team_id=team_id),
    ]

    override_current_user(admin)
    override_db()

    from app.api.routes import teams as teams_routes

    def fake_get_team_leads_service(db, current_team_id):
        assert current_team_id == team_id
        return leads

    monkeypatch.setattr(teams_routes, "get_team_leads_service", fake_get_team_leads_service)

    response = client.get(f"/teams/{team_id}/leads")

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["team_id"] == str(team_id)


def test_admin_can_add_team_lead(client, monkeypatch, override_current_user, override_db):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    team_id = uuid4()
    user_id = uuid4()
    created_lead = make_team_lead(team_id=team_id, user_id=user_id)

    override_current_user(admin)
    override_db()

    from app.api.routes import teams as teams_routes

    def fake_add_team_lead_service(db, current_team_id, current_user_id):
        assert current_team_id == team_id
        assert current_user_id == user_id
        return created_lead

    monkeypatch.setattr(teams_routes, "add_team_lead_service", fake_add_team_lead_service)

    response = client.post(
        f"/teams/{team_id}/leads",
        json={"user_id": str(user_id)},
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == str(user_id)


def test_remove_last_team_lead_returns_400(client, monkeypatch, override_current_user, override_db):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    team_id = uuid4()
    user_id = uuid4()

    override_current_user(admin)
    override_db()

    from app.api.routes import teams as teams_routes

    def fake_remove_team_lead(db, current_team_id, current_user_id):
        raise TeamLeadRemovalError("Team must have at least one lead")

    monkeypatch.setattr(teams_routes, "remove_team_lead_service", fake_remove_team_lead)

    response = client.delete(f"/teams/{team_id}/leads/{user_id}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Team must have at least one lead"
