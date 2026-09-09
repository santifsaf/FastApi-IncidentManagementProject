"""Exige que los tickets asignados pertenezcan a un equipo

ID de revision: 9bdd685802ed
Revision anterior: d0e1f2a3b4c5
Fecha de creacion: 2026-09-08

"""
from typing import Sequence, Union

from alembic import op


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "9bdd685802ed"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Impide guardar un responsable en tickets que todavia no tienen team."""

    op.create_check_constraint(
        "ck_tickets_assigned_requires_team",
        "tickets",
        "assigned_to IS NULL OR team_id IS NOT NULL",
    )


def downgrade() -> None:
    """Retira la regla y vuelve a permitir asignaciones sin team."""

    op.drop_constraint(
        "ck_tickets_assigned_requires_team",
        "tickets",
        type_="check",
    )
