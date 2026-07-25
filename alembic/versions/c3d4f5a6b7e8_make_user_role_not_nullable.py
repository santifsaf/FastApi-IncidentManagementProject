"""Hace users.role obligatorio

ID de revision: c3d4f5a6b7e8
Revision anterior: b8f3a2d9c741
Fecha de creacion: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "c3d4f5a6b7e8"
down_revision: Union[str, Sequence[str], None] = "b8f3a2d9c741"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Alinea users.role con el modelo SQLAlchemy."""

    # Asegura un valor valido antes de aplicar NOT NULL.
    op.execute("UPDATE users SET role = 'USER' WHERE role IS NULL")
    op.alter_column(
        "users",
        "role",
        existing_type=postgresql.ENUM("USER", "AGENT", "ADMIN", name="userrole"),
        nullable=False,
    )


def downgrade() -> None:
    """Permite nuevamente NULL en users.role."""

    op.alter_column(
        "users",
        "role",
        existing_type=postgresql.ENUM("USER", "AGENT", "ADMIN", name="userrole"),
        nullable=True,
    )
