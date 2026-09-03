"""Esquema inicial.

Esta revision funciona como baseline: debe poder construir las tablas base en
una base vacia antes de que las siguientes migraciones agreguen funcionalidades.

ID de revision: e7a4c246fce6
Revision anterior:
Fecha de creacion: 2026-05-13 20:54:21.744274

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Identificadores que Alembic usa para ordenar y aplicar migraciones.
revision: str = 'e7a4c246fce6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Crea la estructura base sobre la que trabajan las demas migraciones."""

    # Crea el enum de PostgreSQL si todavia no existe.
    # checkfirst=True evita fallar si el tipo ya fue creado antes.
    ticketstatus = postgresql.ENUM('OPEN', 'IN_PROGRESS', 'ON_HOLD', 'RESOLVED', 'CLOSED', name='ticketstatus')
    ticketstatus.create(op.get_bind(), checkfirst=True)

    # Para columnas que usan el enum existente, create_type=False evita
    # que SQLAlchemy intente crear el mismo tipo otra vez.
    ticketstatus_column = postgresql.ENUM(
        'OPEN',
        'IN_PROGRESS',
        'ON_HOLD',
        'RESOLVED',
        'CLOSED',
        name='ticketstatus',
        create_type=False,
    )

    # Orden obligatorio: primero las entidades principales y despues las tablas
    # de auditoria que tienen foreign keys hacia ellas.
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=True),
        sa.Column('role', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('last_assigned_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.create_table(
        'tickets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        # Empiezan como texto porque las migraciones siguientes convierten
        # status y priority a enums de PostgreSQL de forma explicita.
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('priority', sa.String(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('assigned_to', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Historial de asignaciones:
    op.create_table(
        'ticket_assignment_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=False),
        sa.Column('old_assigned_to', sa.UUID(), nullable=True),
        sa.Column('new_assigned_to', sa.UUID(), nullable=True),
        sa.Column('changed_by', sa.UUID(), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['new_assigned_to'], ['users.id'], ),
        sa.ForeignKeyConstraint(['old_assigned_to'], ['users.id'], ),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Historial de estados:
    op.create_table(
        'ticket_status_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=True),
        sa.Column('old_status', ticketstatus_column, nullable=True),
        sa.Column('new_status', ticketstatus_column, nullable=True),
        sa.Column('changed_by', sa.UUID(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Convierte tickets.status de texto a enum. USING indica como transformar
    # los valores actuales, por ejemplo "OPEN" -> ticketstatus.OPEN.
    op.execute(
        'ALTER TABLE tickets '
        'ALTER COLUMN status TYPE ticketstatus '
        'USING status::ticketstatus'
    )


def downgrade() -> None:
    """Revierte los cambios de esta migracion."""

    # Primero elimina las tablas dependientes y despues las principales.
    op.drop_table('ticket_status_history')
    op.drop_table('ticket_assignment_history')
    op.drop_table('tickets')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')

    # Finalmente elimina el enum si ya no esta en uso.
    ticketstatus = postgresql.ENUM('OPEN', 'IN_PROGRESS', 'ON_HOLD', 'RESOLVED', 'CLOSED', name='ticketstatus')
    ticketstatus.drop(op.get_bind(), checkfirst=True)
