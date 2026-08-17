"""Agrega leads multiples por equipo

ID de revision: a7b8c9d0e1f2
Revision anterior: f6a7b8c9d0e1
Fecha de creacion: 2026-08-17

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea team_leads y migra los leads principales existentes."""

    op.create_table(
        "team_leads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_leads_team_user"),
    )

    connection = op.get_bind()
    teams = sa.table(
        "teams",
        sa.column("id", sa.UUID()),
        sa.column("lead_id", sa.UUID()),
    )
    team_leads = sa.table(
        "team_leads",
        sa.column("id", sa.UUID()),
        sa.column("team_id", sa.UUID()),
        sa.column("user_id", sa.UUID()),
    )

    # Copiamos el lead principal actual para que los equipos existentes entren
    # en el nuevo modelo sin perder compatibilidad con Team.lead_id.
    existing_teams = connection.execute(sa.select(teams.c.id, teams.c.lead_id)).all()
    if existing_teams:
        connection.execute(
            team_leads.insert(),
            [
                {
                    "id": uuid.uuid4(),
                    "team_id": team.id,
                    "user_id": team.lead_id,
                }
                for team in existing_teams
            ],
        )


def downgrade() -> None:
    """Elimina los leads multiples."""

    op.drop_table("team_leads")
