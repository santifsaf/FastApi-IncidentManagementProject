"""Agrega configuracion de auto-reclamo por equipo

ID de revision: 4f6c8a91d2e3
Revision anterior: 9bdd685802ed
Fecha de creacion: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "4f6c8a91d2e3"
down_revision: Union[str, Sequence[str], None] = "9bdd685802ed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Habilita una configuracion independiente de reclamo para cada team."""

    op.add_column(
        "teams",
        sa.Column(
            "self_assignment_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Elimina la configuracion de auto-reclamo de los teams."""

    op.drop_column("teams", "self_assignment_enabled")
