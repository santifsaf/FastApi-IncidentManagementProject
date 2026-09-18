"""Agrega routing por categoria y auditoria de autoasignaciones

ID de revision: 8bd42f10c7a1
Revision anterior: 7ac91e4b2d60
Fecha de creacion: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8bd42f10c7a1"
down_revision: Union[str, Sequence[str], None] = "7ac91e4b2d60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


team_assignment_strategy = postgresql.ENUM(
    "LEAST_LOAD_PER_MEMBER",
    name="teamassignmentstrategy",
    create_type=False,
)
assignment_source = postgresql.ENUM(
    "MANUAL",
    "CLAIM",
    "AUTOMATIC",
    name="assignmentsource",
    create_type=False,
)
agent_assignment_strategy = postgresql.ENUM(
    "LEAST_ACTIVE",
    "LONGEST_IDLE",
    name="assignmentstrategy",
    create_type=False,
)


def upgrade() -> None:
    """Agrega las dos etapas de autoasignacion y su fuente de auditoria."""

    team_assignment_strategy.create(op.get_bind(), checkfirst=True)
    assignment_source.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "ticket_categories",
        sa.Column("auto_team_assignment_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "ticket_categories",
        sa.Column("team_assignment_delay_minutes", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "ticket_categories",
        sa.Column(
            "team_assignment_strategy",
            team_assignment_strategy,
            server_default="LEAST_LOAD_PER_MEMBER",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_ticket_categories_team_assignment_delay_non_negative",
        "ticket_categories",
        "team_assignment_delay_minutes >= 0",
    )

    op.add_column("tickets", sa.Column("team_queue_entered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("team_assignment_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("team_assignment_strategy", team_assignment_strategy, nullable=True))
    op.add_column("tickets", sa.Column("auto_assignment_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tickets", sa.Column("auto_assignment_strategy", agent_assignment_strategy, nullable=True))

    for table_name in ("ticket_assignment_history", "ticket_team_history"):
        op.alter_column(table_name, "changed_by", existing_type=sa.UUID(), nullable=True)
        op.add_column(
            table_name,
            sa.Column("source", assignment_source, server_default="MANUAL", nullable=False),
        )
        op.alter_column(table_name, "source", server_default=None)


def downgrade() -> None:
    """Revierte routing, vencimientos y fuente de auditoria."""

    for table_name in ("ticket_team_history", "ticket_assignment_history"):
        op.execute(f"DELETE FROM {table_name} WHERE changed_by IS NULL")
        op.drop_column(table_name, "source")
        op.alter_column(table_name, "changed_by", existing_type=sa.UUID(), nullable=False)

    op.drop_column("tickets", "auto_assignment_strategy")
    op.drop_column("tickets", "auto_assignment_due_at")
    op.drop_column("tickets", "team_assignment_strategy")
    op.drop_column("tickets", "team_assignment_due_at")
    op.drop_column("tickets", "team_queue_entered_at")

    op.drop_constraint(
        "ck_ticket_categories_team_assignment_delay_non_negative",
        "ticket_categories",
        type_="check",
    )
    op.drop_column("ticket_categories", "team_assignment_strategy")
    op.drop_column("ticket_categories", "team_assignment_delay_minutes")
    op.drop_column("ticket_categories", "auto_team_assignment_enabled")

    assignment_source.drop(op.get_bind(), checkfirst=True)
    team_assignment_strategy.drop(op.get_bind(), checkfirst=True)
