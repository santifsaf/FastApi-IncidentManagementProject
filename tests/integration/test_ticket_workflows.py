"""Flujos criticos de tickets ejecutados contra PostgreSQL real."""

from uuid import uuid4

import pytest

from app.models.category import TicketCategory
from app.models.ticket import Ticket, TicketDependency, TicketStatus, TicketStatusHistory
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCreate
from app.services.ticket_service import (
    TicketBlockedByOpenDependenciesError,
    add_ticket_dependency,
    change_ticket_status,
    create_ticket_service,
)


pytestmark = pytest.mark.integration


def _create_user(db, role: UserRole) -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        password_hash="hash-de-test",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _create_category(db) -> TicketCategory:
    category = TicketCategory(name=f"Categoria {uuid4()}", is_active=True)
    db.add(category)
    db.flush()
    return category


def _create_ticket(db, creator: User, category: TicketCategory, **overrides) -> Ticket:
    values = {
        "title": "Ticket de integracion",
        "description": "Comprueba persistencia real",
        "status": TicketStatus.OPEN,
        "created_by": creator.id,
        "category_id": category.id,
    }
    values.update(overrides)
    ticket = Ticket(**values)
    db.add(ticket)
    db.flush()
    return ticket


def test_create_ticket_persists_server_managed_fields(integration_db):
    user = _create_user(integration_db, UserRole.USER)
    category = _create_category(integration_db)

    ticket = create_ticket_service(
        integration_db,
        TicketCreate(
            title="Error de login",
            description="No puedo ingresar",
            category_id=category.id,
        ),
        user,
    )

    persisted_ticket = integration_db.get(Ticket, ticket.id)
    assert persisted_ticket is not None
    assert persisted_ticket.status == TicketStatus.OPEN
    assert persisted_ticket.created_by == user.id
    assert persisted_ticket.category_id == category.id
    assert persisted_ticket.created_at is not None


def test_status_change_persists_ticket_and_history_atomically(integration_db):
    agent = _create_user(integration_db, UserRole.AGENT)
    category = _create_category(integration_db)
    ticket = _create_ticket(integration_db, agent, category, assigned_to=agent.id)

    result = change_ticket_status(
        integration_db,
        ticket,
        TicketStatus.IN_PROGRESS,
        agent,
    )

    history = (
        integration_db.query(TicketStatusHistory)
        .filter(TicketStatusHistory.ticket_id == ticket.id)
        .one()
    )
    assert result.status == TicketStatus.IN_PROGRESS
    assert history.old_status == TicketStatus.OPEN
    assert history.new_status == TicketStatus.IN_PROGRESS
    assert history.changed_by == agent.id
    assert history.changed_at is not None


def test_open_dependency_prevents_resolving_ticket(integration_db):
    admin = _create_user(integration_db, UserRole.ADMIN)
    category = _create_category(integration_db)
    blocked_ticket = _create_ticket(
        integration_db,
        admin,
        category,
        status=TicketStatus.IN_PROGRESS,
    )
    blocking_ticket = _create_ticket(integration_db, admin, category)

    dependency = add_ticket_dependency(
        integration_db,
        blocked_ticket.id,
        blocking_ticket.id,
        admin,
        reason="Falta resolver el ticket bloqueante",
    )

    with pytest.raises(TicketBlockedByOpenDependenciesError):
        change_ticket_status(
            integration_db,
            blocked_ticket,
            TicketStatus.RESOLVED,
            admin,
        )

    persisted_dependency = integration_db.get(TicketDependency, dependency.id)
    assert persisted_dependency is not None
    assert persisted_dependency.is_active is True
    assert blocked_ticket.status == TicketStatus.IN_PROGRESS
