"""Crea la base PostgreSQL aislada usada por los tests de integracion."""

import argparse

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import make_url

from app.core.config import settings


def get_test_database_url():
    development_url = make_url(settings.database_url)
    test_url = make_url(settings.test_database_url) if settings.test_database_url else development_url.set(
        database=f"{development_url.database}_test"
    )

    if test_url == development_url:
        raise RuntimeError("La base de test no puede ser la base de desarrollo")

    if not test_url.database or not test_url.database.lower().endswith("_test"):
        raise RuntimeError("El nombre de la base de test debe terminar en '_test'")

    return test_url


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Elimina y vuelve a crear exclusivamente la base terminada en _test",
    )
    args = parser.parse_args()
    test_url = get_test_database_url()

    # PostgreSQL permite crear una base conectandose primero a la base de
    # mantenimiento "postgres". AUTOCOMMIT es obligatorio para CREATE DATABASE.
    connection = psycopg2.connect(
        dbname="postgres",
        user=test_url.username,
        password=test_url.password,
        host=test_url.host,
        port=test_url.port,
    )
    connection.autocommit = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_url.database,))
            if cursor.fetchone() is not None:
                if not args.recreate:
                    print(f"La base {test_url.database} ya existe")
                    return

                # Solo se llega aca despues de validar el sufijo _test. Cerramos
                # conexiones para poder recrear una base descartable limpia.
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (test_url.database,),
                )
                cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(test_url.database)))

            # Identifier escapa el nombre como identificador SQL; no concatenamos
            # texto recibido de configuracion dentro de la sentencia.
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(test_url.database)))
            print(f"Base {test_url.database} creada")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
