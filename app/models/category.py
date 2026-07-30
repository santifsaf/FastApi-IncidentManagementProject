import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class TicketCategory(Base):
    __tablename__ = "ticket_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
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
