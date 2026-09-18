import uuid
from enum import Enum as PythonEnum

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class TeamAssignmentStrategy(str, PythonEnum):
    """Criterios disponibles para enrutar una categoría hacia un equipo."""

    LEAST_LOAD_PER_MEMBER = "LEAST_LOAD_PER_MEMBER"


class TicketCategory(Base):
    __tablename__ = "ticket_categories"
    __table_args__ = (
        CheckConstraint(
            "team_assignment_delay_minutes >= 0",
            name="ck_ticket_categories_team_assignment_delay_non_negative",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    auto_team_assignment_enabled = Column(Boolean, nullable=False, default=False, server_default=false())
    team_assignment_delay_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    team_assignment_strategy = Column(
        Enum(TeamAssignmentStrategy, name="teamassignmentstrategy"),
        nullable=False,
        default=TeamAssignmentStrategy.LEAST_LOAD_PER_MEMBER,
        server_default=TeamAssignmentStrategy.LEAST_LOAD_PER_MEMBER.value,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tickets = relationship("Ticket", back_populates="category")
    teams = relationship(
        "CategoryTeam",
        back_populates="category",
        cascade="all, delete-orphan",
    )


Index("uq_ticket_categories_lower_name", func.lower(TicketCategory.name), unique=True)


class CategoryTeam(Base):
    __tablename__ = "category_teams"
    __table_args__ = (
        UniqueConstraint("category_id", "team_id", name="uq_category_teams_category_team"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = Column(UUID(as_uuid=True), ForeignKey("ticket_categories.id"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    category = relationship("TicketCategory", back_populates="teams")
    team = relationship("Team", back_populates="categories")
