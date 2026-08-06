"""Agrega soft delete a dependencias de tickets

ID de revision: f6a7b8c9d0e1
Revision anterior: e5f6a7b8c9d0
Fecha de creacion: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Permite remover dependencias sin perder trazabilidad."""

    op.add_column(
        "ticket_dependencies",
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column("ticket_dependencies", sa.Column("removed_by", sa.UUID(), nullable=True))
    op.add_column("ticket_dependencies", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ticket_dependencies", sa.Column("removed_reason", sa.Text(), nullable=True))

    op.create_foreign_key(
        "fk_ticket_dependencies_removed_by_users",
        "ticket_dependencies",
        "users",
        ["removed_by"],
        ["id"],
    )

    # La constraint anterior no distingue activas/removidas. La reemplazamos
    # por un indice unico parcial: solo impide duplicar dependencias activas.
    op.drop_constraint("uq_ticket_dependencies_pair", "ticket_dependencies", type_="unique")
    op.create_index(
        "uq_ticket_dependencies_active_pair",
        "ticket_dependencies",
        ["ticket_id", "depends_on_ticket_id"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
    )


def downgrade() -> None:
    """Vuelve al borrado fisico de dependencias."""

    op.drop_index("uq_ticket_dependencies_active_pair", table_name="ticket_dependencies")
    op.create_unique_constraint(
        "uq_ticket_dependencies_pair",
        "ticket_dependencies",
        ["ticket_id", "depends_on_ticket_id"],
    )
    op.drop_constraint("fk_ticket_dependencies_removed_by_users", "ticket_dependencies", type_="foreignkey")
    op.drop_column("ticket_dependencies", "removed_reason")
    op.drop_column("ticket_dependencies", "removed_at")
    op.drop_column("ticket_dependencies", "removed_by")
    op.drop_column("ticket_dependencies", "is_active")
