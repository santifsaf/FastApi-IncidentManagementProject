"""Agrega equipos de trabajo

ID de revision: f2a3b4c5d6e7
Revision anterior: e1f2a3b4c5d6
Fecha de creacion: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea la estructura minima para equipos y vincula tickets a un equipo."""

    op.create_table(
        "teams",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_teams_name"), "teams", ["name"], unique=False)

    op.create_table(
        "team_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
    )

    # El ticket puede nacer sin equipo; por eso team_id queda nullable.
    op.add_column("tickets", sa.Column("team_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_tickets_team_id_teams", "tickets", "teams", ["team_id"], ["id"])


def downgrade() -> None:
    """Elimina la estructura de equipos."""

    op.drop_constraint("fk_tickets_team_id_teams", "tickets", type_="foreignkey")
    op.drop_column("tickets", "team_id")
    op.drop_table("team_members")
    op.drop_index(op.f("ix_teams_name"), table_name="teams")
    op.drop_table("teams")
