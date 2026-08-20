"""Agrega campos de archivado de tickets

ID de revision: c9d0e1f2a3b4
Revision anterior: b8c9d0e1f2a3
Fecha de creacion: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Agrega estado administrativo de archivo sin tocar el status operativo."""

    op.add_column("tickets", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("archived_by", sa.UUID(), nullable=True))
    op.add_column("tickets", sa.Column("archive_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_tickets_archived_by_users",
        "tickets",
        "users",
        ["archived_by"],
        ["id"],
    )


def downgrade() -> None:
    """Elimina los campos de archivado."""

    op.drop_constraint("fk_tickets_archived_by_users", "tickets", type_="foreignkey")
    op.drop_column("tickets", "archive_reason")
    op.drop_column("tickets", "archived_by")
    op.drop_column("tickets", "archived_at")
    op.drop_column("tickets", "closed_at")
