"""Tests HTTP de endpoints de tickets.

Estos tests usan TestClient porque queremos validar la capa API: path real,
dependencias, status codes, response_model y serializacion JSON. La logica fina
del negocio queda cubierta en test_ticket_service.py y test_ticket_rules.py.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.ticket import TicketCommentVisibility, TicketPriority, TicketStatus
from app.models.user import UserRole
from app.services.ticket_service import (
    TicketArchiveError,
    TicketCommentNotAllowedError,
    TicketNotFoundError,
    TicketPermissionError,
)


class FakeQuery:
    """Query minima para endpoints que solo filtran, ordenan y paginan."""

    def __init__(self, items):
        self.items = items

    def filter(self, *args, **kwargs):
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
        return self.items[0] if self.items else None

    def all(self):
        return self.items


class FakeSession:
    """Sesion fake para tests HTTP livianos.

    No reemplaza los tests con base real. Sirve para que TestClient pueda pasar
    por FastAPI sin conectar a PostgreSQL en cada caso de endpoint.
    """

    def __init__(self, ticket=None, tickets=None, history=None):
        self.tickets = tickets if tickets is not None else ([ticket] if ticket else [])
        self.history = history or []

    def query(self, model):
        if model.__name__ == "Ticket":
            return FakeQuery(self.tickets)
        if model.__name__ in {
            "TicketStatusHistory",
            "TicketAssignmentHistory",
            "TicketTeamHistory",
            "TicketCategoryHistory",
        }:
            return FakeQuery(self.history)
        raise AssertionError(f"Unexpected model queried: {model}")


def make_ticket(**overrides):
    """Crea un ticket completo para que TicketRead pueda serializarlo."""

    data = {
        "id": uuid4(),
        "title": "Error en login",
        "description": "No puedo ingresar al sistema",
        "status": TicketStatus.OPEN,
        "priority": TicketPriority.MEDIUM,
        "created_by": uuid4(),
        "assigned_to": None,
        "team_id": None,
        "category_id": uuid4(),
        "closed_at": None,
        "archived_at": None,
        "archived_by": None,
        "archive_reason": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_created_by_me_endpoint_returns_created_tickets(client, override_current_user, override_db):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER, is_active=True)
    ticket = make_ticket(created_by=user.id)

    override_current_user(user)
    override_db(FakeSession(ticket=ticket))

    response = client.get("/tickets/created-by-me")

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(ticket.id)
    assert response.json()[0]["created_by"] == str(user.id)


def test_assigned_to_me_endpoint_returns_assigned_tickets(client, override_current_user, override_db):
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT, is_active=True)
    ticket = make_ticket(assigned_to=user.id)

    override_current_user(user)
    override_db(FakeSession(ticket=ticket))

    response = client.get("/tickets/assigned-to-me")

    assert response.status_code == 200
    assert response.json()[0]["assigned_to"] == str(user.id)


def test_assigned_to_me_endpoint_rejects_user_role(client, override_current_user, override_db):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER, is_active=True)

    override_current_user(user)
    override_db(FakeSession())

    response = client.get("/tickets/assigned-to-me")

    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions"


def test_get_all_tickets_endpoint_applies_pagination(client, override_current_user, override_db):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    tickets = [make_ticket(), make_ticket(), make_ticket()]

    override_current_user(admin)
    override_db(FakeSession(tickets=tickets))

    response = client.get("/tickets/?skip=1&limit=1")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(tickets[1].id)]


def test_get_ticket_detail_endpoint_returns_service_result(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER, is_active=True)
    ticket = make_ticket(created_by=user.id)

    override_current_user(user)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_get_ticket_detail(db, current_ticket_id, current_user):
        assert current_ticket_id == ticket.id
        assert current_user is user
        return ticket

    monkeypatch.setattr(
        tickets_routes,
        "get_ticket_detail",
        fake_get_ticket_detail,
    )

    response = client.get(f"/tickets/{ticket.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(ticket.id)


def test_get_ticket_detail_endpoint_maps_not_found_to_404(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER, is_active=True)
    ticket_id = uuid4()

    override_current_user(user)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_get_ticket_detail(db, current_ticket_id, current_user):
        raise TicketNotFoundError("Ticket not found")

    monkeypatch.setattr(tickets_routes, "get_ticket_detail", fake_get_ticket_detail)

    response = client.get(f"/tickets/{ticket_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket not found"


def test_get_ticket_detail_endpoint_maps_permission_error_to_403(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER, is_active=True)
    ticket_id = uuid4()

    override_current_user(user)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_get_ticket_detail(db, current_ticket_id, current_user):
        raise TicketPermissionError("Not enough permissions to view ticket")

    monkeypatch.setattr(tickets_routes, "get_ticket_detail", fake_get_ticket_detail)

    response = client.get(f"/tickets/{ticket_id}")

    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions to view ticket"


def test_status_history_endpoint_returns_403_for_unauthorized_user(client, override_current_user, override_db):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER, is_active=True)
    ticket = make_ticket(created_by=uuid4(), assigned_to=None, team_id=None)

    override_current_user(user)
    override_db(FakeSession(ticket=ticket, history=[]))

    response = client.get(f"/tickets/{ticket.id}/status-history")

    assert response.status_code == 403
    assert response.json()["detail"] == "Not enough permissions to view ticket status history"


def test_assignment_history_endpoint_returns_200_for_assigned_agent(client, override_current_user, override_db):
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT, is_active=True)
    ticket = make_ticket(assigned_to=user.id)
    history_item = SimpleNamespace(
        ticket_id=ticket.id,
        old_assigned_to=None,
        new_assigned_to=user.id,
        changed_by=user.id,
        changed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    override_current_user(user)
    override_db(FakeSession(ticket=ticket, history=[history_item]))

    response = client.get(f"/tickets/{ticket.id}/assignment-history")

    assert response.status_code == 200
    assert response.json()[0]["new_assigned_to"] == str(user.id)


def test_team_history_endpoint_returns_service_result(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT, is_active=True)
    ticket_id = uuid4()
    history_item = SimpleNamespace(
        old_team_id=None,
        new_team_id=uuid4(),
        changed_by=user.id,
        changed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    override_current_user(user)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_get_ticket_team_history_service(db, current_ticket_id, current_user):
        assert current_ticket_id == ticket_id
        assert current_user is user
        return [history_item]

    monkeypatch.setattr(
        tickets_routes,
        "get_ticket_team_history_service",
        fake_get_ticket_team_history_service,
    )

    response = client.get(f"/tickets/{ticket_id}/team-history")

    assert response.status_code == 200
    assert response.json()[0]["new_team_id"] == str(history_item.new_team_id)


def test_category_history_endpoint_returns_service_result(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT, is_active=True)
    ticket_id = uuid4()
    history_item = SimpleNamespace(
        old_category_id=uuid4(),
        new_category_id=uuid4(),
        reason="Categoria incorrecta",
        changed_by=user.id,
        changed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    override_current_user(user)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_get_ticket_category_history_service(db, current_ticket_id, current_user):
        assert current_ticket_id == ticket_id
        assert current_user is user
        return [history_item]

    monkeypatch.setattr(
        tickets_routes,
        "get_ticket_category_history_service",
        fake_get_ticket_category_history_service,
    )

    response = client.get(f"/tickets/{ticket_id}/category-history")

    assert response.status_code == 200
    assert response.json()[0]["new_category_id"] == str(history_item.new_category_id)


def test_blocked_tickets_endpoint_returns_service_result(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    user = SimpleNamespace(id=uuid4(), role=UserRole.AGENT, is_active=True)
    ticket_id = uuid4()
    blocked_ticket = make_ticket(
        title="Ticket bloqueado",
        description="Depende del ticket actual",
        status=TicketStatus.ON_HOLD,
    )

    override_current_user(user)
    override_db()

    # Este endpoint delega casi todo en el service; aca solo validamos wiring HTTP.
    from app.api.routes import tickets as tickets_routes

    def fake_get_blocked_tickets_service(db, current_ticket_id, current_user):
        assert current_ticket_id == ticket_id
        assert current_user is user
        return [blocked_ticket]

    monkeypatch.setattr(
        tickets_routes,
        "get_blocked_tickets_service",
        fake_get_blocked_tickets_service,
    )

    response = client.get(f"/tickets/{ticket_id}/blocked-tickets")

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(blocked_ticket.id)


def test_archive_ticket_endpoint_returns_archived_ticket(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    ticket = make_ticket(
        status=TicketStatus.CLOSED,
        archived_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        archived_by=admin.id,
        archive_reason="Limpieza operativa",
    )

    override_current_user(admin)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_archive_ticket(db, current_ticket_id, current_user, reason):
        assert current_ticket_id == ticket.id
        assert current_user is admin
        assert reason == "Limpieza operativa"
        return ticket

    monkeypatch.setattr(
        tickets_routes,
        "archive_ticket",
        fake_archive_ticket,
    )

    response = client.patch(
        f"/tickets/{ticket.id}/archive",
        json={"reason": "Limpieza operativa"},
    )

    assert response.status_code == 200
    assert response.json()["archived_by"] == str(admin.id)
    assert response.json()["archive_reason"] == "Limpieza operativa"


def test_archive_ticket_endpoint_maps_business_error_to_400(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    ticket_id = uuid4()

    override_current_user(admin)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_archive_ticket(db, current_ticket_id, current_user, reason):
        raise TicketArchiveError("Only closed tickets can be archived")

    monkeypatch.setattr(tickets_routes, "archive_ticket", fake_archive_ticket)

    response = client.patch(
        f"/tickets/{ticket_id}/archive",
        json={"reason": "Limpieza operativa"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only closed tickets can be archived"


def test_unarchive_ticket_endpoint_returns_visible_ticket(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN, is_active=True)
    ticket = make_ticket(status=TicketStatus.CLOSED)

    override_current_user(admin)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_unarchive_ticket(db, current_ticket_id, current_user):
        assert current_ticket_id == ticket.id
        assert current_user is admin
        return ticket

    monkeypatch.setattr(
        tickets_routes,
        "unarchive_ticket",
        fake_unarchive_ticket,
    )

    response = client.patch(f"/tickets/{ticket.id}/unarchive")

    assert response.status_code == 200
    assert response.json()["archived_at"] is None
    assert response.json()["archived_by"] is None
    assert response.json()["archive_reason"] is None


def test_create_comment_endpoint_returns_created_comment(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER, is_active=True)
    ticket_id = uuid4()
    comment = SimpleNamespace(
        id=uuid4(),
        ticket_id=ticket_id,
        author_id=user.id,
        body="Necesito ayuda con el acceso",
        visibility=TicketCommentVisibility.REQUESTER_VISIBLE,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    override_current_user(user)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_create_ticket_comment(db, current_ticket_id, comment_in, current_user):
        assert current_ticket_id == ticket_id
        assert current_user is user
        assert comment_in.visibility == TicketCommentVisibility.REQUESTER_VISIBLE
        return comment

    monkeypatch.setattr(tickets_routes, "create_ticket_comment", fake_create_ticket_comment)

    response = client.post(
        f"/tickets/{ticket_id}/comments",
        json={"body": comment.body, "visibility": "REQUESTER_VISIBLE"},
    )

    assert response.status_code == 201
    assert response.json()["visibility"] == "REQUESTER_VISIBLE"


def test_get_comments_endpoint_delegates_visibility_filter_to_service(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER, is_active=True)
    ticket_id = uuid4()
    comment = SimpleNamespace(
        id=uuid4(),
        ticket_id=ticket_id,
        author_id=uuid4(),
        body="Respuesta publica",
        visibility=TicketCommentVisibility.REQUESTER_VISIBLE,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    override_current_user(user)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_get_ticket_comments(db, current_ticket_id, current_user, skip, limit):
        assert current_ticket_id == ticket_id
        assert current_user is user
        assert (skip, limit) == (0, 20)
        return [comment]

    monkeypatch.setattr(tickets_routes, "get_ticket_comments", fake_get_ticket_comments)

    response = client.get(f"/tickets/{ticket_id}/comments")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(comment.id),
            "ticket_id": str(ticket_id),
            "author_id": str(comment.author_id),
            "body": "Respuesta publica",
            "visibility": "REQUESTER_VISIBLE",
            "created_at": "2024-01-01T00:00:00Z",
        }
    ]


def test_create_comment_endpoint_maps_closed_ticket_error_to_400(
    client,
    monkeypatch,
    override_current_user,
    override_db,
):
    user = SimpleNamespace(id=uuid4(), role=UserRole.USER, is_active=True)
    ticket_id = uuid4()
    override_current_user(user)
    override_db()

    from app.api.routes import tickets as tickets_routes

    def fake_create_ticket_comment(db, current_ticket_id, comment_in, current_user):
        raise TicketCommentNotAllowedError("Closed or archived tickets cannot receive comments")

    monkeypatch.setattr(tickets_routes, "create_ticket_comment", fake_create_ticket_comment)

    response = client.post(
        f"/tickets/{ticket_id}/comments",
        json={"body": "Comentario tardio", "visibility": "REQUESTER_VISIBLE"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Closed or archived tickets cannot receive comments"
