"""Casos de uso relacionados con comentarios de tickets."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.ticket_rules import (
    can_ticket_receive_comments,
    can_user_create_comment,
    can_user_view_comments,
)
from app.models.ticket import Ticket, TicketComment, TicketCommentVisibility
from app.models.user import User, UserRole
from app.schemas.ticket import TicketCommentCreate
from app.services.team_queries import is_team_lead, is_team_member
from app.services.ticket_exceptions import (
    TicketCommentError,
    TicketCommentNotAllowedError,
    TicketNotFoundError,
    TicketPermissionError,
)
from app.services.ticket_service_utils import commit_and_refresh


def create_ticket_comment(
    db: Session,
    ticket_id: UUID,
    comment_in: TicketCommentCreate,
    current_user: User,
) -> TicketComment:
    """Crea una respuesta al solicitante o una nota interna del equipo."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    is_member = False
    is_lead = False
    if current_user.role == UserRole.AGENT and ticket.team_id is not None:
        is_member = is_team_member(db, ticket.team_id, current_user.id)
        is_lead = is_team_lead(db, ticket.team_id, current_user.id)

    if not can_user_create_comment(
        current_user,
        ticket,
        comment_in.visibility,
        is_team_member=is_member,
        is_team_lead=is_lead,
    ):
        raise TicketPermissionError("Not enough permissions to add this ticket comment")

    if not can_ticket_receive_comments(ticket):
        raise TicketCommentNotAllowedError("Closed or archived tickets cannot receive comments")

    body = comment_in.body.strip()
    if not body:
        raise TicketCommentError("Comment body cannot be empty")

    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=current_user.id,
        body=body,
        visibility=comment_in.visibility,
    )
    db.add(comment)
    return commit_and_refresh(db, comment)


def get_ticket_comments(
    db: Session,
    ticket_id: UUID,
    current_user: User,
    skip: int = 0,
    limit: int = 20,
) -> list[TicketComment]:
    """Lista comentarios y oculta las notas internas al solicitante."""

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise TicketNotFoundError("Ticket not found")

    is_member = False
    if current_user.role == UserRole.AGENT and ticket.team_id is not None:
        is_member = is_team_member(db, ticket.team_id, current_user.id)

    if not can_user_view_comments(current_user, ticket, is_member):
        raise TicketPermissionError("Not enough permissions to view ticket comments")

    query = db.query(TicketComment).filter(TicketComment.ticket_id == ticket.id)

    # El solicitante recibe solo los comentarios dirigidos a el.
    if current_user.role == UserRole.USER:
        query = query.filter(TicketComment.visibility == TicketCommentVisibility.REQUESTER_VISIBLE)

    return (
        # El id desempata timestamps iguales y mantiene estable la paginacion.
        query.order_by(TicketComment.created_at.asc(), TicketComment.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
