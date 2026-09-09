"""Tests unitarios del ciclo de vida y archivado de tickets."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.ticket import TicketStatus, TicketStatusHistory
from app.services.ticket_exceptions import (
    InvalidStatusTransitionError,
    MissingStatusChangeReasonError,
    TicketArchiveError,
    TicketPermissionError,
)
from app.services.ticket_lifecycle_service import (
    archive_old_closed_tickets,
    archive_ticket,
    change_ticket_status,
    unarchive_ticket,
)
from tests.ticket_service_fakes import FailingTeamAwareFakeDb, TeamAwareFakeDb


def test_change_ticket_status_updates_ticket_and_creates_history():
    ticket = SimpleNamespace(
        id=uuid4(),
        status="OPEN",
    )
    db = TeamAwareFakeDb(ticket=ticket)

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    result = change_ticket_status(db, ticket.id, "IN_PROGRESS", current_user)

    assert result is ticket
    assert ticket.status == "IN_PROGRESS"
    assert db.committed is True
    assert db.refreshed is ticket
    assert len(db.added) == 1

    history = db.added[0]
    assert isinstance(history, TicketStatusHistory)
    assert history.ticket_id == ticket.id
    assert history.old_status == "OPEN"
    assert history.new_status == "IN_PROGRESS"
    assert history.reason is None
    assert history.changed_by == current_user.id


def test_change_ticket_status_saves_reason_when_provided():
    ticket = SimpleNamespace(
        id=uuid4(),
        status="OPEN",
    )
    db = TeamAwareFakeDb(ticket=ticket)

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    result = change_ticket_status(db, ticket.id, "ON_HOLD", current_user, "Waiting for provider")

    assert result is ticket
    assert ticket.status == "ON_HOLD"

    history = db.added[0]
    assert history.reason == "Waiting for provider"


def test_change_ticket_status_sets_closed_at_when_closing_ticket():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.RESOLVED,
    )
    db = TeamAwareFakeDb(ticket=ticket)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    result = change_ticket_status(db, ticket.id, TicketStatus.CLOSED, current_user, "Confirmado")

    assert result is ticket
    assert ticket.status == TicketStatus.CLOSED
    assert ticket.closed_at is not None
    assert db.committed is True


def test_change_ticket_status_requires_reason_for_sensitive_status_change():
    ticket = SimpleNamespace(
        id=uuid4(),
        status="OPEN",
    )
    db = TeamAwareFakeDb(ticket=ticket)

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    with pytest.raises(MissingStatusChangeReasonError, match="Reason is required"):
        change_ticket_status(db, ticket.id, "ON_HOLD", current_user)

    assert ticket.status == "OPEN"
    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None


def test_admin_archives_closed_ticket():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        archived_at=None,
        archived_by=None,
        archive_reason=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket)

    result = archive_ticket(db, ticket.id, current_user, " Limpieza operativa ")

    assert result is ticket
    assert ticket.archived_at is not None
    assert ticket.archived_by == current_user.id
    assert ticket.archive_reason == "Limpieza operativa"
    assert db.committed is True


def test_archive_ticket_rejects_non_closed_ticket():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.IN_PROGRESS,
        archived_at=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket)

    with pytest.raises(TicketArchiveError, match="Only closed tickets"):
        archive_ticket(db, ticket.id, current_user, "Limpieza")

    assert ticket.archived_at is None
    assert db.committed is False


def test_archive_ticket_requires_reason():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        archived_at=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket)

    with pytest.raises(TicketArchiveError, match="Reason is required"):
        archive_ticket(db, ticket.id, current_user, "   ")

    assert ticket.archived_at is None
    assert db.committed is False


def test_admin_unarchives_archived_ticket():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        archived_at=object(),
        archived_by=uuid4(),
        archive_reason="Limpieza",
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket)

    result = unarchive_ticket(db, ticket.id, current_user)

    assert result is ticket
    assert ticket.archived_at is None
    assert ticket.archived_by is None
    assert ticket.archive_reason is None
    assert db.committed is True


def test_unarchive_ticket_rejects_visible_ticket():
    ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        archived_at=None,
    )
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")
    db = TeamAwareFakeDb(ticket=ticket)

    with pytest.raises(TicketArchiveError, match="not archived"):
        unarchive_ticket(db, ticket.id, current_user)

    assert db.committed is False


def test_archive_old_closed_tickets_archives_matching_tickets():
    old_closed_ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        closed_at=datetime.now(timezone.utc) - timedelta(days=45),
        archived_at=None,
        archived_by=None,
        archive_reason=None,
    )
    db = TeamAwareFakeDb(tickets=[old_closed_ticket])

    archived_count = archive_old_closed_tickets(db, days=30)

    assert archived_count == 1
    assert old_closed_ticket.archived_at is not None
    assert old_closed_ticket.archived_by is None
    assert old_closed_ticket.archive_reason == "Archivado automaticamente luego de 30 dias cerrado"
    assert db.committed is True


def test_archive_old_closed_tickets_rejects_invalid_days():
    db = TeamAwareFakeDb(tickets=[])

    with pytest.raises(TicketArchiveError, match="Days must be greater than zero"):
        archive_old_closed_tickets(db, days=0)

    assert db.committed is False


def test_archive_old_closed_tickets_rolls_back_when_commit_fails():
    old_closed_ticket = SimpleNamespace(
        id=uuid4(),
        status=TicketStatus.CLOSED,
        closed_at=datetime.now(timezone.utc) - timedelta(days=45),
        archived_at=None,
        archived_by=None,
        archive_reason=None,
    )
    db = FailingTeamAwareFakeDb(tickets=[old_closed_ticket])

    with pytest.raises(RuntimeError, match="Commit failed"):
        archive_old_closed_tickets(db, days=30)

    assert db.rolled_back is True


def test_change_ticket_status_treats_blank_reason_as_missing():
    ticket = SimpleNamespace(
        id=uuid4(),
        status="RESOLVED",
    )
    db = TeamAwareFakeDb(ticket=ticket)

    current_user = SimpleNamespace(
        id=uuid4(),
        role="ADMIN",
    )

    with pytest.raises(MissingStatusChangeReasonError, match="Reason is required"):
        change_ticket_status(db, ticket.id, "OPEN", current_user, "   ")

    assert ticket.status == "RESOLVED"
    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None


def test_change_ticket_status_raises_value_error_for_invalid_transition():
    ticket = SimpleNamespace(id=uuid4(), status="CLOSED")
    db = TeamAwareFakeDb(ticket=ticket)
    current_user = SimpleNamespace(id=uuid4(), role="ADMIN")

    with pytest.raises(InvalidStatusTransitionError, match="Invalid transition"):
        change_ticket_status(db, ticket.id, "OPEN", current_user)

    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None


def test_change_ticket_status_raises_permission_error_for_unauthorized_user():
    ticket = SimpleNamespace(id=uuid4(), status="OPEN")
    db = TeamAwareFakeDb(ticket=ticket)
    current_user = SimpleNamespace(id=uuid4(), role="USER")

    with pytest.raises(TicketPermissionError, match="Not enough permissions"):
        change_ticket_status(db, ticket.id, "IN_PROGRESS", current_user)

    assert db.added == []
    assert db.committed is False
    assert db.refreshed is None
