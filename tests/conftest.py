from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client():
    """Cliente HTTP de test.

    TestClient ejecuta la app FastAPI completa sin levantar uvicorn. Limpiamos
    overrides antes y despues para que un test no contamine al siguiente.
    """

    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def fake_db():
    """Objeto simple para endpoints donde el service esta mockeado."""

    return SimpleNamespace()


@pytest.fixture
def override_db(fake_db):
    """Reemplaza get_db por una dependencia controlada por el test."""

    def apply_override(db=fake_db):
        def get_test_db():
            yield db

        app.dependency_overrides[get_db] = get_test_db
        return db

    return apply_override


@pytest.fixture
def override_current_user():
    """Reemplaza la autenticacion para probar permisos sin generar JWTs."""

    def apply_override(user):
        def get_test_current_user():
            return user

        app.dependency_overrides[get_current_active_user] = get_test_current_user
        return user

    return apply_override
