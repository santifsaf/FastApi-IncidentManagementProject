"""${message}

ID de revision: ${up_revision}
Revision anterior: ${down_revision | comma,n}
Fecha de creacion: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """Aplica los cambios de esta migracion."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revierte los cambios de esta migracion."""
    ${downgrades if downgrades else "pass"}
