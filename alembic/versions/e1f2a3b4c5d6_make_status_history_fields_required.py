"""Hace obligatorios campos del historial de estados

ID de revision: e1f2a3b4c5d6
Revision anterior: d9e8f7a6b5c4
Fecha de creacion: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d9e8f7a6b5c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Alinea el historial de estados con los datos necesarios para auditoria."""

    # No inventamos datos de auditoria: si existen filas incompletas,
    # hay que corregirlas manualmente antes de aplicar NOT NULL.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM ticket_status_history
                WHERE ticket_id IS NULL
                   OR old_status IS NULL
                   OR new_status IS NULL
                   OR changed_by IS NULL
            ) THEN
                RAISE EXCEPTION 'ticket_status_history has rows with required NULL fields';
            END IF;
        END $$;
        """
    )

    ticketstatus = postgresql.ENUM(
        "OPEN",
        "IN_PROGRESS",
        "ON_HOLD",
        "RESOLVED",
        "CLOSED",
        name="ticketstatus",
    )

    op.alter_column("ticket_status_history", "ticket_id", nullable=False)
    op.alter_column(
        "ticket_status_history",
        "old_status",
        existing_type=ticketstatus,
        nullable=False,
    )
    op.alter_column(
        "ticket_status_history",
        "new_status",
        existing_type=ticketstatus,
        nullable=False,
    )
    op.alter_column("ticket_status_history", "changed_by", nullable=False)


def downgrade() -> None:
    """Permite nuevamente NULL en campos principales del historial."""

    ticketstatus = postgresql.ENUM(
        "OPEN",
        "IN_PROGRESS",
        "ON_HOLD",
        "RESOLVED",
        "CLOSED",
        name="ticketstatus",
    )

    op.alter_column("ticket_status_history", "changed_by", nullable=True)
    op.alter_column(
        "ticket_status_history",
        "new_status",
        existing_type=ticketstatus,
        nullable=True,
    )
    op.alter_column(
        "ticket_status_history",
        "old_status",
        existing_type=ticketstatus,
        nullable=True,
    )
    op.alter_column("ticket_status_history", "ticket_id", nullable=True)
