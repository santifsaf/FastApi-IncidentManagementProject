"""Elimina lead_id de teams

ID de revision: b8c9d0e1f2a3
Revision anterior: a7b8c9d0e1f2
Fecha de creacion: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Quita la columna antigua porque los leads viven en team_leads."""

    op.drop_column("teams", "lead_id")


def downgrade() -> None:
    """Reconstruye lead_id tomando el primer lead registrado de cada team."""

    op.add_column("teams", sa.Column("lead_id", sa.UUID(), nullable=True))

    # Si alguna vez hay que volver atras, elegimos un lead existente por equipo
    # para reconstruir la columna vieja sin perder compatibilidad.
    op.execute(
        """
        UPDATE teams
        SET lead_id = first_leads.user_id
        FROM (
            SELECT DISTINCT ON (team_id)
                team_id,
                user_id
            FROM team_leads
            ORDER BY team_id, created_at ASC
        ) AS first_leads
        WHERE teams.id = first_leads.team_id
        """
    )

    op.alter_column("teams", "lead_id", nullable=False)
    op.create_foreign_key(
        "fk_teams_lead_id_users",
        "teams",
        "users",
        ["lead_id"],
        ["id"],
    )
