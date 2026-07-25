"""Convierte roles y prioridades a enums

ID de revision: b8f3a2d9c741
Revision anterior: e7a4c246fce6
Fecha de creacion: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "b8f3a2d9c741"
down_revision: Union[str, Sequence[str], None] = "e7a4c246fce6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Aplica la conversion de strings a enums de PostgreSQL."""

    userrole = postgresql.ENUM("USER", "AGENT", "ADMIN", name="userrole")
    ticketpriority = postgresql.ENUM("LOW", "MEDIUM", "HIGH", name="ticketpriority")

    # Crea los tipos si todavia no existen.
    userrole.create(op.get_bind(), checkfirst=True)
    ticketpriority.create(op.get_bind(), checkfirst=True)

    # Convierte los valores existentes de texto a enum.
    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN role TYPE userrole "
        "USING role::userrole"
    )
    op.execute(
        "ALTER TABLE tickets "
        "ALTER COLUMN priority TYPE ticketpriority "
        "USING priority::ticketpriority"
    )


def downgrade() -> None:
    """Revierte los enums a columnas de texto."""

    op.execute(
        "ALTER TABLE tickets "
        "ALTER COLUMN priority TYPE VARCHAR "
        "USING priority::text"
    )
    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN role TYPE VARCHAR "
        "USING role::text"
    )

    userrole = postgresql.ENUM("USER", "AGENT", "ADMIN", name="userrole")
    ticketpriority = postgresql.ENUM("LOW", "MEDIUM", "HIGH", name="ticketpriority")

    # Borra los tipos si ya no estan en uso.
    ticketpriority.drop(op.get_bind(), checkfirst=True)
    userrole.drop(op.get_bind(), checkfirst=True)
