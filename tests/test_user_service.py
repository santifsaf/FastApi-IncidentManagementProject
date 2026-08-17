"""Tests del service de usuarios.

Se enfocan en reglas internas: email duplicado, normalizacion y rollback si
falla la transaccion.
"""

import pytest

from app.models.user import User
from app.schemas.user import UserCreate
from app.services.user_service import UserServiceError, create_user_service


class FakeQuery:
    def __init__(self, result=None):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.result


class FailingCommitDb:
    def __init__(self, existing_user=None):
        self.existing_user = existing_user
        self.added = []
        self.rolled_back = False

    def query(self, model):
        assert model is User
        return FakeQuery(self.existing_user)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        raise RuntimeError("Commit failed")

    def rollback(self):
        self.rolled_back = True


def test_create_user_service_rolls_back_when_commit_fails():
    db = FailingCommitDb()
    user_in = UserCreate(
        email="USER@Example.COM",
        password="secure-password",
        full_name="Test User",
    )

    with pytest.raises(RuntimeError, match="Commit failed"):
        create_user_service(db, user_in)

    assert len(db.added) == 1
    assert db.added[0].email == "user@example.com"
    assert db.rolled_back is True


def test_create_user_service_rejects_existing_email_before_insert():
    existing_user = object()
    db = FailingCommitDb(existing_user=existing_user)
    user_in = UserCreate(
        email=" USER@Example.COM ",
        password="secure-password",
        full_name="Test User",
    )

    with pytest.raises(UserServiceError) as exc_info:
        create_user_service(db, user_in)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Email already registered"
    assert db.added == []
    assert db.rolled_back is False
