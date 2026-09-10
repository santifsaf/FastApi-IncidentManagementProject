"""Agrega configuracion de autoasignacion por equipo

ID de revision: 7ac91e4b2d60
Revision anterior: 4f6c8a91d2e3
Fecha de creacion: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7ac91e4b2d60"
down_revision: Union[str, Sequence[str], None] = "4f6c8a91d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


assignment_strategy = postgresql.ENUM(
    "LEAST_ACTIVE",
    "LONGEST_IDLE",
    name="assignmentstrategy",
    create_type=False,
)


def upgrade() -> None:
    """Guarda la estrategia y el tiempo de espera elegidos para cada team."""

    assignment_strategy.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "teams",
        sa.Column("auto_assignment_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "teams",
        sa.Column("auto_assignment_delay_minutes", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "teams",
        sa.Column(
            "assignment_strategy",
            assignment_strategy,
            server_default="LEAST_ACTIVE",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_teams_auto_assignment_delay_non_negative",
        "teams",
        "auto_assignment_delay_minutes >= 0",
    )


def downgrade() -> None:
    """Retira la configuracion y su tipo enum de PostgreSQL."""

    op.drop_constraint("ck_teams_auto_assignment_delay_non_negative", "teams", type_="check")
    op.drop_column("teams", "assignment_strategy")
    op.drop_column("teams", "auto_assignment_delay_minutes")
    op.drop_column("teams", "auto_assignment_enabled")
    assignment_strategy.drop(op.get_bind(), checkfirst=True)
