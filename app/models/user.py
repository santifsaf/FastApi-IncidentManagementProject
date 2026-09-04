from datetime import datetime
import uuid
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, Enum as SqlEnum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class UserRole(str, Enum):
    USER = "USER"
    AGENT = "AGENT"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(SqlEnum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True)
    last_assigned_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    created_tickets = relationship(
        "Ticket",
        foreign_keys="Ticket.created_by",
        back_populates="creator",
    )

    assigned_tickets = relationship(
        "Ticket",
        foreign_keys="Ticket.assigned_to",
        back_populates="assigned_user",
    )

    team_memberships = relationship(
        "TeamMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    team_lead_assignments = relationship(
        "TeamLead",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    authored_ticket_comments = relationship(
        "TicketComment",
        back_populates="author",
    )
