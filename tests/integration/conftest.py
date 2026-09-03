"""Infraestructura compartida para tests contra PostgreSQL real."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _get_test_database_url() -> str:
    """Obtiene una URL aislada y evita usar accidentalmente desarrollo.

    La validacion tambien vive en el script de creacion porque los tests deben
    protegerse aunque la base haya sido creada manualmente.
    """

    development_url = make_url(settings.database_url)
    test_url = make_url(settings.test_database_url) if settings.test_database_url else development_url.set(
        database=f"{development_url.database}_test"
    )

    if test_url == development_url:
        raise RuntimeError("La base de integracion no puede ser la base de desarrollo")

    if not test_url.database or not test_url.database.lower().endswith("_test"):
        raise RuntimeError("El nombre de la base de integracion debe terminar en '_test'")

    return test_url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def integration_engine():
    """Prepara el esquema una sola vez y comparte el engine durante la suite."""

    database_url = _get_test_database_url()

    # Ejecutamos las migraciones reales. Esto comprueba que una instalacion
    # nueva pueda reconstruir todo el esquema sin usar Base.create_all().
    alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_config.attributes["database_url"] = database_url
    command.upgrade(alembic_config, "head")

    # El engine administra el pool; cada test tomara su propia conexion.
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def integration_db(integration_engine):
    """Aisla cada test aunque el service ejecute su propio commit().

    La Session confirma savepoints internos. La transaccion exterior pertenece
    al fixture y siempre se revierte al terminar el test.
    """

    connection = integration_engine.connect()

    # Esta transaccion no pertenece al service. Permanece abierta durante todo
    # el test y nos permite borrar sus datos con un unico rollback final.
    outer_transaction = connection.begin()

    # Los commit() del service confirman savepoints internos, no la transaccion
    # exterior controlada por el fixture. Asi probamos el service sin falsearlo.
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        session.close()
        # Se ejecuta aunque el test falle: ningun dato de prueba queda guardado.
        outer_transaction.rollback()
        connection.close()
