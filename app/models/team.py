import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint, false, func
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
    # Cada equipo decide si sus agentes pueden tomar tickets de su propia cola.
    self_assignment_enabled = Column(Boolean, nullable=False, default=False, server_default=false())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    members = relationship(
        "TeamMember",
        back_populates="team",
        cascade="all, delete-orphan",
    )
    lead_assignments = relationship(
        "TeamLead",
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


class TeamLead(Base):
    __tablename__ = "team_leads"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_leads_team_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    team = relationship("Team", back_populates="lead_assignments")
    user = relationship("User", back_populates="team_lead_assignments")
