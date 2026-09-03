"""Configura como Alembic encuentra los modelos y la base que debe migrar."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from app.core.config import settings
from app.db.base import Base
from app.models import category, team, ticket, user

# Objeto de configuracion de Alembic. Desde aca se leen valores de alembic.ini.
config = context.config

# Configura los logs definidos en alembic.ini para que Alembic muestre mensajes.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Base.metadata contiene las tablas que SQLAlchemy conoce.
# Los imports de app.models registran User, Team, Category, Ticket e historiales en esta metadata.
target_metadata = Base.metadata

# En CLI no existe el atributo y se usa APP_DATABASE_URL. Los tests agregan el
# atributo programaticamente para ejecutar la misma cadena sobre ticketing_test.
database_url = config.attributes.get("database_url", settings.database_url)
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Ejecuta migraciones en modo offline.

    En este modo Alembic no se conecta a la base. Usa solo la URL para generar
    SQL, por ejemplo con comandos que imprimen el script en vez de ejecutarlo.
    No es el modo habitual mientras desarrollas localmente.
    """

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecuta migraciones en modo online.

    Este es el modo normal: Alembic crea un engine, abre una conexion real
    contra PostgreSQL y aplica las migraciones pendientes.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


# Alembic decide el modo segun el comando usado. En el flujo normal entra al else.
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
