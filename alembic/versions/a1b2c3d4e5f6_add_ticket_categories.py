"""Agrega categorias de tickets

ID de revision: a1b2c3d4e5f6
Revision anterior: f2a3b4c5d6e7
Fecha de creacion: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea categorias, las vincula a teams y exige categoria en tickets nuevos."""

    op.create_table(
        "ticket_categories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="ticket_categories_name_key"),
    )
    op.create_index(op.f("ix_ticket_categories_name"), "ticket_categories", ["name"], unique=False)

    op.create_table(
        "category_teams",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["ticket_categories.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "team_id", name="uq_category_teams_category_team"),
    )

    # Como decidimos que no hay tickets existentes, category_id puede ser obligatorio.
    # Si hubiera filas en tickets, esta migracion debe frenarse y migrarlas antes.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM tickets) THEN
                RAISE EXCEPTION 'tickets table must be empty before adding required category_id';
            END IF;
        END $$;
        """
    )

    op.add_column("tickets", sa.Column("category_id", sa.UUID(), nullable=False))
    op.create_foreign_key(
        "fk_tickets_category_id_ticket_categories",
        "tickets",
        "ticket_categories",
        ["category_id"],
        ["id"],
    )


def downgrade() -> None:
    """Elimina categorias y la relacion obligatoria desde tickets."""

    op.drop_constraint("fk_tickets_category_id_ticket_categories", "tickets", type_="foreignkey")
    op.drop_column("tickets", "category_id")
    op.drop_table("category_teams")
    op.drop_index(op.f("ix_ticket_categories_name"), table_name="ticket_categories")
    op.drop_table("ticket_categories")
