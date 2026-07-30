import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("name", name="teams_name_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, index=True)

    # El lead es un AGENT responsable de coordinar este equipo.
    lead_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    lead = relationship(
        "User",
        foreign_keys=[lead_id],
        back_populates="led_teams",
    )
    members = relationship(
        "TeamMember",
        back_populates="team",
        cascade="all, delete-orphan",
    )
    tickets = relationship("Ticket", back_populates="team")
    categories = relationship(
        "CategoryTeam",
        back_populates="team",
        cascade="all, delete-orphan",
    )


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")
