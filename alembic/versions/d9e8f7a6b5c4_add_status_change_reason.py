"""Agrega motivo al historial de estados

ID de revision: d9e8f7a6b5c4
Revision anterior: c3d4f5a6b7e8
Fecha de creacion: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "d9e8f7a6b5c4"
down_revision: Union[str, Sequence[str], None] = "c3d4f5a6b7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Agrega el motivo opcional del cambio de estado."""

    op.add_column("ticket_status_history", sa.Column("reason", sa.Text(), nullable=True))


def downgrade() -> None:
    """Elimina el motivo del cambio de estado."""

    op.drop_column("ticket_status_history", "reason")
