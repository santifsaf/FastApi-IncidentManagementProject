"""Tests HTTP de la configuración de routing de categorías."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.category import TeamAssignmentStrategy
from app.models.user import UserRole


def make_category(**overrides):
    data = {
        "id": uuid4(),
        "name": "Soporte técnico",
        "description": None,
        "is_active": True,
        "auto_team_assignment_enabled": False,
        "team_assignment_delay_minutes": 0,
        "team_assignment_strategy": TeamAssignmentStrategy.LEAST_LOAD_PER_MEMBER,
        "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_admin_configures_category_team_assignment(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    """El endpoint valida el contrato HTTP y delega el cambio al service."""

    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    category_id = uuid4()
    updated_category = make_category(
        id=category_id,
        auto_team_assignment_enabled=True,
        team_assignment_delay_minutes=15,
    )
    override_current_user(admin)
    override_db()

    from app.api.routes import categories as category_routes

    def fake_update_category_team_assignment(
        db,
        current_category_id,
        enabled,
        delay_minutes,
        strategy,
    ):
        assert current_category_id == category_id
        assert enabled is True
        assert delay_minutes == 15
        assert strategy == TeamAssignmentStrategy.LEAST_LOAD_PER_MEMBER
        return updated_category

    monkeypatch.setattr(
        category_routes,
        "update_category_team_assignment_service",
        fake_update_category_team_assignment,
    )

    response = client.patch(
        f"/ticket-categories/{category_id}/team-assignment",
        json={
            "auto_team_assignment_enabled": True,
            "team_assignment_delay_minutes": 15,
            "team_assignment_strategy": "LEAST_LOAD_PER_MEMBER",
        },
    )

    assert response.status_code == 200
    assert response.json()["auto_team_assignment_enabled"] is True
    assert response.json()["team_assignment_delay_minutes"] == 15


def test_agent_cannot_configure_category_team_assignment(
    client,
    override_current_user,
    override_db,
):
    agent = SimpleNamespace(id=uuid4(), role=UserRole.AGENT, is_active=True)
    override_current_user(agent)
    override_db()

    response = client.patch(
        f"/ticket-categories/{uuid4()}/team-assignment",
        json={
            "auto_team_assignment_enabled": True,
            "team_assignment_delay_minutes": 15,
            "team_assignment_strategy": "LEAST_LOAD_PER_MEMBER",
        },
    )

    assert response.status_code == 403


def test_category_team_assignment_rejects_negative_delay(
    client,
    override_current_user,
    override_db,
):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    override_current_user(admin)
    override_db()

    response = client.patch(
        f"/ticket-categories/{uuid4()}/team-assignment",
        json={
            "auto_team_assignment_enabled": True,
            "team_assignment_delay_minutes": -1,
            "team_assignment_strategy": "LEAST_LOAD_PER_MEMBER",
        },
    )

    assert response.status_code == 422
