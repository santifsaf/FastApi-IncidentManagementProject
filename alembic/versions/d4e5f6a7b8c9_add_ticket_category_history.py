"""Agrega historial de categorias del ticket

ID de revision: d4e5f6a7b8c9
Revision anterior: c3d4e5f6a7b8
Fecha de creacion: 2026-07-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea la tabla que audita cambios de categoria en tickets."""

    op.create_table(
        "ticket_category_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("old_category_id", sa.UUID(), nullable=False),
        sa.Column("new_category_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.UUID(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["new_category_id"], ["ticket_categories.id"]),
        sa.ForeignKeyConstraint(["old_category_id"], ["ticket_categories.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Elimina el historial de categorias."""

    op.drop_table("ticket_category_history")
