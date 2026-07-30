"""Hace unico el nombre de categoria sin distinguir mayusculas

ID de revision: b2c3d4e5f6a7
Revision anterior: a1b2c3d4e5f6
Fecha de creacion: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reemplaza la unique exacta por una unique sobre lower(name)."""

    # Evita que la migracion avance si ya existen duplicados case-insensitive.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT lower(name)
                FROM ticket_categories
                GROUP BY lower(name)
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'ticket_categories has duplicate names ignoring case';
            END IF;
        END $$;
        """
    )

    op.drop_constraint("ticket_categories_name_key", "ticket_categories", type_="unique")
    op.create_index(
        "uq_ticket_categories_lower_name",
        "ticket_categories",
        [sa.text("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    """Vuelve a la unique exacta sobre name."""

    op.drop_index("uq_ticket_categories_lower_name", table_name="ticket_categories")
    op.create_unique_constraint("ticket_categories_name_key", "ticket_categories", ["name"])
