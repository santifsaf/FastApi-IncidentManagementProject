"""Agrega dependencias entre tickets

ID de revision: e5f6a7b8c9d0
Revision anterior: d4e5f6a7b8c9
Fecha de creacion: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea la tabla que indica que un ticket depende de otro."""

    op.create_table(
        "ticket_dependencies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("depends_on_ticket_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["depends_on_ticket_id"], ["tickets.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", "depends_on_ticket_id", name="uq_ticket_dependencies_pair"),
    )


def downgrade() -> None:
    """Elimina la tabla de dependencias entre tickets."""

    op.drop_table("ticket_dependencies")
