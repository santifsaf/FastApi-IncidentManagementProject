"""Agrega historial de equipos del ticket

ID de revision: c3d4e5f6a7b8
Revision anterior: b2c3d4e5f6a7
Fecha de creacion: 2026-07-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea la tabla que audita cambios de team_id en tickets."""

    op.create_table(
        "ticket_team_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("old_team_id", sa.UUID(), nullable=True),
        sa.Column("new_team_id", sa.UUID(), nullable=True),
        sa.Column("changed_by", sa.UUID(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["new_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["old_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Elimina el historial de equipos."""

    op.drop_table("ticket_team_history")
