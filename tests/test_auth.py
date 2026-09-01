"""Tests de autenticacion y JWT.

Cubren login, usuarios inactivos, normalizacion de email y claims obligatorios
del access token. No prueban rutas protegidas completas; eso queda para tests
HTTP con TestClient.
"""

from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException, status

from app.api.routes import auth as auth_routes
from app.models.user import User


class FakeQuery:
    def __init__(self, user):
        self.user = user

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.user


class FakeSession:
    def __init__(self, user=None):
        self.user = user

    def query(self, model):
        assert model is User
        return FakeQuery(self.user)


class FakeForm:
    def __init__(self, username, password):
        self.username = username
        self.password = password


def test_login_rejects_inactive_user(monkeypatch):
    inactive_user = SimpleNamespace(
        email="inactive@example.com",
        password_hash="fake-hash",
        is_active=False,
    )

    def fake_verify_password(plain_password, hashed_password):
        return True

    monkeypatch.setattr(auth_routes, "verify_password", fake_verify_password)
    fake_session = FakeSession(user=inactive_user)
    form = FakeForm(username="inactive@example.com", password="password")

    with pytest.raises(HTTPException) as exc_info:
        auth_routes.login(form_data=form, db=fake_session)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "Inactive user"


def test_login_returns_token_for_active_user(monkeypatch):
    active_user = SimpleNamespace(
        id="123",
        email="active@example.com",
        password_hash="fake-hash",
        is_active=True,
    )

    def fake_verify_password(plain_password, hashed_password):
        return True

    def fake_create_access_token(subject):
        assert subject == active_user.id
        return "token"

    monkeypatch.setattr(auth_routes, "verify_password", fake_verify_password)
    monkeypatch.setattr(auth_routes, "create_access_token", fake_create_access_token)
    fake_session = FakeSession(user=active_user)
    form = FakeForm(username="active@example.com", password="password")

    token = auth_routes.login(form_data=form, db=fake_session)

    assert token.access_token == "token"


def test_login_normalizes_email_before_lookup(monkeypatch):
    active_user = SimpleNamespace(
        id="123",
        email="user@example.com",
        password_hash="fake-hash",
        is_active=True,
    )

    def fake_verify_password(plain_password, hashed_password):
        return True

    def fake_create_access_token(subject):
        return "token"

    monkeypatch.setattr(auth_routes, "verify_password", fake_verify_password)
    monkeypatch.setattr(auth_routes, "create_access_token", fake_create_access_token)

    class NormalizingQuery(FakeQuery):
        def __init__(self, user):
            super().__init__(user)
            self.filter_condition = None

        def filter(self, condition):
            self.filter_condition = condition
            return self

    class NormalizingSession(FakeSession):
        def query(self, model):
            assert model is User
            self.last_query = NormalizingQuery(self.user)
            return self.last_query

    fake_session = NormalizingSession(user=active_user)
    form = FakeForm(username=" USER@Example.COM ", password="password")

    token = auth_routes.login(form_data=form, db=fake_session)

    assert token.access_token == "token"
    assert fake_session.last_query.filter_condition.right.value == "user@example.com"


def test_decode_access_token_returns_typed_payload(monkeypatch):
    from app.core.config import settings
    from app.core.security import create_access_token, decode_access_token

    # monkeypatch cambia settings solo durante este test y restaura los valores
    # originales al finalizar, evitando contaminar otros casos.
    monkeypatch.setattr(settings, "secret_key", "x" * 32)
    monkeypatch.setattr(settings, "algorithm", "HS256")
    monkeypatch.setattr(settings, "access_token_expire_minutes", 1)

    token = create_access_token("123e4567-e89b-12d3-a456-426614174000")
    payload = decode_access_token(token)

    assert str(payload.sub) == "123e4567-e89b-12d3-a456-426614174000"
    assert payload.exp > payload.iat
    assert payload.iat is not None


def test_decode_access_token_rejects_missing_required_claims(monkeypatch):
    from app.core.config import settings
    from app.core.security import decode_access_token

    # Usamos la misma configuracion controlada para generar y decodificar el JWT.
    monkeypatch.setattr(settings, "secret_key", "x" * 32)
    monkeypatch.setattr(settings, "algorithm", "HS256")

    token = jwt.encode(
        {"sub": "123e4567-e89b-12d3-a456-426614174000"},
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)
