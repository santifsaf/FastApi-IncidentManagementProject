"""Agrega comentarios publicos e internos a los tickets

ID de revision: d0e1f2a3b4c5
Revision anterior: c9d0e1f2a3b4
Fecha de creacion: 2026-09-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


comment_visibility = postgresql.ENUM(
    "REQUESTER_VISIBLE",
    "INTERNAL",
    name="ticketcommentvisibility",
    create_type=False,
)


def upgrade() -> None:
    """Crea un unico recurso de comentarios diferenciado por visibilidad."""

    comment_visibility.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("visibility", comment_visibility, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_comments_ticket_id", "ticket_comments", ["ticket_id"])


def downgrade() -> None:
    """Elimina los comentarios y su enum de visibilidad."""

    op.drop_index("ix_ticket_comments_ticket_id", table_name="ticket_comments")
    op.drop_table("ticket_comments")
    comment_visibility.drop(op.get_bind(), checkfirst=True)
