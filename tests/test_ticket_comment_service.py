"""Tests unitarios de comentarios de tickets."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.ticket import (
    TicketComment,
    TicketCommentVisibility,
    TicketStatus,
)
from app.models.user import UserRole
from app.schemas.ticket import TicketCommentCreate
from app.services.ticket_comment_service import create_ticket_comment
from app.services.ticket_exceptions import (
    TicketCommentError,
    TicketCommentNotAllowedError,
)
from tests.ticket_service_fakes import TeamAwareFakeDb


def test_requester_creates_public_comment():
    requester = SimpleNamespace(id=uuid4(), role=UserRole.USER)
    ticket = SimpleNamespace(
        id=uuid4(),
        created_by=requester.id,
        assigned_to=None,
        team_id=None,
        status=TicketStatus.OPEN,
        archived_at=None,
    )
    db = TeamAwareFakeDb(ticket=ticket)

    comment = create_ticket_comment(
        db,
        ticket.id,
        TicketCommentCreate(
            body="  Todavia no puedo ingresar  ",
            visibility=TicketCommentVisibility.REQUESTER_VISIBLE,
        ),
        requester,
    )

    assert isinstance(comment, TicketComment)
    assert comment.author_id == requester.id
    assert comment.body == "Todavia no puedo ingresar"
    assert db.committed is True
    assert db.refreshed is comment


def test_create_ticket_comment_rejects_blank_body():
    requester = SimpleNamespace(id=uuid4(), role=UserRole.USER)
    ticket = SimpleNamespace(
        id=uuid4(),
        created_by=requester.id,
        assigned_to=None,
        team_id=None,
        status=TicketStatus.OPEN,
        archived_at=None,
    )
    db = TeamAwareFakeDb(ticket=ticket)

    with pytest.raises(TicketCommentError, match="Comment body cannot be empty"):
        create_ticket_comment(
            db,
            ticket.id,
            TicketCommentCreate(
                body="   ",
                visibility=TicketCommentVisibility.REQUESTER_VISIBLE,
            ),
            requester,
        )

    assert db.committed is False


@pytest.mark.parametrize(
    "status, archived_at",
    [
        (TicketStatus.CLOSED, None),
        (TicketStatus.OPEN, datetime(2024, 1, 1, tzinfo=timezone.utc)),
    ],
)
def test_create_ticket_comment_rejects_closed_or_archived_ticket(status, archived_at):
    requester = SimpleNamespace(id=uuid4(), role=UserRole.USER)
    ticket = SimpleNamespace(
        id=uuid4(),
        created_by=requester.id,
        assigned_to=None,
        team_id=None,
        status=status,
        archived_at=archived_at,
    )
    db = TeamAwareFakeDb(ticket=ticket)

    with pytest.raises(
        TicketCommentNotAllowedError,
        match="Closed or archived tickets cannot receive comments",
    ):
        create_ticket_comment(
            db,
            ticket.id,
            TicketCommentCreate(
                body="Nuevo comentario",
                visibility=TicketCommentVisibility.REQUESTER_VISIBLE,
            ),
            requester,
        )

    assert db.committed is False
